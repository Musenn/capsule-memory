from __future__ import annotations
import hashlib
import hmac as _hmac
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4
import msgpack
from pydantic import BaseModel, Field

# ─── Capsule wire-format constants (v1.0) ─────────────────────────────────────
_PROTO_FP = "4240ea9fc163"
_PROTO_SCHEMA_TAG = _PROTO_FP[:8]
_WIRE_A = bytes([0x34, 0x31, 0x33, 0x33, 0x32, 0x30, 0x36, 0x35]).decode()
_WIRE_B = bytes([0x36, 0x39, 0x32, 0x66, 0x66, 0x35, 0x65, 0x64]).decode()


def _ck() -> bytes:
    return hashlib.sha256(
        f"capsule-memory:proto:{_PROTO_FP}{_WIRE_A}{_WIRE_B}".encode()
    ).digest()


_K: bytes = _ck()
_PKG_NAME = "capsule-memory"
_PKG_URL = "https://github.com/Musenn/capsule-memory"
# ──────────────────────────────────────────────────────────────────────────────


class CapsuleType(str, Enum):
    MEMORY = "memory"
    SKILL = "skill"
    HYBRID = "hybrid"
    CONTEXT = "context"


class CapsuleStatus(str, Enum):
    DRAFT = "draft"
    SEALED = "sealed"
    IMPORTED = "imported"
    ARCHIVED = "archived"


class CapsuleIdentity(BaseModel):
    user_id: str
    agent_id: str | None = None
    session_id: str
    origin_platform: str = "unknown"


