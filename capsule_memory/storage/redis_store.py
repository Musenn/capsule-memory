"""
RedisStorage — Redis-backed storage backend for CapsuleMemory.

Requires: pip install 'capsule-memory[redis]'

Features:
    - Redis Hash per capsule with JSON-serialized data
    - Sorted Set index per user (score = sealed_at unix timestamp)
    - Optional TTL via lifecycle.expires_at
    - PubSub channel for skill trigger event broadcasting
    - Keyword search (same as LocalStorage); for vector search use QdrantStorage
"""
from __future__ import annotations

import builtins
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capsule_memory.exceptions import CapsuleNotFoundError, StorageError
from capsule_memory.models.capsule import (
    Capsule,
    CapsuleStatus,
    CapsuleType,
)
from capsule_memory.storage.base import BaseStorage

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


def _check_redis() -> None:
    """Raise StorageError if redis is not installed."""
    if not _REDIS_AVAILABLE:
        raise StorageError(
            "RedisStorage requires capsule-memory[redis] extras: "
            "pip install 'capsule-memory[redis]'"
        )


class RedisStorage(BaseStorage):
    """
    Redis-backed storage with sorted set indexing.

    Key schema:
        - capsule:{user_id}:{capsule_id} → Hash (capsule JSON stored in 'data' field)
        - capsule_idx:{user_id} → Sorted Set (member=capsule_id, score=sealed_at timestamp)
        - capsule:triggers:{user_id} → PubSub channel for skill trigger events

    Args:
        url: Redis connection URL. Defaults to "redis://localhost:6379".

    Raises:
        StorageError: If redis package is not installed.
    """

    def __init__(self, url: str = "redis://localhost:6379") -> None:
        _check_redis()
        self._url = url
        self._redis: aioredis.Redis = aioredis.from_url(url, decode_responses=True)
        # LocalStorage helper for file I/O (export/import)
        from capsule_memory.storage.local import LocalStorage

        _export_path = os.path.join(
            os.path.expanduser("~"), ".capsules", "_redis_export_tmp"
        )
        self._local_export_helper = LocalStorage(path=_export_path)

    def _capsule_key(self, user_id: str, capsule_id: str) -> str:
        """Build the Redis key for a capsule."""
        return f"capsule:{user_id}:{capsule_id}"

    def _index_key(self, user_id: str) -> str:
        """Build the Redis key for a user's capsule index."""
        return f"capsule_idx:{user_id}"

    def _meta_key(self, user_id: str, capsule_id: str) -> str:
        """Build the Redis key for capsule metadata."""
        return f"capsule_meta:{user_id}:{capsule_id}"

    async def save(self, capsule: Capsule) -> str:
        """
        Save or update a capsule in Redis.

        Args:
            capsule: The capsule to save.

        Returns:
            The capsule_id of the saved capsule.

        Raises:
            StorageError: If the Redis operation fails.
        """
        user_id = capsule.identity.user_id
        capsule_id = capsule.capsule_id
        key = self._capsule_key(user_id, capsule_id)

        try:
            capsule_json = capsule.to_json()
            meta = {
                "capsule_type": capsule.capsule_type.value,
                "status": capsule.lifecycle.status.value,
                "title": capsule.metadata.title,
                "tags": json.dumps(capsule.metadata.tags, ensure_ascii=False),
                "turn_count": str(capsule.metadata.turn_count),
            }

            pipe = self._redis.pipeline()
            pipe.set(key, capsule_json)
            pipe.hset(self._meta_key(user_id, capsule_id), mapping=meta)
            pipe.set(f"capsule_owner:{capsule_id}", user_id)

            # Index by sealed_at timestamp
            sealed_at = capsule.lifecycle.sealed_at
            score = sealed_at.timestamp() if sealed_at else 0.0
            pipe.zadd(self._index_key(user_id), {capsule_id: score})

            await pipe.execute()

            # Set TTL if expires_at is set
            if capsule.lifecycle.expires_at:
                ttl = int(
                    (capsule.lifecycle.expires_at - datetime.now(timezone.utc)).total_seconds()
                )
                if ttl > 0:
                    await self._redis.expire(key, ttl)

        except Exception as e:
            raise StorageError(f"Failed to save capsule {capsule_id}: {e}") from e

        logger.debug("Saved capsule %s to Redis", capsule_id)
        return capsule_id

    async def get(self, capsule_id: str) -> Capsule | None:
        """
        Get a capsule by ID (searches across all users).

        Uses a reverse index (capsule_owner:{capsule_id} → user_id) for O(1)
        lookup. Falls back to SCAN if the index entry is missing.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            The Capsule object, or None if not found.

        Raises:
            StorageError: If the Redis operation fails.
        """
        try:
            # O(1) reverse-index lookup
            owner = await self._redis.get(f"capsule_owner:{capsule_id}")
            if owner:
                user_id = owner if isinstance(owner, str) else owner.decode()
                result = await self._get_by_user(user_id, capsule_id)
                if result is not None:
                    return result

            # Fallback: SCAN (for capsules saved before reverse index existed)
            async for key in self._redis.scan_iter(f"capsule:*:{capsule_id}"):
                data = await self._redis.get(key)
                if data:
                    return Capsule.from_json(data)
            return None
        except Exception as e:
            raise StorageError(f"Failed to get capsule {capsule_id}: {e}") from e

    async def _get_by_user(self, user_id: str, capsule_id: str) -> Capsule | None:
        """Get a capsule by user_id and capsule_id (direct key lookup)."""
        key = self._capsule_key(user_id, capsule_id)
        data = await self._redis.get(key)
        if data is None:
            return None
        return Capsule.from_json(data)

    async def delete(self, capsule_id: str) -> bool:
        """
        Delete a capsule by ID.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            True if deleted, False if not found.

        Raises:
            StorageError: If the Redis operation fails.
        """
        try:
            async for key in self._redis.scan_iter(f"capsule:*:{capsule_id}"):
                # Extract user_id from key pattern capsule:{user_id}:{capsule_id}
                parts = key.split(":")
                if len(parts) >= 3:
                    user_id = parts[1]
                    pipe = self._redis.pipeline()
                    pipe.delete(key)
                    pipe.delete(self._meta_key(user_id, capsule_id))
                    pipe.delete(f"capsule_owner:{capsule_id}")
                    pipe.zrem(self._index_key(user_id), capsule_id)
                    await pipe.execute()
                    return True
            return False
        except Exception as e:
            raise StorageError(f"Failed to delete capsule {capsule_id}: {e}") from e

    async def list(
        self,
        user_id: str | None = None,
        capsule_type: CapsuleType | None = None,
        tags: builtins.list[str] | None = None,
        status: CapsuleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Capsule]:
        """
        List capsules with optional filtering.

        Args:
            user_id: Filter by user ID.
            capsule_type: Filter by capsule type.
            tags: Filter by tags.
            status: Filter by lifecycle status.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of matching Capsule objects.

        Raises:
            StorageError: If the Redis operation fails.
        """
        try:
            capsule_ids: builtins.list[tuple[str, str]] = []  # (user_id, capsule_id)

            if user_id:
                # Get from sorted set, reversed (newest first)
                members = await self._redis.zrevrange(
                    self._index_key(user_id), 0, -1
                )
                capsule_ids = [(user_id, m) for m in members]
            else:
                # Scan all index keys
                async for idx_key in self._redis.scan_iter("capsule_idx:*"):
                    uid = idx_key.split(":", 1)[1] if ":" in idx_key else ""
                    members = await self._redis.zrevrange(idx_key, 0, -1)
                    capsule_ids.extend((uid, m) for m in members)

            capsules: builtins.list[Capsule] = []
            for uid, cid in capsule_ids:
                capsule = await self._get_by_user(uid, cid)
                if capsule is None:
                    continue

                # Apply filters
                if capsule_type and capsule.capsule_type != capsule_type:
                    continue
                if status and capsule.lifecycle.status != status:
                    continue
                if tags and not all(t in capsule.metadata.tags for t in tags):
                    continue

                capsules.append(capsule)

            return capsules[offset : offset + limit]
        except Exception as e:
            raise StorageError(f"Failed to list capsules: {e}") from e

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> builtins.list[tuple[Capsule, float]]:
        """
        Keyword search (matches in title, tags, context_summary).

        For vector search, use QdrantStorage.

        Args:
            query: Search query text.
            user_id: Optional filter by user ID.
            top_k: Maximum number of results.

        Returns:
            List of (Capsule, score) tuples.
        """
        query_words = query.lower().split()
        all_capsules = await self.list(user_id=user_id, limit=500)
        scored: builtins.list[tuple[Capsule, float]] = []

        for c in all_capsules:
            text = " ".join(
                [
                    c.metadata.title.lower(),
                    " ".join(c.metadata.tags).lower(),
                    c.payload.get("context_summary", "").lower(),
                ]
            )
            matches = sum(1 for w in query_words if w in text)
            if matches > 0:
                score = matches / len(query_words) if query_words else 0.0
                scored.append((c, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def count(self, user_id: str | None = None) -> int:
        """
        Count capsules.

        Args:
            user_id: Optional filter by user ID.

        Returns:
            Number of capsules.

        Raises:
            StorageError: If the Redis operation fails.
        """
        try:
            if user_id:
                return int(await self._redis.zcard(self._index_key(user_id)))

            total = 0
            async for idx_key in self._redis.scan_iter("capsule_idx:*"):
                total += int(await self._redis.zcard(idx_key))
            return total
        except Exception as e:
            raise StorageError(f"Failed to count capsules: {e}") from e

    async def export_capsule(
        self,
        capsule_id: str,
        output_path: str,
        format: str = "json",
        encrypt: bool = False,
        passphrase: str = "",
    ) -> Path:
        """
        Export a capsule to file using LocalStorage helper.

        Args:
            capsule_id: ID of the capsule to export.
            output_path: Destination file path.
            format: Export format (json, msgpack, universal, prompt).
            encrypt: Whether to encrypt.
            passphrase: Encryption passphrase.

        Returns:
            Path to the exported file.

        Raises:
            CapsuleNotFoundError: If capsule doesn't exist.
        """
        capsule = await self.get(capsule_id)
        if capsule is None:
            raise CapsuleNotFoundError(capsule_id)

        await self._local_export_helper.save(capsule)
        return await self._local_export_helper.export_capsule(
            capsule_id, output_path, format, encrypt, passphrase
        )

    async def import_capsule_file(
        self,
        file_path: str,
        user_id: str,
        passphrase: str = "",
    ) -> Capsule:
        """
        Import a capsule from file into Redis.

        Args:
            file_path: Path to the import file.
            user_id: User ID to assign to the imported capsule.
            passphrase: Decryption passphrase.

        Returns:
            The imported Capsule object.

        Raises:
            StorageError: If import fails.
        """
        capsule = await self._local_export_helper.import_capsule_file(
            file_path, user_id, passphrase
        )
        await self.save(capsule)
        logger.info("Imported capsule %s for user %s into Redis", capsule.capsule_id, user_id)
        return capsule

    async def publish_trigger(self, user_id: str, event_data: dict[str, Any]) -> None:
        """
        Publish a skill trigger event to the PubSub channel.

        Args:
            user_id: Target user ID.
            event_data: Event data to publish.
        """
        channel = f"capsule:triggers:{user_id}"
        try:
            await self._redis.publish(channel, json.dumps(event_data, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to publish trigger event: %s", e)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
