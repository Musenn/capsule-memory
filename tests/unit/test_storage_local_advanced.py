"""Advanced tests for capsule_memory/storage/local.py — search, msgpack, encrypted export/import."""
from __future__ import annotations

import json
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import pytest
from datetime import datetime
from pathlib import Path

from capsule_memory.models.capsule import (
    Capsule, CapsuleType, CapsuleStatus, CapsuleIdentity, CapsuleLifecycle,
    CapsuleMetadata,
)
from capsule_memory.storage.local import LocalStorage
from capsule_memory.exceptions import CapsuleNotFoundError, StorageError, TransportError


def _make_capsule(
    user_id: str = "u1",
    title: str = "Test",
    tags: list[str] | None = None,
    summary: str = "test summary",
) -> Capsule:
    c = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id=user_id, session_id="s1"),
        lifecycle=CapsuleLifecycle(status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow()),
        metadata=CapsuleMetadata(title=title, tags=tags or ["test"]),
        payload={
            "facts": [{"key": "lang", "value": "Python", "confidence": 0.9}],
            "context_summary": summary,
            "entities": {},
            "timeline": [],
            "raw_turns": [],
        },
    )
    c.integrity.checksum = c.compute_checksum()
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# search
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    async def test_search_matches_title(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule(title="Python Django Guide")
        await storage.save(c)

        results = await storage.search("Python", user_id="u1")
        assert len(results) >= 1
        capsule, score = results[0]
        assert capsule.capsule_id == c.capsule_id
        assert score > 0

    async def test_search_matches_tags(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule(tags=["python", "django"])
        await storage.save(c)

        results = await storage.search("django", user_id="u1")
        assert len(results) >= 1

    async def test_search_matches_summary(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule(summary="FastAPI web framework guide")
        await storage.save(c)

        results = await storage.search("FastAPI", user_id="u1")
        assert len(results) >= 1

    async def test_search_no_match(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule(title="Python Guide", tags=["python"])
        await storage.save(c)

        results = await storage.search("Kubernetes", user_id="u1")
        assert len(results) == 0

    async def test_search_multi_word_query(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule(title="Python Django Optimization", tags=["python", "django"])
        await storage.save(c)

        results = await storage.search("Python Django", user_id="u1")
        assert len(results) >= 1
        _, score = results[0]
        assert score == 1.0  # Both words match

    async def test_search_top_k(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        for i in range(10):
            c = _make_capsule(title=f"Python Guide {i}")
            await storage.save(c)

        results = await storage.search("Python", user_id="u1", top_k=3)
        assert len(results) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# msgpack format
# ═══════════════════════════════════════════════════════════════════════════════

class TestMsgpackFormat:
    async def test_save_and_get_msgpack(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path, format="msgpack")
        c = _make_capsule()
        await storage.save(c)

        retrieved = await storage.get(c.capsule_id)
        assert retrieved is not None
        assert retrieved.capsule_id == c.capsule_id
        assert retrieved.metadata.title == "Test"

    async def test_export_msgpack_format(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule()
        await storage.save(c)

        out = tmp_path / "export.capsule"
        await storage.export_capsule(c.capsule_id, str(out), format="msgpack")
        assert out.exists()
        assert out.stat().st_size > 0


# ═══════════════════════════════════════════════════════════════════════════════
# encrypted export/import
# ═══════════════════════════════════════════════════════════════════════════════

class TestEncryptedExportImport:
    async def test_export_encrypted_json(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule()
        await storage.save(c)

        out = tmp_path / "encrypted.json"
        await storage.export_capsule(
            c.capsule_id, str(out), format="json", encrypt=True, passphrase="secret123"
        )
        assert out.exists()
        data = json.loads(out.read_text())
        assert data.get("integrity", {}).get("encrypted") is True

    async def test_export_encrypted_msgpack(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule()
        await storage.save(c)

        out = tmp_path / "encrypted.capsule"
        await storage.export_capsule(
            c.capsule_id, str(out), format="msgpack", encrypt=True, passphrase="secret123"
        )
        assert out.exists()

    async def test_export_encrypted_requires_passphrase(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule()
        await storage.save(c)

        out = tmp_path / "no_pass.capsule"
        with pytest.raises(StorageError, match="passphrase"):
            await storage.export_capsule(
                c.capsule_id, str(out), format="msgpack", encrypt=True, passphrase=""
            )

    async def test_export_not_found_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        out = tmp_path / "nope.json"
        with pytest.raises(CapsuleNotFoundError):
            await storage.export_capsule("nonexistent", str(out))


# ═══════════════════════════════════════════════════════════════════════════════
# import — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestImportEdgeCases:
    async def test_import_msgpack_file(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule()
        await storage.save(c)

        export_path = tmp_path / "import_test.capsule"
        await storage.export_capsule(c.capsule_id, str(export_path), format="msgpack")

        imported = await storage.import_capsule_file(str(export_path), user_id="new_user")
        assert imported.identity.user_id == "new_user"
        assert imported.lifecycle.status == CapsuleStatus.IMPORTED

    async def test_import_txt_file(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "context.txt"
        txt_file.write_text("This is some context information for testing.", encoding="utf-8")

        storage = LocalStorage(path=tmp_path)
        imported = await storage.import_capsule_file(str(txt_file), user_id="txt_user")
        assert imported.capsule_type == CapsuleType.CONTEXT
        assert imported.identity.user_id == "txt_user"
        assert "context information" in imported.payload.get("content", "")

    async def test_import_nonexistent_file_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        with pytest.raises(StorageError, match="not found"):
            await storage.import_capsule_file(str(tmp_path / "nope.json"), "u1")

    async def test_import_invalid_json_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json!!!", encoding="utf-8")

        storage = LocalStorage(path=tmp_path)
        with pytest.raises(TransportError):
            await storage.import_capsule_file(str(bad_file), "u1")


# ═══════════════════════════════════════════════════════════════════════════════
# delete edge case — file already removed
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeleteEdgeCases:
    async def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        assert await storage.delete("nonexistent_id") is False


# ═══════════════════════════════════════════════════════════════════════════════
# list filters
# ═══════════════════════════════════════════════════════════════════════════════

class TestListFilters:
    async def test_list_filter_by_status(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        c = _make_capsule()
        await storage.save(c)

        results = await storage.list(status=CapsuleStatus.SEALED)
        assert len(results) >= 1

        results2 = await storage.list(status=CapsuleStatus.IMPORTED)
        assert len(results2) == 0

    async def test_list_with_offset(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        for i in range(5):
            c = _make_capsule(title=f"Cap {i}")
            await storage.save(c)

        all_results = await storage.list(user_id="u1")
        offset_results = await storage.list(user_id="u1", offset=2)
        assert len(offset_results) == len(all_results) - 2

    async def test_count_with_user_id(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        await storage.save(_make_capsule(user_id="u1"))
        await storage.save(_make_capsule(user_id="u1"))
        await storage.save(_make_capsule(user_id="u2"))

        assert await storage.count(user_id="u1") == 2
        assert await storage.count(user_id="u2") == 1
        assert await storage.count() == 3

    async def test_list_all_users(self, tmp_path: Path) -> None:
        storage = LocalStorage(path=tmp_path)
        await storage.save(_make_capsule(user_id="u1"))
        await storage.save(_make_capsule(user_id="u2"))

        results = await storage.list()
        assert len(results) == 2
