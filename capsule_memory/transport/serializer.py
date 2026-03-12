from __future__ import annotations
import json
import logging
from pathlib import Path
from capsule_memory.exceptions import TransportError
from capsule_memory.models.capsule import Capsule

logger = logging.getLogger(__name__)


class CapsuleSerializer:
    """Utility class for capsule serialization and deserialization."""

    @staticmethod
    def to_json(capsule: Capsule, indent: int = 2) -> str:
        """Serialize capsule to JSON string."""
        return capsule.to_json(indent=indent)

    @staticmethod
    def from_json(data: str | bytes) -> Capsule:
        """Deserialize capsule from JSON string."""
        try:
            return Capsule.from_json(data)
        except Exception as e:
            raise TransportError(f"JSON deserialization failed: {e}") from e

    @staticmethod
    def to_msgpack(capsule: Capsule) -> bytes:
        """Serialize capsule to MsgPack binary."""
        return capsule.to_msgpack()

    @staticmethod
    def from_msgpack(data: bytes) -> Capsule:
        """Deserialize capsule from MsgPack binary."""
        try:
            return Capsule.from_msgpack(data)
        except Exception as e:
            raise TransportError(f"MsgPack deserialization failed: {e}") from e

    @staticmethod
    def detect_format(file_path: str | Path) -> str:
        """
        Detect capsule file format by extension and content.

        Returns:
            One of: "json", "msgpack", "universal", "prompt"
        """
        p = Path(file_path)
        if p.suffix == ".capsule":
            return "msgpack"
        elif p.suffix == ".txt":
            return "prompt"
        elif p.suffix == ".json":
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.loads(f.read())
                if data.get("schema") == "universal-memory/1.0":
                    return "universal"
            except (json.JSONDecodeError, KeyError):
                pass
            return "json"
        return "json"
