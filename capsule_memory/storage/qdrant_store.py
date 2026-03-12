"""
QdrantStorage — Qdrant-backed storage with vector search for CapsuleMemory.

Requires: pip install 'capsule-memory[qdrant]'

Features:
    - Per-user collections for data isolation
    - 384-dim vector search via sentence-transformers (all-MiniLM-L6-v2)
    - Full BaseStorage implementation with Qdrant as primary store
    - Export/Import via internal LocalStorage helper
"""
from __future__ import annotations

import asyncio
import builtins
import logging
import os
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
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False


def _check_qdrant() -> None:
    """Raise StorageError if required packages are not installed."""
    if not _QDRANT_AVAILABLE:
        raise StorageError(
            "QdrantStorage requires capsule-memory[qdrant] extras: "
            "pip install 'capsule-memory[qdrant]'"
        )


class QdrantStorage(BaseStorage):
    """
    Qdrant-backed storage with vector search capabilities.

    Architecture:
        - One collection per user: {collection_prefix}_{user_id}
        - Point ID = capsule_id (stored as UUID-derived numeric hash)
        - Payload stores full capsule JSON + metadata fields
        - sentence-transformers generates 384-dim embeddings for search

    Args:
        url: Qdrant server URL. Defaults to "http://localhost:6333".
        collection_prefix: Prefix for collection names. Defaults to "capsule".
        model_name: sentence-transformers model name. Defaults to "all-MiniLM-L6-v2".

    Raises:
        StorageError: If qdrant-client is not installed.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection_prefix: str = "capsule",
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        _check_qdrant()
        self._url = url
        self._collection_prefix = collection_prefix
        self._client = QdrantClient(url=url)
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._model_lock = asyncio.Lock()
        self._known_collections: set[str] = set()

        # LocalStorage helper for file I/O
        from capsule_memory.storage.local import LocalStorage

        _export_path = os.path.join(
            os.path.expanduser("~"), ".capsules", "_qdrant_export_tmp"
        )
        self._local_export_helper = LocalStorage(path=_export_path)

    def _collection_name(self, user_id: str) -> str:
        """Build the Qdrant collection name for a user."""
        safe_id = user_id.replace("-", "_").replace(".", "_")
        return f"{self._collection_prefix}_{safe_id}"

    def _point_id(self, capsule_id: str) -> str:
        """Convert capsule_id to a Qdrant point ID string."""
        return capsule_id

    async def _ensure_collection(self, user_id: str) -> str:
        """Create the collection if it doesn't exist."""
        name = self._collection_name(user_id)
        if name in self._known_collections:
            return name

        try:
            collections = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_collections
            )
            existing = {c.name for c in collections.collections}
            if name not in existing:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                    ),
                )
                logger.info("Created Qdrant collection: %s", name)
            self._known_collections.add(name)
        except Exception as e:
            raise StorageError(f"Failed to ensure collection {name}: {e}") from e

        return name

    async def _get_model(self) -> SentenceTransformer | None:
        """Lazy-load the embedding model."""
        if not _ST_AVAILABLE:
            return None
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            self._model = await asyncio.get_event_loop().run_in_executor(
                None, lambda: SentenceTransformer(self._model_name)
            )
            logger.info("Loaded embedding model: %s", self._model_name)
            return self._model

    async def _encode(self, text: str) -> builtins.list[float]:
        """Encode text to embedding vector."""
        model = await self._get_model()
        if model is None:
            return [0.0] * 384
        _text = text
        _model = model
        embedding = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _model.encode(_text, normalize_embeddings=True)
        )
        result: builtins.list[float] = embedding.tolist()
        return result

    def _get_searchable_text(self, capsule: Capsule) -> str:
        """Extract text for embedding generation."""
        parts: list[str] = [capsule.metadata.title]
        parts.extend(capsule.metadata.tags)

        p = capsule.payload
        if capsule.capsule_type == CapsuleType.MEMORY:
            parts.append(p.get("context_summary", ""))
            for f in p.get("facts", []):
                parts.append(f"{f.get('key', '')} {f.get('value', '')}")
        elif capsule.capsule_type == CapsuleType.SKILL:
            parts.append(p.get("description", ""))
            parts.append(p.get("instructions", ""))
        elif capsule.capsule_type == CapsuleType.HYBRID:
            mem = p.get("memory", {})
            parts.append(mem.get("context_summary", ""))
            for s in p.get("skills", []):
                parts.append(s.get("description", ""))
        elif capsule.capsule_type == CapsuleType.CONTEXT:
            parts.append(p.get("content", "")[:500])

        return " ".join(part for part in parts if part)

    async def save(self, capsule: Capsule) -> str:
        """
        Save or update a capsule in Qdrant.

        Args:
            capsule: The capsule to save.

        Returns:
            The capsule_id of the saved capsule.

        Raises:
            StorageError: If the Qdrant operation fails.
        """
        user_id = capsule.identity.user_id
        collection = await self._ensure_collection(user_id)
        searchable_text = self._get_searchable_text(capsule)

        try:
            embedding = await self._encode(searchable_text)
            capsule_json = capsule.to_json()

            point = PointStruct(
                id=self._point_id(capsule.capsule_id),
                vector=embedding,
                payload={
                    "capsule_id": capsule.capsule_id,
                    "user_id": user_id,
                    "capsule_type": capsule.capsule_type.value,
                    "status": capsule.lifecycle.status.value,
                    "title": capsule.metadata.title,
                    "tags": capsule.metadata.tags,
                    "sealed_at": (
                        capsule.lifecycle.sealed_at.isoformat()
                        if capsule.lifecycle.sealed_at
                        else None
                    ),
                    "turn_count": capsule.metadata.turn_count,
                    "capsule_json": capsule_json,
                },
            )

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.upsert(
                    collection_name=collection, points=[point]
                ),
            )
        except Exception as e:
            raise StorageError(f"Failed to save capsule {capsule.capsule_id}: {e}") from e

        logger.debug("Saved capsule %s to Qdrant", capsule.capsule_id)
        return capsule.capsule_id

    async def get(self, capsule_id: str) -> Capsule | None:
        """
        Get a capsule by ID (searches across all user collections).

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            The Capsule object, or None if not found.

        Raises:
            StorageError: If the Qdrant operation fails.
        """
        try:
            collections = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_collections
            )
            for col in collections.collections:
                if not col.name.startswith(self._collection_prefix):
                    continue
                try:
                    _col_name = col.name
                    _cap_id = capsule_id

                    def _retrieve_fn(_cn: str = _col_name, _cid: str = _cap_id) -> Any:
                        return self._client.retrieve(
                            collection_name=_cn,
                            ids=[self._point_id(_cid)],
                            with_payload=True,
                        )

                    points = await asyncio.get_event_loop().run_in_executor(
                        None, _retrieve_fn,
                    )
                    if points:
                        capsule_json = points[0].payload.get("capsule_json", "")
                        if capsule_json:
                            return Capsule.from_json(capsule_json)
                except Exception as e:
                    logger.debug("Skipping collection %s for capsule %s: %s", col.name, capsule_id, e)
                    continue
            return None
        except Exception as e:
            raise StorageError(f"Failed to get capsule {capsule_id}: {e}") from e

    async def delete(self, capsule_id: str) -> bool:
        """
        Delete a capsule by ID.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            True if deleted, False if not found.

        Raises:
            StorageError: If the Qdrant operation fails.
        """
        capsule = await self.get(capsule_id)
        if capsule is None:
            return False

        collection = self._collection_name(capsule.identity.user_id)
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.delete(
                    collection_name=collection,
                    points_selector=[self._point_id(capsule_id)],
                ),
            )
            return True
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
            StorageError: If the Qdrant operation fails.
        """
        try:
            collections_to_search: builtins.list[str] = []
            if user_id:
                col = await self._ensure_collection(user_id)
                collections_to_search = [col]
            else:
                cols = await asyncio.get_event_loop().run_in_executor(
                    None, self._client.get_collections
                )
                collections_to_search = [
                    c.name
                    for c in cols.collections
                    if c.name.startswith(self._collection_prefix)
                ]

            all_capsules: builtins.list[Capsule] = []
            for collection in collections_to_search:
                try:
                    # Build filter conditions
                    conditions: builtins.list[Any] = []
                    if capsule_type:
                        conditions.append(
                            FieldCondition(
                                key="capsule_type",
                                match=MatchValue(value=capsule_type.value),
                            )
                        )
                    if status:
                        conditions.append(
                            FieldCondition(
                                key="status",
                                match=MatchValue(value=status.value),
                            )
                        )

                    scroll_filter = Filter(must=conditions) if conditions else None

                    _sc = collection
                    _sf = scroll_filter
                    _sl = limit + offset

                    def _scroll_fn(_cn: str = _sc, _flt: Any = _sf, _lim: int = _sl) -> Any:
                        return self._client.scroll(
                            collection_name=_cn,
                            scroll_filter=_flt,
                            limit=_lim,
                            with_payload=True,
                        )

                    points, _ = await asyncio.get_event_loop().run_in_executor(
                        None, _scroll_fn,
                    )

                    for point in points:
                        capsule_json = point.payload.get("capsule_json", "")
                        if not capsule_json:
                            continue
                        capsule = Capsule.from_json(capsule_json)

                        # Tag filtering in Python
                        if tags and not all(t in capsule.metadata.tags for t in tags):
                            continue

                        all_capsules.append(capsule)
                except Exception as e:
                    logger.warning("Error scrolling collection %s: %s", collection, e)

            # Sort by sealed_at descending
            all_capsules.sort(
                key=lambda c: (
                    c.lifecycle.sealed_at.isoformat() if c.lifecycle.sealed_at else ""
                ),
                reverse=True,
            )
            return all_capsules[offset : offset + limit]
        except Exception as e:
            raise StorageError(f"Failed to list capsules: {e}") from e

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> builtins.list[tuple[Capsule, float]]:
        """
        Vector search for capsules matching the query.

        Args:
            query: Search query text.
            user_id: Optional filter by user ID.
            top_k: Maximum number of results.

        Returns:
            List of (Capsule, score) tuples, score 0.0-1.0.

        Raises:
            StorageError: If the search operation fails.
        """
        try:
            query_embedding = await self._encode(query)
        except Exception as e:
            logger.warning("Embedding failed, falling back to keyword search: %s", e)
            return await self._keyword_search(query, user_id, top_k)

        try:
            collections_to_search: builtins.list[str] = []
            if user_id:
                col = await self._ensure_collection(user_id)
                collections_to_search = [col]
            else:
                cols = await asyncio.get_event_loop().run_in_executor(
                    None, self._client.get_collections
                )
                collections_to_search = [
                    c.name
                    for c in cols.collections
                    if c.name.startswith(self._collection_prefix)
                ]

            results: builtins.list[tuple[Capsule, float]] = []
            for collection in collections_to_search:
                try:
                    _search_col = collection
                    _search_vec = query_embedding
                    _search_k = top_k

                    def _search_fn(_cn: str = _search_col, _qv: builtins.list[float] = _search_vec, _tk: int = _search_k) -> Any:
                        return self._client.query_points(
                            collection_name=_cn,
                            query=_qv,
                            limit=_tk,
                            with_payload=True,
                        )

                    query_response = await asyncio.get_event_loop().run_in_executor(
                        None, _search_fn,
                    )
                    for hit in query_response.points:
                        capsule_json = hit.payload.get("capsule_json", "")
                        if capsule_json:
                            capsule = Capsule.from_json(capsule_json)
                            score = max(0.0, min(1.0, hit.score))
                            results.append((capsule, score))
                except Exception as e:
                    logger.warning("Error searching collection %s: %s", collection, e)

            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
        except Exception as e:
            logger.warning("Vector search failed, falling back to keyword: %s", e)
            return await self._keyword_search(query, user_id, top_k)

    async def _keyword_search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> builtins.list[tuple[Capsule, float]]:
        """Fallback keyword search."""
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
            StorageError: If the Qdrant operation fails.
        """
        try:
            if user_id:
                col = self._collection_name(user_id)
                try:
                    info = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._client.get_collection(col),
                    )
                    return int(info.points_count or 0)
                except Exception as e:
                    logger.debug("Collection %s not accessible: %s", col, e)
                    return 0

            total = 0
            cols = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_collections
            )
            for col_desc in cols.collections:
                if col_desc.name.startswith(self._collection_prefix):
                    try:
                        _cname = col_desc.name

                        def _get_col_fn(_cn: str = _cname) -> Any:
                            return self._client.get_collection(_cn)

                        info = await asyncio.get_event_loop().run_in_executor(
                            None, _get_col_fn,
                        )
                        total += int(info.points_count or 0)
                    except Exception as e:
                        logger.debug("Skipping collection %s in count: %s", col_desc.name, e)
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
        Export a capsule to file.

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
        Import a capsule from file into Qdrant.

        Args:
            file_path: Path to the import file.
            user_id: User ID for the imported capsule.
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
        logger.info("Imported capsule %s for user %s into Qdrant", capsule.capsule_id, user_id)
        return capsule
