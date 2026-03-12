from __future__ import annotations
import builtins
from abc import ABC, abstractmethod
from pathlib import Path
from capsule_memory.models.capsule import Capsule, CapsuleType, CapsuleStatus


class BaseStorage(ABC):
    """Abstract base class for all storage backends. All methods are async."""

    @abstractmethod
    async def save(self, capsule: Capsule) -> str:
        """Save or update a capsule, return capsule_id."""

    @abstractmethod
    async def get(self, capsule_id: str) -> Capsule | None:
        """Get capsule by ID, return None if not found."""

    @abstractmethod
    async def delete(self, capsule_id: str) -> bool:
        """Delete a capsule, return whether deletion was successful."""

    @abstractmethod
    async def list(
        self,
        user_id: str | None = None,
        capsule_type: CapsuleType | None = None,
        tags: builtins.list[str] | None = None,
        status: CapsuleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Capsule]:
        """List capsules by criteria, supports pagination."""

    @abstractmethod
    async def search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> builtins.list[tuple[Capsule, float]]:
        """Semantic/keyword search, return (capsule, score) list, score range 0.0-1.0."""

    @abstractmethod
    async def count(self, user_id: str | None = None) -> int:
        """Count capsules."""

    async def exists(self, capsule_id: str) -> bool:
        """Check if a capsule exists (default: via get)."""
        return await self.get(capsule_id) is not None

    @abstractmethod
    async def export_capsule(
        self,
        capsule_id: str,
        output_path: str,
        format: str = "json",
        encrypt: bool = False,
        passphrase: str = "",
    ) -> Path:
        """Export capsule to file, format: json | msgpack | universal | prompt."""

    @abstractmethod
    async def import_capsule_file(
        self,
        file_path: str,
        user_id: str,
        passphrase: str = "",
    ) -> Capsule:
        """Import capsule from file, auto-detect format and convert."""
