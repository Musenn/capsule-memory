"""Unit tests for capsule_memory/storage/qdrant_store.py — mock-based, no real Qdrant required."""
from __future__ import annotations

import asyncio
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from capsule_memory.models.capsule import (
    Capsule,
    CapsuleType,
    CapsuleStatus,
    CapsuleIdentity,
    CapsuleLifecycle,
    CapsuleMetadata,
)
from capsule_memory.exceptions import CapsuleNotFoundError, StorageError

try:
    import numpy as np  # noqa: F401
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

pytestmark = pytest.mark.skipif(not _HAS_NUMPY, reason="numpy not installed (qdrant extras)")


def _make_capsule(
    user_id: str = "u1",
    capsule_id: str | None = None,
    title: str = "Test Capsule",
    tags: list[str] | None = None,
    summary: str = "test summary",
    capsule_type: CapsuleType = CapsuleType.MEMORY,
    status: CapsuleStatus = CapsuleStatus.SEALED,
) -> Capsule:
    c = Capsule(
        capsule_type=capsule_type,
        identity=CapsuleIdentity(user_id=user_id, session_id="s1"),
        lifecycle=CapsuleLifecycle(
            status=status,
            sealed_at=datetime.utcnow(),
        ),
        metadata=CapsuleMetadata(title=title, tags=tags or ["test"], turn_count=3),
        payload={
            "facts": [{"key": "lang", "value": "Python", "confidence": 0.9}],
            "context_summary": summary,
            "entities": {},
            "timeline": [],
            "raw_turns": [],
        },
    )
    if capsule_id:
        c.capsule_id = capsule_id
    c.integrity.checksum = c.compute_checksum()
    return c


class _FakeCollectionInfo:
    """Fake Qdrant collection info."""
    def __init__(self, name: str, points_count: int = 0):
        self.name = name
        self.points_count = points_count


class _FakeCollections:
    """Fake Qdrant get_collections response."""
    def __init__(self, names: list[str]):
        self.collections = [_FakeCollectionInfo(n) for n in names]


class _FakePoint:
    """Fake Qdrant point."""
    def __init__(self, capsule_json: str, score: float = 0.9):
        self.payload = {"capsule_json": capsule_json, "capsule_id": "test"}
        self.score = score


class _FakeQueryResponse:
    """Fake Qdrant query_points response (wraps points list)."""
    def __init__(self, points: list[_FakePoint]):
        self.points = points


@pytest.fixture
def qdrant_storage():
    """Create a QdrantStorage with fully mocked dependencies."""
    mock_client = MagicMock()
    mock_model = MagicMock()

    # Mock model.encode to return a 384-dim vector
    import numpy as np
    mock_model.encode.return_value = np.random.rand(384).astype(np.float32)

    from capsule_memory.storage.qdrant_store import QdrantStorage
    storage = QdrantStorage.__new__(QdrantStorage)
    storage._url = "http://localhost:6333"
    storage._collection_prefix = "capsule"
    storage._client = mock_client
    storage._model_name = "all-MiniLM-L6-v2"
    storage._model = mock_model
    storage._model_lock = asyncio.Lock()
    storage._known_collections = set()
    storage._local_export_helper = AsyncMock()

    yield storage, mock_client, mock_model


