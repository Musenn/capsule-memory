from __future__ import annotations
import asyncio
import builtins
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import aiofiles  # type: ignore[import-untyped]
import aiofiles.os  # type: ignore[import-untyped]
from capsule_memory.exceptions import CapsuleNotFoundError, StorageError, TransportError
from capsule_memory.models.capsule import (
    Capsule, CapsuleType, CapsuleStatus, CapsuleIdentity, CapsuleLifecycle, CapsuleMetadata,
)
from capsule_memory.storage.base import BaseStorage

logger = logging.getLogger(__name__)

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _validate_path_component(value: str, name: str) -> None:
    """Reject path-traversal characters in user_id / capsule_id."""
    if not value or not _SAFE_ID_RE.match(value):
        raise StorageError(f"Invalid {name}: must be alphanumeric/hyphen/underscore/dot")


class LocalStorage(BaseStorage):
    """
    File-system-based storage backend, zero external dependencies.
    Each capsule is stored as an individual file, with index.json for fast listing.
    search() uses keyword matching (SQLiteStorage provides vector search).
    """

    def __init__(
        self,
        path: str | Path = "~/.capsules",
        format: str = "json",
    ) -> None:
        self.root = Path(path).expanduser().resolve()
        self.format = format
        self._index_lock: asyncio.Lock = asyncio.Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "exports").mkdir(exist_ok=True)

    def _user_dir(self, user_id: str) -> Path:
        _validate_path_component(user_id, "user_id")
        d = self.root / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _capsule_path(self, user_id: str, capsule_id: str) -> Path:
        _validate_path_component(capsule_id, "capsule_id")
        ext = ".json" if self.format == "json" else ".capsule"
        return self._user_dir(user_id) / f"{capsule_id}{ext}"

    def _index_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "index.json"

    async def _read_index(self, user_id: str) -> dict[str, Any]:
        """Read user's index.json, return empty dict if not found."""
        p = self._index_path(user_id)
        try:
            async with aiofiles.open(p, "r", encoding="utf-8") as f:
                result: dict[str, Any] = json.loads(await f.read())
                return result
        except FileNotFoundError:
            return {}
        except Exception as e:
            raise StorageError(f"Failed to read index for {user_id}: {e}") from e

    async def _write_index(self, user_id: str, index: dict[str, Any]) -> None:
        """
        Atomically write index.json: write to temp file first, then rename.
        Uses asyncio.Lock for thread safety within the process.
        """
        p = self._index_path(user_id)
        tmp_p = p.with_suffix(".tmp")
        async with self._index_lock:
            async with aiofiles.open(tmp_p, "w", encoding="utf-8") as f:
                await f.write(json.dumps(index, ensure_ascii=False, indent=2, default=str))
            # Use os.replace instead of os.rename: on Windows, rename fails if target exists
            import os as _os
            _os.replace(tmp_p, p)

    def _index_entry(self, capsule: Capsule) -> dict[str, Any]:
        """Build an index entry from a Capsule (lightweight fields)."""
        return {
            "capsule_id": capsule.capsule_id,
            "type": capsule.capsule_type.value,
            "status": capsule.lifecycle.status.value,
            "title": capsule.metadata.title,
            "tags": capsule.metadata.tags,
            "sealed_at": (
                capsule.lifecycle.sealed_at.isoformat() if capsule.lifecycle.sealed_at else None
            ),
            "turn_count": capsule.metadata.turn_count,
        }

    async def save(self, capsule: Capsule) -> str:
        p = self._capsule_path(capsule.identity.user_id, capsule.capsule_id)
        tmp_p = p.with_suffix(".tmp")
        try:
            if self.format == "json":
                content = capsule.to_json()
                async with aiofiles.open(tmp_p, "w", encoding="utf-8") as f:
                    await f.write(content)
            else:
                content_bytes = capsule.to_msgpack()
                async with aiofiles.open(tmp_p, "wb") as f:
                    await f.write(content_bytes)
            # Use os.replace: on Windows, os.rename fails if target exists
            os.replace(tmp_p, p)
        except Exception as e:
            if tmp_p.exists():
                tmp_p.unlink(missing_ok=True)
            raise StorageError(f"Failed to save capsule {capsule.capsule_id}: {e}") from e

        index = await self._read_index(capsule.identity.user_id)
        index[capsule.capsule_id] = self._index_entry(capsule)
        await self._write_index(capsule.identity.user_id, index)
        logger.debug("Saved capsule %s", capsule.capsule_id)
        return capsule.capsule_id

    async def get(self, capsule_id: str) -> Capsule | None:
        for user_dir in self.root.iterdir():
            if not user_dir.is_dir() or user_dir.name == "exports":
                continue
            for ext in (".json", ".capsule"):
                p = user_dir / f"{capsule_id}{ext}"
                if p.exists():
                    try:
                        if ext == ".json":
                            async with aiofiles.open(p, "r", encoding="utf-8") as f:
                                return Capsule.from_json(await f.read())
                        else:
                            async with aiofiles.open(p, "rb") as f:
                                return Capsule.from_msgpack(await f.read())
                    except Exception as e:
                        raise StorageError(
                            f"Failed to read capsule {capsule_id}: {e}"
                        ) from e
        return None

    async def delete(self, capsule_id: str) -> bool:
        capsule = await self.get(capsule_id)
        if capsule is None:
            return False
        p = self._capsule_path(capsule.identity.user_id, capsule_id)
        try:
            await aiofiles.os.remove(p)
        except FileNotFoundError:
            return False
        index = await self._read_index(capsule.identity.user_id)
        index.pop(capsule_id, None)
        await self._write_index(capsule.identity.user_id, index)
        return True

    async def list(
        self,
        user_id: str | None = None,
        capsule_type: CapsuleType | None = None,
        tags: builtins.list[str] | None = None,
        status: CapsuleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Capsule]:
        results: builtins.list[dict[str, Any]] = []
        user_dirs = (
            [self.root / user_id] if user_id else
            [d for d in self.root.iterdir() if d.is_dir() and d.name != "exports"]
        )
        for ud in user_dirs:
            if not ud.exists():
                continue
            index = await self._read_index(ud.name)
            for entry in index.values():
                if capsule_type and entry["type"] != capsule_type.value:
                    continue
                if status and entry["status"] != status.value:
                    continue
                if tags and not all(t in entry.get("tags", []) for t in tags):
                    continue
                results.append(entry)

        results.sort(key=lambda e: e.get("sealed_at") or "", reverse=True)
        page = results[offset: offset + limit]

        capsules: builtins.list[Capsule] = []
        for entry in page:
            c = await self.get(entry["capsule_id"])
            if c is not None:
                capsules.append(c)
        return capsules

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> builtins.list[tuple[Capsule, float]]:
        """
        Keyword search (matches in title, tags, context_summary).
        Returns results sorted by match score = matched_words / query_words.
        SQLiteStorage provides actual vector search.
        """
        query_words = query.lower().split()
        all_capsules = await self.list(user_id=user_id, limit=500)
        scored: builtins.list[tuple[Capsule, float]] = []
        for c in all_capsules:
            # Build searchable text from all payload locations
            summary = c.payload.get("context_summary", "")
            if not summary and "memory" in c.payload:
                summary = c.payload["memory"].get("context_summary", "")
            fact_text = ""
            facts = c.payload.get("facts", [])
            if not facts and "memory" in c.payload:
                facts = c.payload["memory"].get("facts", [])
            for f in facts:
                if isinstance(f, dict):
                    fact_text += f" {f.get('key', '')} {f.get('value', '')}"
            text = " ".join([
                c.metadata.title.lower(),
                " ".join(c.metadata.tags).lower(),
                summary.lower(),
                fact_text.lower(),
            ])
            matches = sum(1 for w in query_words if w in text)
            if matches > 0:
                score = matches / len(query_words) if query_words else 0.0
                scored.append((c, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def count(self, user_id: str | None = None) -> int:
        user_dirs = (
            [self.root / user_id] if user_id else
            [d for d in self.root.iterdir() if d.is_dir() and d.name != "exports"]
        )
        total = 0
        for ud in user_dirs:
            if ud.exists():
                index = await self._read_index(ud.name)
                total += len(index)
        return total

    async def export_capsule(
        self,
        capsule_id: str,
        output_path: str,
        format: str = "json",
        encrypt: bool = False,
        passphrase: str = "",
    ) -> Path:
        """
        Export capsule file, supports four formats:
        - "json": Full capsule JSON (requires SDK to parse)
        - "msgpack": Compressed binary capsule (requires SDK to parse)
        - "universal": Universal memory JSON (readable by any platform)
        - "prompt": Plain text prompt snippet (can be directly pasted)

        If encrypt=True, uses Fernet encryption for json/msgpack formats (requires passphrase).
        """
        from capsule_memory.transport.crypto import CapsuleCrypto
        capsule = await self.get(capsule_id)
        if capsule is None:
            raise CapsuleNotFoundError(capsule_id)

        out_path = Path(output_path).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "universal":
            content = json.dumps(capsule.to_universal_memory(), ensure_ascii=False, indent=2)
            async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
                await f.write(content)
        elif format == "prompt":
            async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
                await f.write(capsule.to_prompt_snippet())
        elif format == "msgpack":
            data = capsule.to_msgpack()
            if encrypt:
                if not passphrase:
                    raise StorageError("passphrase is required when encrypt=True")
                capsule_enc = CapsuleCrypto.encrypt(capsule, passphrase)
                data = capsule_enc.to_msgpack()
            async with aiofiles.open(out_path, "wb") as f:
                await f.write(data)
        else:  # json (default)
            target = (
                CapsuleCrypto.encrypt(capsule, passphrase)
                if encrypt and passphrase else capsule
            )
            async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
                await f.write(target.to_json())

        logger.info("Exported capsule %s to %s (format=%s)", capsule_id, out_path, format)
        return out_path

    async def import_capsule_file(
        self,
        file_path: str,
        user_id: str,
        passphrase: str = "",
    ) -> Capsule:
        """
        Import capsule from file, auto-detect format:
        - .capsule extension -> MsgPack format
        - .json with "schema": "universal-memory/1.0" -> Universal format
        - .json with "capsule_id" -> Full capsule JSON
        - .txt extension -> Treat as prompt snippet, wrap as CONTEXT type capsule

        After import: identity.user_id updated, status set to IMPORTED.
        """
        from capsule_memory.transport.crypto import CapsuleCrypto
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            raise StorageError(f"File not found: {file_path}")

        try:
            if p.suffix == ".capsule":
                async with aiofiles.open(p, "rb") as f:
                    capsule = Capsule.from_msgpack(await f.read())
            elif p.suffix == ".txt":
                async with aiofiles.open(p, "r", encoding="utf-8") as f:
                    content = await f.read()
                capsule = Capsule(
                    capsule_type=CapsuleType.CONTEXT,
                    identity=CapsuleIdentity(
                        user_id=user_id, session_id=f"imported_{uuid4().hex[:8]}"
                    ),
                    lifecycle=CapsuleLifecycle(
                        status=CapsuleStatus.IMPORTED, sealed_at=datetime.now(timezone.utc)
                    ),
                    metadata=CapsuleMetadata(title=p.stem),
                    payload={"content": content},
                )
            else:  # .json
                async with aiofiles.open(p, "r", encoding="utf-8") as f:
                    raw = await f.read()
                data = json.loads(raw)
                if data.get("schema") == "universal-memory/1.0":
                    capsule = Capsule.from_universal_memory(data, user_id)
                else:
                    capsule = Capsule.from_json(raw)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise TransportError(f"Failed to parse import file {file_path}: {e}") from e

        if capsule.integrity.encrypted and passphrase:
            capsule = CapsuleCrypto.decrypt(capsule, passphrase)

        capsule.identity.user_id = user_id
        capsule.lifecycle.status = CapsuleStatus.IMPORTED
        capsule.integrity.checksum = capsule.compute_checksum()

        await self.save(capsule)
        logger.info("Imported capsule %s for user %s", capsule.capsule_id, user_id)
        return capsule