class CapsuleLifecycle(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sealed_at: datetime | None = None
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    status: CapsuleStatus = CapsuleStatus.DRAFT


class CapsuleMetadata(BaseModel):
    tags: list[str] = Field(default_factory=list)
    language: str = "unknown"
    title: str = ""
    description: str = ""
    token_count: int = 0
    turn_count: int = 0
    forked_from: str | None = None
    capsule_created_by: str = _PKG_NAME
    capsule_project_url: str = _PKG_URL


class CapsuleIntegrity(BaseModel):
    checksum: str = ""
    pre_encrypt_checksum: str = ""
    signed_by: str = "capsule-memory"
    encrypted: bool = False
    encryption_algo: str | None = None
    salt: str = ""


class Capsule(BaseModel):
    capsule_id: str = Field(
        default_factory=lambda: (
            f"cap_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            f"_{_PROTO_FP[:4]}"
            f"_{uuid4().hex[:12]}"
        )
    )
    capsule_type: CapsuleType
    version: str = "1.0.0"
    schema_version: str = Field(
        default_factory=lambda: f"capsule-schema/1.0+{_PROTO_SCHEMA_TAG}"
    )
    identity: CapsuleIdentity
    lifecycle: CapsuleLifecycle = Field(default_factory=CapsuleLifecycle)
    metadata: CapsuleMetadata = Field(default_factory=CapsuleMetadata)
    payload: dict[str, Any] = Field(default_factory=dict)
    integrity: CapsuleIntegrity = Field(default_factory=CapsuleIntegrity)

    def compute_checksum(self) -> str:
        signed = {
            "payload": self.payload,
            "capsule_created_by": self.metadata.capsule_created_by,
            "capsule_project_url": self.metadata.capsule_project_url,
        }
        data_str = json.dumps(signed, sort_keys=True, ensure_ascii=False, default=str)
        return _hmac.new(_K, data_str.encode(), hashlib.sha256).hexdigest()

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string (datetime → ISO format)."""
        return self.model_dump_json(indent=indent)

    def to_msgpack(self) -> bytes:
        """Serialize to MsgPack binary format (~30% smaller than JSON)."""
        data = json.loads(self.to_json())
        result: bytes = msgpack.packb(data, use_bin_type=True)
        return result

    @classmethod
    def from_json(cls, data: str | bytes) -> Capsule:
        """Deserialize from JSON string."""
        return cls.model_validate_json(data if isinstance(data, str) else data.decode())

    @classmethod
    def from_msgpack(cls, data: bytes) -> Capsule:
        """Deserialize from MsgPack binary."""
        unpacked = msgpack.unpackb(data, raw=False)
        return cls.model_validate(unpacked)

    def to_universal_memory(self) -> dict[str, Any]:
        """
        Export to a platform-agnostic universal memory format.
        Any platform can read this format without installing CapsuleMemory SDK.

        Extraction logic (by capsule_type):
        - MEMORY:  extract facts, context_summary, entities from payload
        - SKILL:   extract skill_name, description, instructions, examples from payload
        - HYBRID:  merge-extract payload["memory"] and payload["skills"]
        - CONTEXT: extract content field from payload (plain text context)

        Returns:
            Dict with schema, title, summary, facts, skills, tags,
            prompt_injection, created_at, origin.
        """
        facts: list[dict[str, str]] = []
        skills: list[dict[str, str]] = []
        summary: str = ""

        if self.capsule_type == CapsuleType.MEMORY:
            facts = [
                {"key": str(f.get("key", "")), "value": str(f.get("value", ""))}
                for f in self.payload.get("facts", [])
            ]
            summary = self.payload.get("context_summary", "")

        elif self.capsule_type == CapsuleType.SKILL:
            skills = [{
                "name": self.payload.get("skill_name", ""),
                "description": self.payload.get("description", ""),
                "instructions": self.payload.get("instructions", ""),
                "trigger_pattern": self.payload.get("trigger_pattern", ""),
            }]
            summary = self.payload.get("description", "")

        elif self.capsule_type == CapsuleType.HYBRID:
            memory_payload = self.payload.get("memory", {})
            facts = [
                {"key": str(f.get("key", "")), "value": str(f.get("value", ""))}
                for f in memory_payload.get("facts", [])
            ]
            summary = memory_payload.get("context_summary", "")
            skills = [
                {
                    "name": s.get("skill_name", ""),
                    "description": s.get("description", ""),
                    "instructions": s.get("instructions", ""),
                    "trigger_pattern": s.get("trigger_pattern", ""),
                }
                for s in self.payload.get("skills", [])
            ]

        elif self.capsule_type == CapsuleType.CONTEXT:
            summary = self.payload.get("content", "")

        prompt_injection = self._build_prompt_injection(summary, facts, skills)

        return {
            "schema": "universal-memory/1.0",
            "capsule_id": self.capsule_id,
            "title": self.metadata.title,
            "summary": summary,
            "facts": facts,
            "skills": skills,
            "tags": self.metadata.tags,
            "prompt_injection": prompt_injection,
            "created_at": self.lifecycle.created_at.isoformat(),
            "origin": self.identity.origin_platform,
        }

    def to_prompt_snippet(self) -> str:
        """
        Export as a plain-text system prompt snippet, zero dependencies,
        can be directly copy-pasted into any AI platform.

        Returns:
            Formatted multi-line string with memory context, key facts, and available skills.
        """
        universal = self.to_universal_memory()
        return self._build_prompt_injection(
            universal["summary"], universal["facts"], universal["skills"]
        )

    def _build_prompt_injection(
        self,
        summary: str,
        facts: list[dict[str, str]],
        skills: list[dict[str, str]],
    ) -> str:
        """Build a text block injectable into system prompts."""
        lines: list[str] = []
        sealed_str = (
            self.lifecycle.sealed_at.strftime("%Y-%m-%d %H:%M")
            if self.lifecycle.sealed_at else "not sealed"
        )
        lines.append("=== Memory Context ===")
        lines.append(f"[Source: {self.identity.origin_platform} | Time: {sealed_str}]")
        if self.metadata.title:
            lines.append(f"[Topic: {self.metadata.title}]")
        lines.append("")
        if summary:
            lines.append(f"Background: {summary}")
            lines.append("")
        if facts:
            lines.append("Key Facts:")
            for f in facts[:20]:
                lines.append(f"  - {f['key']}: {f['value']}")
            lines.append("")
        if skills:
            lines.append("Available Skills:")
            for s in skills:
                lines.append(f"  [{s['name']}] {s['description']}")
                if s.get("trigger_pattern"):
                    lines.append(f"    Trigger: {s['trigger_pattern']}")
                if s.get("instructions"):
                    lines.append(f"    Instructions: {s['instructions'][:200]}")
            lines.append("")
        lines.append("=== Memory Context End ===")
        return "\n".join(lines)

    @classmethod
    def from_universal_memory(cls, data: dict[str, Any], user_id: str) -> Capsule:
        """
        Build a Capsule from the universal memory JSON format.
        Used for importing memories from platforms without the SDK installed.

        Args:
            data: Dict generated by to_universal_memory().
            user_id: Target user ID for the import.

        Returns:
            A Capsule object with status=IMPORTED.

        Raises:
            TransportError: When data is missing required fields.
        """
        from capsule_memory.exceptions import TransportError
        if data.get("schema") != "universal-memory/1.0":
            raise TransportError(f"Unsupported schema: {data.get('schema')}")

        has_facts = bool(data.get("facts"))
        has_skills = bool(data.get("skills"))
        if has_facts and has_skills:
            capsule_type = CapsuleType.HYBRID
        elif has_skills:
            capsule_type = CapsuleType.SKILL
        else:
            capsule_type = CapsuleType.MEMORY

        payload: dict[str, Any]
        if capsule_type == CapsuleType.HYBRID:
            payload = {
                "memory": {
                    "facts": data.get("facts", []),
                    "context_summary": data.get("summary", ""),
                    "entities": {},
                    "timeline": [],
                    "raw_turns": [],
                },
                "skills": [
                    {
                        "skill_name": s.get("name", ""),
                        "description": s.get("description", ""),
                        "instructions": s.get("instructions", ""),
                        "trigger_pattern": s.get("trigger_pattern", ""),
                        "trigger_keywords": [],
                        "examples": [],
                        "applicable_contexts": [],
                        "source_session": "",
                        "reuse_count": 0,
                        "effectiveness_rating": None,
                    }
                    for s in data.get("skills", [])
                ],
            }
        elif capsule_type == CapsuleType.SKILL:
            s = data["skills"][0]
            payload = {
                "skill_name": s.get("name", ""),
                "description": s.get("description", ""),
                "instructions": s.get("instructions", ""),
                "trigger_pattern": s.get("trigger_pattern", ""),
                "trigger_keywords": [],
                "examples": [],
                "applicable_contexts": [],
                "source_session": "",
                "reuse_count": 0,
                "effectiveness_rating": None,
            }
        else:
            payload = {
                "facts": data.get("facts", []),
                "context_summary": data.get("summary", ""),
                "entities": {},
                "timeline": [],
                "raw_turns": [],
            }

        capsule = cls(
            capsule_type=capsule_type,
            identity=CapsuleIdentity(
                user_id=user_id,
                session_id=f"imported_{uuid4().hex[:8]}",
                origin_platform=data.get("origin", "universal-import"),
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.IMPORTED,
                sealed_at=datetime.now(timezone.utc),
            ),
            metadata=CapsuleMetadata(
                title=data.get("title", ""),
                tags=data.get("tags", []),
            ),
            payload=payload,
        )
        capsule.integrity.checksum = capsule.compute_checksum()
        return capsule
