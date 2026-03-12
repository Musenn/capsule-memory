"""Unit tests for capsule_memory/storage/redis_store.py — mock-based, no real Redis required."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import pytest
from datetime import datetime, timedelta, timezone
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


def _make_capsule(
    user_id: str = "u1",
    capsule_id: str | None = None,
    title: str = "Test Capsule",
    tags: list[str] | None = None,
    summary: str = "test summary",
    capsule_type: CapsuleType = CapsuleType.MEMORY,
    status: CapsuleStatus = CapsuleStatus.SEALED,
    expires_at: datetime | None = None,
) -> Capsule:
    c = Capsule(
        capsule_type=capsule_type,
        identity=CapsuleIdentity(user_id=user_id, session_id="s1"),
        lifecycle=CapsuleLifecycle(
            status=status,
            sealed_at=datetime.utcnow(),
            expires_at=expires_at,
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


def _mock_redis() -> AsyncMock:
    """Create a mock Redis client with common methods."""
    r = AsyncMock()

    # pipeline() is synchronous in redis.asyncio — returns a Pipeline object
    pipe = MagicMock()
    pipe.set = MagicMock()
    pipe.hset = MagicMock()
    pipe.zadd = MagicMock()
    pipe.delete = MagicMock()
    pipe.zrem = MagicMock()
    pipe.execute = AsyncMock(return_value=[True, True, True])
    r.pipeline = MagicMock(return_value=pipe)
    return r


@pytest.fixture
def mock_redis_module():
    """Patch redis.asyncio and return (storage, mock_redis)."""
    mock_r = _mock_redis()

    from capsule_memory.storage.redis_store import RedisStorage
    storage = RedisStorage.__new__(RedisStorage)
    storage._url = "redis://localhost:6379"
    storage._redis = mock_r
    storage._local_export_helper = AsyncMock()

    yield storage, mock_r


# ═══════════════════════════════════════════════════════════════════════════════
# Key generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeyGeneration:
    def test_capsule_key(self, mock_redis_module: tuple) -> None:
        storage, _ = mock_redis_module
        assert storage._capsule_key("u1", "c1") == "capsule:u1:c1"

    def test_index_key(self, mock_redis_module: tuple) -> None:
        storage, _ = mock_redis_module
        assert storage._index_key("u1") == "capsule_idx:u1"

    def test_meta_key(self, mock_redis_module: tuple) -> None:
        storage, _ = mock_redis_module
        assert storage._meta_key("u1", "c1") == "capsule_meta:u1:c1"


# ═══════════════════════════════════════════════════════════════════════════════
# save
# ═══════════════════════════════════════════════════════════════════════════════

class TestSave:
    async def test_save_basic(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsule = _make_capsule()
        result = await storage.save(capsule)
        assert result == capsule.capsule_id

        # Verify pipeline was used
        mock_r.pipeline.assert_called()
        pipe = mock_r.pipeline.return_value
        # pipe.set is called twice: capsule data + capsule_owner reverse index
        assert pipe.set.call_count == 2
        pipe.hset.assert_called_once()
        pipe.zadd.assert_called_once()
        pipe.execute.assert_awaited_once()

    async def test_save_with_ttl(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        capsule = _make_capsule(expires_at=future)
        await storage.save(capsule)
        mock_r.expire.assert_awaited_once()

    async def test_save_with_past_ttl_no_expire(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        capsule = _make_capsule(expires_at=past)
        await storage.save(capsule)
        # TTL <= 0, should not call expire
        mock_r.expire.assert_not_awaited()

    async def test_save_without_sealed_at(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsule = _make_capsule()
        capsule.lifecycle.sealed_at = None
        result = await storage.save(capsule)
        assert result == capsule.capsule_id
        # Score should be 0.0 when sealed_at is None
        pipe = mock_r.pipeline.return_value
        call_args = pipe.zadd.call_args
        mapping = call_args[0][1]
        assert list(mapping.values())[0] == 0.0

    async def test_save_raises_storage_error(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.pipeline.return_value.execute.side_effect = Exception("conn failed")
        capsule = _make_capsule()
        with pytest.raises(StorageError, match="Failed to save"):
            await storage.save(capsule)


# ═══════════════════════════════════════════════════════════════════════════════
# get
# ═══════════════════════════════════════════════════════════════════════════════

class TestGet:
    async def test_get_found(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsule = _make_capsule()
        capsule_json = capsule.to_json()

        # Mock scan_iter to yield a key
        async def _scan_iter(pattern: str):
            yield f"capsule:u1:{capsule.capsule_id}"

        mock_r.scan_iter = _scan_iter
        mock_r.get = AsyncMock(return_value=capsule_json)

        result = await storage.get(capsule.capsule_id)
        assert result is not None
        assert result.capsule_id == capsule.capsule_id

    async def test_get_not_found(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            return
            yield  # make it an async generator

        mock_r.scan_iter = _scan_iter
        # owner reverse-index lookup must return None so get() falls through to SCAN
        mock_r.get = AsyncMock(return_value=None)
        result = await storage.get("nonexistent")
        assert result is None

    async def test_get_raises_storage_error(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        # Make the initial owner lookup raise an error
        mock_r.get = AsyncMock(side_effect=Exception("redis error"))
        with pytest.raises(StorageError, match="Failed to get"):
            await storage.get("c1")

    async def test_get_by_user(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsule = _make_capsule()
        mock_r.get = AsyncMock(return_value=capsule.to_json())

        result = await storage._get_by_user("u1", capsule.capsule_id)
        assert result is not None
        assert result.capsule_id == capsule.capsule_id

    async def test_get_by_user_not_found(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.get = AsyncMock(return_value=None)

        result = await storage._get_by_user("u1", "nonexistent")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# delete
# ═══════════════════════════════════════════════════════════════════════════════

class TestDelete:
    async def test_delete_found(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            yield "capsule:u1:c1"

        mock_r.scan_iter = _scan_iter
        result = await storage.delete("c1")
        assert result is True

        pipe = mock_r.pipeline.return_value
        pipe.delete.assert_called()
        pipe.zrem.assert_called()

    async def test_delete_not_found(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            return
            yield

        mock_r.scan_iter = _scan_iter
        result = await storage.delete("nonexistent")
        assert result is False

    async def test_delete_raises_storage_error(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            raise Exception("redis down")
            yield

        mock_r.scan_iter = _scan_iter
        with pytest.raises(StorageError, match="Failed to delete"):
            await storage.delete("c1")

    async def test_delete_key_with_unexpected_format(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            yield "badkey"  # less than 3 parts when split by ':'

        mock_r.scan_iter = _scan_iter
        result = await storage.delete("c1")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# list
# ═══════════════════════════════════════════════════════════════════════════════

class TestList:
    async def test_list_by_user(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c1 = _make_capsule(capsule_id="c1", title="First")
        c2 = _make_capsule(capsule_id="c2", title="Second")

        mock_r.zrevrange = AsyncMock(return_value=["c1", "c2"])
        mock_r.get = AsyncMock(side_effect=[c1.to_json(), c2.to_json()])

        results = await storage.list(user_id="u1")
        assert len(results) == 2
        assert results[0].capsule_id == "c1"

    async def test_list_all_users(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c1 = _make_capsule(user_id="u1", capsule_id="c1")

        async def _scan_iter(pattern: str):
            yield "capsule_idx:u1"

        mock_r.scan_iter = _scan_iter
        mock_r.zrevrange = AsyncMock(return_value=["c1"])
        mock_r.get = AsyncMock(return_value=c1.to_json())

        results = await storage.list()
        assert len(results) == 1

    async def test_list_filter_by_type(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c_mem = _make_capsule(capsule_id="c1", capsule_type=CapsuleType.MEMORY)
        c_skill = _make_capsule(capsule_id="c2", capsule_type=CapsuleType.SKILL)

        mock_r.zrevrange = AsyncMock(return_value=["c1", "c2"])
        mock_r.get = AsyncMock(side_effect=[c_mem.to_json(), c_skill.to_json()])

        results = await storage.list(user_id="u1", capsule_type=CapsuleType.MEMORY)
        assert len(results) == 1
        assert results[0].capsule_type == CapsuleType.MEMORY

    async def test_list_filter_by_status(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c = _make_capsule(capsule_id="c1", status=CapsuleStatus.SEALED)

        mock_r.zrevrange = AsyncMock(return_value=["c1"])
        mock_r.get = AsyncMock(return_value=c.to_json())

        results = await storage.list(user_id="u1", status=CapsuleStatus.DRAFT)
        assert len(results) == 0

    async def test_list_filter_by_tags(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c1 = _make_capsule(capsule_id="c1", tags=["python", "django"])
        c2 = _make_capsule(capsule_id="c2", tags=["rust"])

        mock_r.zrevrange = AsyncMock(return_value=["c1", "c2"])
        mock_r.get = AsyncMock(side_effect=[c1.to_json(), c2.to_json()])

        results = await storage.list(user_id="u1", tags=["python"])
        assert len(results) == 1
        assert "python" in results[0].metadata.tags

    async def test_list_with_offset_and_limit(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsules = [_make_capsule(capsule_id=f"c{i}") for i in range(5)]

        mock_r.zrevrange = AsyncMock(return_value=[f"c{i}" for i in range(5)])
        mock_r.get = AsyncMock(side_effect=[c.to_json() for c in capsules])

        results = await storage.list(user_id="u1", limit=2, offset=1)
        assert len(results) == 2

    async def test_list_raises_storage_error(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.zrevrange = AsyncMock(side_effect=Exception("conn lost"))

        with pytest.raises(StorageError, match="Failed to list"):
            await storage.list(user_id="u1")

    async def test_list_skips_none_capsules(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        mock_r.zrevrange = AsyncMock(return_value=["c1", "c2"])
        mock_r.get = AsyncMock(side_effect=[None, _make_capsule(capsule_id="c2").to_json()])

        results = await storage.list(user_id="u1")
        assert len(results) == 1
        assert results[0].capsule_id == "c2"


# ═══════════════════════════════════════════════════════════════════════════════
# search
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    async def test_search_matches(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c = _make_capsule(title="Python Guide", tags=["python"])

        mock_r.zrevrange = AsyncMock(return_value=[c.capsule_id])
        mock_r.get = AsyncMock(return_value=c.to_json())

        results = await storage.search("python", user_id="u1")
        assert len(results) >= 1
        assert results[0][1] > 0

    async def test_search_no_match(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        c = _make_capsule(title="Rust Book")

        mock_r.zrevrange = AsyncMock(return_value=[c.capsule_id])
        mock_r.get = AsyncMock(return_value=c.to_json())

        results = await storage.search("javascript", user_id="u1")
        assert len(results) == 0

    async def test_search_respects_top_k(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsules = [_make_capsule(capsule_id=f"c{i}", title="Python topic") for i in range(10)]

        mock_r.zrevrange = AsyncMock(return_value=[f"c{i}" for i in range(10)])
        mock_r.get = AsyncMock(side_effect=[c.to_json() for c in capsules])

        results = await storage.search("python", user_id="u1", top_k=3)
        assert len(results) <= 3


# ═══════════════════════════════════════════════════════════════════════════════
# count
# ═══════════════════════════════════════════════════════════════════════════════

class TestCount:
    async def test_count_for_user(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.zcard = AsyncMock(return_value=5)
        result = await storage.count(user_id="u1")
        assert result == 5

    async def test_count_all(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            yield "capsule_idx:u1"
            yield "capsule_idx:u2"

        mock_r.scan_iter = _scan_iter
        mock_r.zcard = AsyncMock(side_effect=[3, 7])

        result = await storage.count()
        assert result == 10

    async def test_count_raises_storage_error(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.zcard = AsyncMock(side_effect=Exception("fail"))
        with pytest.raises(StorageError, match="Failed to count"):
            await storage.count(user_id="u1")


# ═══════════════════════════════════════════════════════════════════════════════
# export / import
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportImport:
    async def test_export_capsule(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsule = _make_capsule()

        # Mock get to return the capsule
        async def _scan_iter(pattern: str):
            yield f"capsule:u1:{capsule.capsule_id}"

        mock_r.scan_iter = _scan_iter
        mock_r.get = AsyncMock(return_value=capsule.to_json())

        from pathlib import Path
        storage._local_export_helper.save = AsyncMock()
        storage._local_export_helper.export_capsule = AsyncMock(return_value=Path("/out.json"))

        result = await storage.export_capsule(capsule.capsule_id, "/out.json")
        assert result == Path("/out.json")
        storage._local_export_helper.save.assert_awaited_once()
        storage._local_export_helper.export_capsule.assert_awaited_once()

    async def test_export_not_found(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module

        async def _scan_iter(pattern: str):
            return
            yield

        mock_r.scan_iter = _scan_iter
        # owner reverse-index lookup must return None so get() returns None
        mock_r.get = AsyncMock(return_value=None)
        with pytest.raises(CapsuleNotFoundError):
            await storage.export_capsule("nonexistent", "/out.json")

    async def test_import_capsule_file(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        capsule = _make_capsule()

        storage._local_export_helper.import_capsule_file = AsyncMock(return_value=capsule)

        # Mock save pipeline
        mock_r.pipeline.return_value.execute = AsyncMock(return_value=[True, True, True])

        result = await storage.import_capsule_file("/input.json", "u1")
        assert result.capsule_id == capsule.capsule_id
        storage._local_export_helper.import_capsule_file.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# publish_trigger
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublishTrigger:
    async def test_publish_trigger(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.publish = AsyncMock()
        await storage.publish_trigger("u1", {"skill_id": "s1", "action": "activate"})
        mock_r.publish.assert_awaited_once()
        call_args = mock_r.publish.call_args
        assert call_args[0][0] == "capsule:triggers:u1"

    async def test_publish_trigger_failure_logged(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        mock_r.publish = AsyncMock(side_effect=Exception("pub fail"))
        # Should not raise, just log warning
        await storage.publish_trigger("u1", {"test": True})


# ═══════════════════════════════════════════════════════════════════════════════
# close
# ═══════════════════════════════════════════════════════════════════════════════

class TestClose:
    async def test_close(self, mock_redis_module: tuple) -> None:
        storage, mock_r = mock_redis_module
        await storage.close()
        mock_r.close.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# _check_redis
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckRedis:
    def test_check_redis_not_available(self) -> None:
        from capsule_memory.storage.redis_store import _check_redis
        with patch("capsule_memory.storage.redis_store._REDIS_AVAILABLE", False):
            with pytest.raises(StorageError, match="redis"):
                _check_redis()

    def test_check_redis_available(self) -> None:
        from capsule_memory.storage.redis_store import _check_redis
        with patch("capsule_memory.storage.redis_store._REDIS_AVAILABLE", True):
            _check_redis()  # should not raise
