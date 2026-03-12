"""
SQLiteStorage — Local vector search backend using sqlite-vec + sentence-transformers.

Requires: pip install 'capsule-memory[sqlite]'

Features:
    - 384-dim vector search via sqlite-vec extension
    - sentence-transformers (all-MiniLM-L6-v2) for embedding generation
    - Full BaseStorage implementation with SQL-backed CRUD
    - Export/Import via internal LocalStorage helper (Patch #5: isolated subdirectory)
"""
from __future__ import annotations

import asyncio
import builtins
import json
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
    import sqlite_vec
    import sqlite3

    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _SQLITE_VEC_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False


def _check_deps() -> None:
    """Raise StorageError if required extras are not installed."""
    if not _SQLITE_VEC_AVAILABLE or not _ST_AVAILABLE:
        raise StorageError(
            "SQLiteStorage requires capsule-memory[sqlite] extras: "
            "pip install 'capsule-memory[sqlite]'"
        )


class SQLiteStorage(BaseStorage):
    """
    SQLite-backed storage with sqlite-vec vector search.

    Architecture:
        - capsules table: stores serialized capsule JSON + metadata columns for fast filtering
        - capsule_vec virtual table: stores 384-dim embeddings for vector search
        - sentence-transformers (all-MiniLM-L6-v2) generates embeddings
        - LocalStorage helper for export/import file I/O (uses isolated _export_tmp subdirectory)

    Args:
        path: Directory for the SQLite database file. Defaults to "~/.capsules".
        model_name: sentence-transformers model name. Defaults to "all-MiniLM-L6-v2".

    Raises:
        StorageError: If sqlite-vec or sentence-transformers is not installed.
    """

    def __init__(
        self,
        path: str | Path = "~/.capsules",
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        _check_deps()

        self._root = Path(path).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._root / "capsule_memory.db"

        # Patch #5: LocalStorage helper uses isolated subdirectory to avoid
        # index.json conflicts with SQLite .db files.
        from capsule_memory.storage.local import LocalStorage

        _export_tmp_path = os.path.join(str(self._root), "_export_tmp")
        self._local_export_helper = LocalStorage(path=_export_tmp_path)

        # Load embedding model with progress indicator
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._model_lock = asyncio.Lock()

        # Initialize database schema
        self._init_db()

    def _init_db(self) -> None:
        """Create tables and load sqlite-vec extension."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS capsules (
                    capsule_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    capsule_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT,
                    tags TEXT,
                    sealed_at TEXT,
                    turn_count INTEGER,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_user_id ON capsules(user_id);
                CREATE INDEX IF NOT EXISTS idx_type ON capsules(capsule_type);
                """
            )
            # sqlite-vec virtual table for vector search
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS capsule_vec USING vec0(
                    capsule_id TEXT,
                    embedding float[384]
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
        logger.debug("SQLiteStorage initialized at %s", self._db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new SQLite connection with sqlite-vec loaded."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return conn

    async def _get_model(self) -> SentenceTransformer:
        """Lazy-load the sentence-transformers model with progress display."""
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            logger.info("Loading embedding model: %s", self._model_name)
            try:
                from rich.progress import Progress

                with Progress() as progress:
                    progress.add_task(
                        f"Loading embedding model ({self._model_name})...", total=None
                    )
                    self._model = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: SentenceTransformer(self._model_name)
                    )
            except ImportError:
                # rich not available, load without progress
                self._model = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: SentenceTransformer(self._model_name)
                )
            logger.info("Embedding model loaded: %s", self._model_name)
            return self._model

    def _encode_sync(self, model: SentenceTransformer, text: str) -> bytes:
        """Encode text to embedding bytes (384-dim float32)."""
        import struct

        embedding = model.encode(text, normalize_embeddings=True)
        return struct.pack(f"{len(embedding)}f", *embedding)

    async def _encode(self, text: str) -> bytes:
        """Encode text to embedding bytes asynchronously."""
        model = await self._get_model()
        return await asyncio.get_event_loop().run_in_executor(
            None, self._encode_sync, model, text
        )

    def _capsule_to_row(self, capsule: Capsule) -> dict[str, Any]:
        """Convert a Capsule to a dict suitable for SQL INSERT."""
        return {
            "capsule_id": capsule.capsule_id,
            "user_id": capsule.identity.user_id,
            "capsule_type": capsule.capsule_type.value,
            "status": capsule.lifecycle.status.value,
            "title": capsule.metadata.title,
            "tags": json.dumps(capsule.metadata.tags, ensure_ascii=False),
            "sealed_at": (
                capsule.lifecycle.sealed_at.isoformat()
                if capsule.lifecycle.sealed_at
                else None
            ),
            "turn_count": capsule.metadata.turn_count,
            "payload_json": capsule.to_json(),
        }

    def _row_to_capsule(self, row: sqlite3.Row) -> Capsule:
        """Reconstruct a Capsule from a database row."""
        return Capsule.from_json(row["payload_json"])

    def _get_searchable_text(self, capsule: Capsule) -> str:
        """Extract text content from a capsule for embedding generation."""
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
            parts.append(p.get("trigger_pattern", ""))
        elif capsule.capsule_type == CapsuleType.HYBRID:
            mem = p.get("memory", {})
            parts.append(mem.get("context_summary", ""))
            for f in mem.get("facts", []):
                parts.append(f"{f.get('key', '')} {f.get('value', '')}")
            for s in p.get("skills", []):
                parts.append(s.get("description", ""))
        elif capsule.capsule_type == CapsuleType.CONTEXT:
            parts.append(p.get("content", "")[:500])

        return " ".join(part for part in parts if part)

    async def save(self, capsule: Capsule) -> str:
        """
        Save or update a capsule in SQLite and update the vector index.

        Args:
            capsule: The capsule to save.

        Returns:
            The capsule_id of the saved capsule.

        Raises:
            StorageError: If the database operation fails.
        """
        row = self._capsule_to_row(capsule)
        searchable_text = self._get_searchable_text(capsule)

        try:
            embedding_bytes = await self._encode(searchable_text)
        except Exception as e:
            logger.warning("Failed to generate embedding, saving without vector: %s", e)
            embedding_bytes = None

        try:
            conn = self._get_conn()
            try:
                # Upsert capsule data
                conn.execute(
                    """
                    INSERT INTO capsules
                        (capsule_id, user_id, capsule_type, status, title, tags,
                         sealed_at, turn_count, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(capsule_id) DO UPDATE SET
                        user_id=excluded.user_id,
                        capsule_type=excluded.capsule_type,
                        status=excluded.status,
                        title=excluded.title,
                        tags=excluded.tags,
                        sealed_at=excluded.sealed_at,
                        turn_count=excluded.turn_count,
                        payload_json=excluded.payload_json
                    """,
                    (
                        row["capsule_id"],
                        row["user_id"],
                        row["capsule_type"],
                        row["status"],
                        row["title"],
                        row["tags"],
                        row["sealed_at"],
                        row["turn_count"],
                        row["payload_json"],
                    ),
                )

                # Update vector index
                if embedding_bytes is not None:
                    # Delete old vector entry if exists
                    conn.execute(
                        "DELETE FROM capsule_vec WHERE capsule_id = ?",
                        (capsule.capsule_id,),
                    )
                    conn.execute(
                        "INSERT INTO capsule_vec (capsule_id, embedding) VALUES (?, ?)",
                        (capsule.capsule_id, embedding_bytes),
                    )

                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            raise StorageError(f"Failed to save capsule {capsule.capsule_id}: {e}") from e

        logger.debug("Saved capsule %s to SQLite", capsule.capsule_id)
        return capsule.capsule_id

    async def get(self, capsule_id: str) -> Capsule | None:
        """
        Get a capsule by ID.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            The Capsule object, or None if not found.

        Raises:
            StorageError: If the database operation fails.
        """
        try:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT payload_json FROM capsules WHERE capsule_id = ?",
                    (capsule_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return Capsule.from_json(row["payload_json"])
            finally:
                conn.close()
        except Exception as e:
            if "no such" in str(e).lower():
                return None
            raise StorageError(f"Failed to get capsule {capsule_id}: {e}") from e

    async def delete(self, capsule_id: str) -> bool:
        """
        Delete a capsule by ID.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            True if the capsule was deleted, False if it didn't exist.

        Raises:
            StorageError: If the database operation fails.
        """
        try:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM capsules WHERE capsule_id = ?", (capsule_id,)
                )
                conn.execute(
                    "DELETE FROM capsule_vec WHERE capsule_id = ?", (capsule_id,)
                )
                conn.commit()
                deleted = cursor.rowcount > 0
            finally:
                conn.close()
            return deleted
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
        List capsules with optional filtering, sorted by sealed_at descending.

        Args:
            user_id: Filter by user ID.
            capsule_type: Filter by capsule type.
            tags: Filter by tags (all specified tags must be present).
            status: Filter by lifecycle status.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of matching Capsule objects.

        Raises:
            StorageError: If the database operation fails.
        """
        try:
            conn = self._get_conn()
            try:
                conditions: builtins.list[str] = []
                params: builtins.list[Any] = []

                if user_id is not None:
                    conditions.append("user_id = ?")
                    params.append(user_id)
                if capsule_type is not None:
                    conditions.append("capsule_type = ?")
                    params.append(capsule_type.value)
                if status is not None:
                    conditions.append("status = ?")
                    params.append(status.value)

                where_clause = ""
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)

                query = f"""
                    SELECT payload_json, tags FROM capsules
                    {where_clause}
                    ORDER BY sealed_at DESC NULLS LAST
                    LIMIT ? OFFSET ?
                """
                # When filtering by tags in Python, fetch more rows to compensate
                sql_limit = limit if not tags else limit * 10
                params.extend([sql_limit, offset])

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                capsules: builtins.list[Capsule] = []
                for row in rows:
                    # Filter by tags in Python (JSON array stored as string)
                    if tags:
                        row_tags = json.loads(row["tags"] or "[]")
                        if not all(t in row_tags for t in tags):
                            continue
                    capsules.append(Capsule.from_json(row["payload_json"]))
                    if len(capsules) >= limit:
                        break

                return capsules
            finally:
                conn.close()
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

        Uses sqlite-vec for approximate nearest neighbor search with cosine similarity.

        Args:
            query: Search query text.
            user_id: Optional filter by user ID.
            top_k: Maximum number of results to return.

        Returns:
            List of (Capsule, score) tuples, score range 0.0-1.0.

        Raises:
            StorageError: If the search operation fails.
        """
        try:
            query_embedding = await self._encode(query)
        except Exception as e:
            logger.warning("Embedding generation failed, falling back to keyword search: %s", e)
            return await self._keyword_search(query, user_id, top_k)

        try:
            conn = self._get_conn()
            try:
                if user_id:
                    cursor = conn.execute(
                        """
                        SELECT cv.capsule_id, cv.distance
                        FROM capsule_vec cv
                        JOIN capsules c ON cv.capsule_id = c.capsule_id
                        WHERE c.user_id = ?
                        AND cv.embedding MATCH ?
                        ORDER BY cv.distance
                        LIMIT ?
                        """,
                        (user_id, query_embedding, top_k),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT cv.capsule_id, cv.distance
                        FROM capsule_vec cv
                        WHERE cv.embedding MATCH ?
                        ORDER BY cv.distance
                        LIMIT ?
                        """,
                        (query_embedding, top_k),
                    )

                results: builtins.list[tuple[Capsule, float]] = []
                for row in cursor.fetchall():
                    capsule_id = row[0]
                    distance = row[1]
                    # Convert distance to similarity score (0-1 range)
                    score = max(0.0, min(1.0, 1.0 - distance))
                    capsule = await self.get(capsule_id)
                    if capsule is not None:
                        results.append((capsule, score))

                return results
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Vector search failed, falling back to keyword search: %s", e)
            return await self._keyword_search(query, user_id, top_k)

    async def _keyword_search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> builtins.list[tuple[Capsule, float]]:
        """
        Fallback keyword-based search when vector search is unavailable.

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
        Count capsules, optionally filtered by user ID.

        Args:
            user_id: Optional filter by user ID.

        Returns:
            Number of matching capsules.

        Raises:
            StorageError: If the database operation fails.
        """
        try:
            conn = self._get_conn()
            try:
                if user_id:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM capsules WHERE user_id = ?",
                        (user_id,),
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) FROM capsules")
                return int(cursor.fetchone()[0])
            finally:
                conn.close()
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
        Export a capsule to file using the LocalStorage helper.

        Patch #5: Uses _export_tmp subdirectory to avoid path conflicts with .db file.

        Args:
            capsule_id: ID of the capsule to export.
            output_path: Destination file path.
            format: Export format (json, msgpack, universal, prompt).
            encrypt: Whether to encrypt the output.
            passphrase: Encryption passphrase (required if encrypt=True).

        Returns:
            Path to the exported file.

        Raises:
            CapsuleNotFoundError: If the capsule doesn't exist.
            StorageError: If export fails.
        """
        capsule = await self.get(capsule_id)
        if capsule is None:
            raise CapsuleNotFoundError(capsule_id)

        # Save capsule to _export_tmp helper (for serialization logic reuse)
        await self._local_export_helper.save(capsule)

        # Export from helper to user-specified output path
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
        Import a capsule from file, auto-detect format.

        Uses LocalStorage helper for file parsing, then saves to SQLite.

        Args:
            file_path: Path to the import file.
            user_id: User ID to assign to the imported capsule.
            passphrase: Decryption passphrase (if encrypted).

        Returns:
            The imported Capsule object.

        Raises:
            StorageError: If import fails.
            TransportError: If the file format is invalid.
        """
        # Use LocalStorage helper to parse the file
        capsule = await self._local_export_helper.import_capsule_file(
            file_path, user_id, passphrase
        )

        # Save to SQLite (the helper already saved to its own storage,
        # but we need it in SQLite too)
        await self.save(capsule)
        logger.info("Imported capsule %s for user %s into SQLite", capsule.capsule_id, user_id)
        return capsule
