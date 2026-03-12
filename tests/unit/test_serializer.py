"""Tests for capsule_memory/transport/serializer.py"""
from __future__ import annotations

import json
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import pytest
from pathlib import Path

from capsule_memory.transport.serializer import CapsuleSerializer
from capsule_memory.models.capsule import (
    Capsule, CapsuleType, CapsuleIdentity, CapsuleLifecycle, CapsuleMetadata,
)
from capsule_memory.exceptions import TransportError


@pytest.fixture
def sample_capsule() -> Capsule:
    return Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(
            user_id="test_user",
            session_id="sess_test123",
            origin_platform="test",
        ),
        lifecycle=CapsuleLifecycle(),
        metadata=CapsuleMetadata(title="Test Capsule", tags=["test"]),
        payload={"facts": [], "context_summary": "test summary"},
    )


# ── JSON round-trip ──────────────────────────────────────────────────────────

class TestJsonSerialization:
    def test_to_json_returns_string(self, sample_capsule: Capsule) -> None:
        result = CapsuleSerializer.to_json(sample_capsule)
        assert isinstance(result, str)
        data = json.loads(result)
        assert data["capsule_type"] == "memory"

    def test_from_json_returns_capsule(self, sample_capsule: Capsule) -> None:
        json_str = CapsuleSerializer.to_json(sample_capsule)
        restored = CapsuleSerializer.from_json(json_str)
        assert isinstance(restored, Capsule)
        assert restored.capsule_type == CapsuleType.MEMORY
        assert restored.identity.user_id == "test_user"

    def test_from_json_bytes(self, sample_capsule: Capsule) -> None:
        json_bytes = CapsuleSerializer.to_json(sample_capsule).encode("utf-8")
        restored = CapsuleSerializer.from_json(json_bytes)
        assert restored.identity.user_id == "test_user"

    def test_from_json_invalid_raises_transport_error(self) -> None:
        with pytest.raises(TransportError, match="JSON deserialization failed"):
            CapsuleSerializer.from_json("{invalid json!!")

    def test_to_json_indent(self, sample_capsule: Capsule) -> None:
        result = CapsuleSerializer.to_json(sample_capsule, indent=4)
        assert isinstance(result, str)


# ── MsgPack round-trip ────────────────────────────────────────────────────────

class TestMsgpackSerialization:
    def test_to_msgpack_returns_bytes(self, sample_capsule: Capsule) -> None:
        result = CapsuleSerializer.to_msgpack(sample_capsule)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_from_msgpack_returns_capsule(self, sample_capsule: Capsule) -> None:
        packed = CapsuleSerializer.to_msgpack(sample_capsule)
        restored = CapsuleSerializer.from_msgpack(packed)
        assert isinstance(restored, Capsule)
        assert restored.capsule_type == CapsuleType.MEMORY
        assert restored.identity.user_id == "test_user"

    def test_from_msgpack_invalid_raises_transport_error(self) -> None:
        with pytest.raises(TransportError, match="MsgPack deserialization failed"):
            CapsuleSerializer.from_msgpack(b"\x00\x01\x02\x03")


# ── detect_format ─────────────────────────────────────────────────────────────

class TestDetectFormat:
    def test_capsule_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "test.capsule"
        p.write_bytes(b"dummy")
        assert CapsuleSerializer.detect_format(p) == "msgpack"

    def test_txt_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "test.txt"
        p.write_text("hello")
        assert CapsuleSerializer.detect_format(p) == "prompt"

    def test_json_extension_regular(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        p.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        assert CapsuleSerializer.detect_format(p) == "json"

    def test_json_extension_universal(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        p.write_text(
            json.dumps({"schema": "universal-memory/1.0", "title": "test"}),
            encoding="utf-8",
        )
        assert CapsuleSerializer.detect_format(p) == "universal"

    def test_json_extension_invalid_json_content(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        p.write_text("not valid json at all{{{", encoding="utf-8")
        assert CapsuleSerializer.detect_format(p) == "json"

    def test_unknown_extension_defaults_to_json(self, tmp_path: Path) -> None:
        p = tmp_path / "test.xyz"
        p.write_bytes(b"data")
        assert CapsuleSerializer.detect_format(p) == "json"

    def test_detect_format_with_string_path(self, tmp_path: Path) -> None:
        p = tmp_path / "test.capsule"
        p.write_bytes(b"dummy")
        assert CapsuleSerializer.detect_format(str(p)) == "msgpack"