# ═══════════════════════════════════════════════════════════════════════════════
# collection / point helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpers:
    def test_collection_name(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        assert storage._collection_name("u1") == "capsule_u1"

    def test_collection_name_special_chars(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        assert storage._collection_name("user-1.0") == "capsule_user_1_0"

    def test_point_id(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        assert storage._point_id("cap-123") == "cap-123"

    def test_get_searchable_text_memory(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        c = _make_capsule(title="Python Guide", tags=["python"], summary="a summary")
        text = storage._get_searchable_text(c)
        assert "Python Guide" in text
        assert "python" in text
        assert "a summary" in text

    def test_get_searchable_text_skill(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        c = _make_capsule(capsule_type=CapsuleType.SKILL)
        c.payload = {"description": "skill desc", "instructions": "do X"}
        text = storage._get_searchable_text(c)
        assert "skill desc" in text
        assert "do X" in text

    def test_get_searchable_text_hybrid(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        c = _make_capsule(capsule_type=CapsuleType.HYBRID)
        c.payload = {
            "memory": {"context_summary": "hybrid summary"},
            "skills": [{"description": "s1 desc"}],
        }
        text = storage._get_searchable_text(c)
        assert "hybrid summary" in text
        assert "s1 desc" in text

    def test_get_searchable_text_context(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        c = _make_capsule(capsule_type=CapsuleType.CONTEXT)
        c.payload = {"content": "some context content here"}
        text = storage._get_searchable_text(c)
        assert "some context content" in text


# ═══════════════════════════════════════════════════════════════════════════════
# _ensure_collection
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnsureCollection:
    async def test_creates_new_collection(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections([])

        result = await storage._ensure_collection("u1")
        assert result == "capsule_u1"
        mock_client.create_collection.assert_called_once()
        assert "capsule_u1" in storage._known_collections

    async def test_existing_collection_skipped(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])

        result = await storage._ensure_collection("u1")
        assert result == "capsule_u1"
        mock_client.create_collection.assert_not_called()

    async def test_cached_collection_skips_query(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        storage._known_collections.add("capsule_u1")

        result = await storage._ensure_collection("u1")
        assert result == "capsule_u1"
        mock_client.get_collections.assert_not_called()

    async def test_ensure_collection_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.side_effect = Exception("qdrant down")

        with pytest.raises(StorageError, match="Failed to ensure collection"):
            await storage._ensure_collection("u1")


# ═══════════════════════════════════════════════════════════════════════════════
# _get_model / _encode
# ═══════════════════════════════════════════════════════════════════════════════

class TestEncode:
    async def test_get_model_returns_existing(self, qdrant_storage: tuple) -> None:
        storage, _, mock_model = qdrant_storage
        model = await storage._get_model()
        assert model is mock_model

    async def test_encode_returns_list(self, qdrant_storage: tuple) -> None:
        storage, _, mock_model = qdrant_storage
        result = await storage._encode("test text")
        assert isinstance(result, list)
        assert len(result) == 384

    async def test_get_model_none_when_st_unavailable(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        storage._model = None
        with patch("capsule_memory.storage.qdrant_store._ST_AVAILABLE", False):
            model = await storage._get_model()
            assert model is None

    async def test_encode_zeros_without_model(self, qdrant_storage: tuple) -> None:
        storage, _, _ = qdrant_storage
        storage._model = None
        with patch("capsule_memory.storage.qdrant_store._ST_AVAILABLE", False):
            result = await storage._encode("test text")
            assert result == [0.0] * 384


# ═══════════════════════════════════════════════════════════════════════════════
# save
# ═══════════════════════════════════════════════════════════════════════════════

class TestSave:
    async def test_save_basic(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])

        capsule = _make_capsule()
        result = await storage.save(capsule)
        assert result == capsule.capsule_id
        mock_client.upsert.assert_called_once()

    async def test_save_raises_storage_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.upsert.side_effect = Exception("upsert fail")

        capsule = _make_capsule()
        with pytest.raises(StorageError, match="Failed to save"):
            await storage.save(capsule)


# ═══════════════════════════════════════════════════════════════════════════════
# get
# ═══════════════════════════════════════════════════════════════════════════════

class TestGet:
    async def test_get_found(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = [_FakePoint(capsule.to_json())]

        result = await storage.get(capsule.capsule_id)
        assert result is not None
        assert result.capsule_id == capsule.capsule_id

    async def test_get_not_found(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = []

        result = await storage.get("nonexistent")
        assert result is None

    async def test_get_no_collections(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections([])

        result = await storage.get("c1")
        assert result is None

    async def test_get_skips_non_prefixed_collections(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["other_collection"])

        result = await storage.get("c1")
        assert result is None

    async def test_get_raises_storage_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.side_effect = Exception("qdrant down")

        with pytest.raises(StorageError, match="Failed to get"):
            await storage.get("c1")

    async def test_get_continues_on_retrieve_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()
        mock_client.get_collections.return_value = _FakeCollections(
            ["capsule_u1", "capsule_u2"]
        )
        # First collection throws, second returns data
        mock_client.retrieve.side_effect = [
            Exception("timeout"),
            [_FakePoint(capsule.to_json())],
        ]

        result = await storage.get(capsule.capsule_id)
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# delete
# ═══════════════════════════════════════════════════════════════════════════════

class TestDelete:
    async def test_delete_found(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = [_FakePoint(capsule.to_json())]

        result = await storage.delete(capsule.capsule_id)
        assert result is True
        mock_client.delete.assert_called_once()

    async def test_delete_not_found(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = []

        result = await storage.delete("nonexistent")
        assert result is False

    async def test_delete_raises_storage_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = [_FakePoint(capsule.to_json())]
        mock_client.delete.side_effect = Exception("delete fail")

        with pytest.raises(StorageError, match="Failed to delete"):
            await storage.delete(capsule.capsule_id)


# ═══════════════════════════════════════════════════════════════════════════════
# list
# ═══════════════════════════════════════════════════════════════════════════════

class TestList:
    async def test_list_by_user(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        c1 = _make_capsule(capsule_id="c1")
        c2 = _make_capsule(capsule_id="c2")

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = (
            [_FakePoint(c1.to_json()), _FakePoint(c2.to_json())],
            None,
        )

        results = await storage.list(user_id="u1")
        assert len(results) == 2

    async def test_list_all_users(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        c = _make_capsule(capsule_id="c1")

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = ([_FakePoint(c.to_json())], None)

        results = await storage.list()
        assert len(results) == 1

    async def test_list_filter_by_type(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        c = _make_capsule(capsule_id="c1", capsule_type=CapsuleType.MEMORY)

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = ([_FakePoint(c.to_json())], None)

        results = await storage.list(user_id="u1", capsule_type=CapsuleType.MEMORY)
        assert len(results) == 1

    async def test_list_filter_by_tags(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        c_match = _make_capsule(capsule_id="c1", tags=["python", "django"])
        c_no = _make_capsule(capsule_id="c2", tags=["rust"])

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = (
            [_FakePoint(c_match.to_json()), _FakePoint(c_no.to_json())],
            None,
        )

        results = await storage.list(user_id="u1", tags=["python"])
        assert len(results) == 1
        assert "python" in results[0].metadata.tags

    async def test_list_empty_capsule_json(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        fake = MagicMock()
        fake.payload = {"capsule_json": ""}

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = ([fake], None)

        results = await storage.list(user_id="u1")
        assert len(results) == 0

    async def test_list_raises_storage_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.side_effect = Exception("qdrant down")

        with pytest.raises(StorageError, match="Failed to list"):
            await storage.list(user_id="u1")

    async def test_list_continues_on_scroll_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(
            ["capsule_u1", "capsule_u2"]
        )
        c = _make_capsule(capsule_id="c1")
        # First collection errors, second succeeds
        mock_client.scroll.side_effect = [
            Exception("scroll error"),
            ([_FakePoint(c.to_json())], None),
        ]
        # Need both collections in known_collections
        storage._known_collections = {"capsule_u1", "capsule_u2"}

        results = await storage.list()
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# search
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    async def test_vector_search(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        fake_hit = _FakePoint(capsule.to_json(), score=0.85)
        mock_client.query_points.return_value = _FakeQueryResponse([fake_hit])

        results = await storage.search("python guide", user_id="u1")
        assert len(results) == 1
        assert results[0][1] == 0.85

    async def test_search_clamps_score(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        fake_hit = _FakePoint(capsule.to_json(), score=1.5)  # above 1.0
        mock_client.query_points.return_value = _FakeQueryResponse([fake_hit])

        results = await storage.search("test", user_id="u1")
        assert results[0][1] == 1.0

    async def test_search_negative_score(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        fake_hit = _FakePoint(capsule.to_json(), score=-0.5)
        mock_client.query_points.return_value = _FakeQueryResponse([fake_hit])

        results = await storage.search("test", user_id="u1")
        assert results[0][1] == 0.0

    async def test_search_falls_back_to_keyword(self, qdrant_storage: tuple) -> None:
        storage, mock_client, mock_model = qdrant_storage
        # Make encode raise to trigger keyword fallback
        mock_model.encode.side_effect = Exception("model error")

        capsule = _make_capsule(title="Python Guide", tags=["python"])
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = ([_FakePoint(capsule.to_json())], None)

        results = await storage.search("python", user_id="u1")
        assert len(results) >= 1

    async def test_vector_search_error_falls_back(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule(title="Python Guide")

        mock_client.get_collections.side_effect = Exception("qdrant down")
        mock_client.scroll.return_value = ([_FakePoint(capsule.to_json())], None)

        # Should fall back to keyword search; keyword also calls list which calls get_collections
        # Reset side_effect for keyword path
        call_count = [0]
        _ = mock_client.get_collections.side_effect  # save ref before override

        def smart_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("qdrant down")
            return _FakeCollections(["capsule_u1"])

        mock_client.get_collections.side_effect = smart_side_effect
        storage._known_collections.add("capsule_u1")

        # The vector search path raises and falls back to _keyword_search,
        # which calls self.list, which also hits get_collections.
        # We need the second call to succeed.
        results = await storage.search("python")
        # May or may not find results depending on fallback path, but should not raise
        assert isinstance(results, list)

    async def test_search_all_collections(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(
            ["capsule_u1", "capsule_u2"]
        )
        fake_hit = _FakePoint(capsule.to_json(), score=0.7)
        mock_client.query_points.return_value = _FakeQueryResponse([fake_hit])

        results = await storage.search("test")
        assert len(results) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# _keyword_search
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeywordSearch:
    async def test_keyword_search_matches(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        c = _make_capsule(title="Python Guide", tags=["python"])

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = ([_FakePoint(c.to_json())], None)
        storage._known_collections.add("capsule_u1")

        results = await storage._keyword_search("python", user_id="u1")
        assert len(results) >= 1
        assert results[0][1] > 0

    async def test_keyword_search_no_match(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        c = _make_capsule(title="Rust Book")

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.scroll.return_value = ([_FakePoint(c.to_json())], None)
        storage._known_collections.add("capsule_u1")

        results = await storage._keyword_search("javascript", user_id="u1")
        assert len(results) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# count
# ═══════════════════════════════════════════════════════════════════════════════

class TestCount:
    async def test_count_for_user(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        info = _FakeCollectionInfo("capsule_u1", points_count=5)
        mock_client.get_collection.return_value = info

        result = await storage.count(user_id="u1")
        assert result == 5

    async def test_count_for_user_no_collection(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collection.side_effect = Exception("not found")

        result = await storage.count(user_id="u1")
        assert result == 0

    async def test_count_all(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(
            ["capsule_u1", "capsule_u2", "other"]
        )
        # get_collection returns info for each capsule-prefixed collection
        info1 = _FakeCollectionInfo("capsule_u1", points_count=3)
        info2 = _FakeCollectionInfo("capsule_u2", points_count=7)
        mock_client.get_collection.side_effect = [info1, info2]

        result = await storage.count()
        assert result == 10

    async def test_count_all_with_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(
            ["capsule_u1", "capsule_u2"]
        )
        info1 = _FakeCollectionInfo("capsule_u1", points_count=5)
        mock_client.get_collection.side_effect = [info1, Exception("err")]

        result = await storage.count()
        assert result == 5  # only first counted

    async def test_count_raises_storage_error(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.side_effect = Exception("total failure")

        with pytest.raises(StorageError, match="Failed to count"):
            await storage.count()


# ═══════════════════════════════════════════════════════════════════════════════
# export / import
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportImport:
    async def test_export_capsule(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = [_FakePoint(capsule.to_json())]

        storage._local_export_helper.save = AsyncMock()
        storage._local_export_helper.export_capsule = AsyncMock(
            return_value=Path("/out.json")
        )

        result = await storage.export_capsule(capsule.capsule_id, "/out.json")
        assert result == Path("/out.json")
        storage._local_export_helper.save.assert_awaited_once()

    async def test_export_not_found(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])
        mock_client.retrieve.return_value = []

        with pytest.raises(CapsuleNotFoundError):
            await storage.export_capsule("nonexistent", "/out.json")

    async def test_import_capsule_file(self, qdrant_storage: tuple) -> None:
        storage, mock_client, _ = qdrant_storage
        capsule = _make_capsule()

        storage._local_export_helper.import_capsule_file = AsyncMock(return_value=capsule)
        mock_client.get_collections.return_value = _FakeCollections(["capsule_u1"])

        result = await storage.import_capsule_file("/input.json", "u1")
        assert result.capsule_id == capsule.capsule_id
        storage._local_export_helper.import_capsule_file.assert_awaited_once()
        mock_client.upsert.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# _check_qdrant
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckQdrant:
    def test_not_available(self) -> None:
        from capsule_memory.storage.qdrant_store import _check_qdrant
        with patch("capsule_memory.storage.qdrant_store._QDRANT_AVAILABLE", False):
            with pytest.raises(StorageError, match="qdrant"):
                _check_qdrant()

    def test_available(self) -> None:
        from capsule_memory.storage.qdrant_store import _check_qdrant
        with patch("capsule_memory.storage.qdrant_store._QDRANT_AVAILABLE", True):
            _check_qdrant()  # should not raise
