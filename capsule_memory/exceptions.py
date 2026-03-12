from __future__ import annotations


class CapsuleError(Exception):
    """All CapsuleMemory exceptions inherit from this base class."""


class CapsuleNotFoundError(CapsuleError):
    """Raised when a capsule with the given ID is not found."""

    def __init__(self, capsule_id: str) -> None:
        super().__init__(f"Capsule not found: {capsule_id}")
        self.capsule_id = capsule_id


class CapsuleIntegrityError(CapsuleError):
    """Raised when capsule integrity check fails (checksum mismatch or decryption failure)."""


class StorageError(CapsuleError):
    """Raised when storage read/write operations fail."""


class ExtractorError(CapsuleError):
    """Raised when LLM memory extraction fails."""


class AdapterError(CapsuleError):
    """Raised when an AI framework adapter fails to parse a response."""


class TransportError(CapsuleError):
    """Raised when capsule serialization/deserialization fails."""


class SessionError(CapsuleError):
    """Raised on session state errors (e.g. ingesting into a sealed session)."""


class SkillDetectorError(CapsuleError):
    """Raised when skill detection encounters an unrecoverable error."""
