"""Tests for CapsuleBuilder, Transport (crypto/validator), and CapsuleStore (T1.8-T1.9, includes Patch #2)."""
from __future__ import annotations
import importlib.util
import json
import pytest
from datetime import datetime
from pathlib import Path
from capsule_memory.models.capsule import (
    Capsule, CapsuleType, CapsuleStatus, CapsuleIdentity, CapsuleLifecycle,
    CapsuleMetadata,
)
from capsule_memory.models.memory import ConversationTurn, MemoryFact, MemoryPayload
from capsule_memory.models.events import SkillDraft, SkillTriggerRule
from capsule_memory.models.skill import SkillPayload
from capsule_memory.core.builder import CapsuleBuilder
from capsule_memory.core.session import SessionConfig
from capsule_memory.core.store import CapsuleStore
from capsule_memory.transport.crypto import CapsuleCrypto
from capsule_memory.transport.schema_validator import validate_capsule, validate_universal_memory, verify_checksum
from capsule_memory.storage.local import LocalStorage
from capsule_memory.exceptions import CapsuleNotFoundError

_has_cryptography = importlib.util.find_spec("cryptography") is not None


# ── CapsuleBuilder tests ──

def _make_config() -> SessionConfig:
    return SessionConfig(user_id="u1", session_id="sess_test")


def _make_memory_payload() -> MemoryPayload:
    return MemoryPayload(
        facts=[MemoryFact(key="lang", value="Python", confidence=0.9, category="technical_preference")],
        context_summary="User prefers Python",
        entities={"technologies": ["Python"]},
    )


def test_build_memory_capsule() -> None:
    config = _make_config()
    payload = _make_memory_payload()
    capsule = CapsuleBuilder.build_memory(config, payload, title="Test", tags=["python"])
    assert capsule.capsule_type == CapsuleType.MEMORY
    assert capsule.identity.user_id == "u1"
    assert capsule.metadata.title == "Test"
    assert capsule.integrity.checksum  # non-empty
    assert capsule.lifecycle.status == CapsuleStatus.SEALED


def test_build_skill_capsule() -> None:
    config = _make_config()
    skill = SkillPayload(
        skill_name="Django ORM",
        trigger_pattern="query optimization",
        description="Use prefetch_related",
        instructions="Apply prefetch_related for ManyToMany",
    )
    capsule = CapsuleBuilder.build_skill(config, skill, tags=["django"])
    assert capsule.capsule_type == CapsuleType.SKILL
    assert capsule.metadata.title == "Django ORM"
    assert capsule.payload["skill_name"] == "Django ORM"


def test_build_hybrid_capsule() -> None:
    config = _make_config()
    payload = _make_memory_payload()
    skills = [{"skill_name": "ORM", "description": "query opt", "instructions": "use select_related"}]
    capsule = CapsuleBuilder.build_hybrid(config, payload, skills, title="Hybrid Test")
    assert capsule.capsule_type == CapsuleType.HYBRID
    assert "memory" in capsule.payload
    assert "skills" in capsule.payload


def test_build_skill_from_draft() -> None:
    config = _make_config()
    draft = SkillDraft(
        suggested_name="Django optimization technique",
        confidence=0.8,
        preview="Use prefetch_related for N+1",
        trigger_rule=SkillTriggerRule.USER_AFFIRMATION,
        source_turns=[2],
    )
    turns = [
        ConversationTurn(turn_id=1, role="user", content="How to optimize?"),
        ConversationTurn(turn_id=2, role="assistant", content="Use prefetch_related and select_related"),
    ]
    skill = CapsuleBuilder.build_skill_from_draft(config, draft, turns)
    assert skill.skill_name == "Django optimization technique"
    assert "prefetch_related" in skill.instructions
    assert len(skill.trigger_keywords) > 0


# ── Transport: Crypto tests ──

@pytest.mark.skipif(not _has_cryptography, reason="cryptography not installed")
def test_encrypt_decrypt_roundtrip() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={"facts": [{"key": "test", "value": "data"}], "context_summary": "test"},
    )
    original_payload = dict(capsule.payload)
    passphrase = "test-secret-123"

    encrypted = CapsuleCrypto.encrypt(capsule, passphrase)
    assert encrypted.integrity.encrypted is True
    assert "encrypted_data" in encrypted.payload
    assert encrypted.integrity.encryption_algo == "Fernet/PBKDF2+CMNamespace"

    decrypted = CapsuleCrypto.decrypt(encrypted, passphrase)
    assert decrypted.integrity.encrypted is False
    assert decrypted.payload == original_payload


@pytest.mark.skipif(not _has_cryptography, reason="cryptography not installed")
def test_decrypt_wrong_passphrase_fails() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={"facts": [], "context_summary": "test"},
    )
    encrypted = CapsuleCrypto.encrypt(capsule, "correct-password")
    with pytest.raises(Exception):  # Fernet InvalidToken or CapsuleIntegrityError
        CapsuleCrypto.decrypt(encrypted, "wrong-password")


# ── Transport: Schema Validator tests ──

def test_validate_capsule_valid() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={"facts": []},
    )
    data = json.loads(capsule.to_json())
    valid, errors = validate_capsule(data)
    assert valid, f"Validation errors: {errors}"


def test_validate_capsule_missing_fields() -> None:
    valid, errors = validate_capsule({"payload": {}})
    assert not valid
    assert any("capsule_id" in e for e in errors)


def test_validate_capsule_wrong_schema_version() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={},
    )
    data = json.loads(capsule.to_json())
    data["schema_version"] = "capsule-schema/1.0+wronguser"
    valid, errors = validate_capsule(data)
    assert not valid
    assert any("mismatch" in e for e in errors)


def test_validate_universal_memory_valid() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        lifecycle=CapsuleLifecycle(sealed_at=datetime.utcnow()),
        payload={"facts": [{"key": "k", "value": "v"}], "context_summary": "test"},
    )
    data = capsule.to_universal_memory()
    valid, errors = validate_universal_memory(data)
    assert valid, f"Validation errors: {errors}"


def test_verify_checksum_valid() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={"facts": [], "context_summary": "test"},
    )
    capsule.integrity.checksum = capsule.compute_checksum()
    data = json.loads(capsule.to_json())
    assert verify_checksum(data) is True


def test_verify_checksum_tampered() -> None:
    capsule = Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={"facts": [], "context_summary": "test"},
    )
    capsule.integrity.checksum = capsule.compute_checksum()
    data = json.loads(capsule.to_json())
    data["payload"]["context_summary"] = "TAMPERED"
    assert verify_checksum(data) is False


# ── CapsuleStore tests (Patch #2) ──

@pytest.fixture
def store(tmp_path: Path) -> CapsuleStore:
    storage = LocalStorage(path=tmp_path)
    return CapsuleStore(storage)


def _make_stored_capsule(user_id: str = "u1", facts_data: list | None = None,
                          summary: str = "test", tags: list[str] | None = None) -> Capsule:
    return Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id=user_id, session_id="s1"),
        lifecycle=CapsuleLifecycle(status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow()),
        metadata=CapsuleMetadata(title="Test", tags=tags or ["test"], turn_count=2),
        payload={
            "facts": facts_data or [{"key": "lang", "value": "Python", "confidence": 0.9}],
            "context_summary": summary,
            "entities": {}, "timeline": [], "raw_turns": [],
        },
    )


async def test_store_save_and_get(store: CapsuleStore) -> None:
    c = _make_stored_capsule()
    c.integrity.checksum = c.compute_checksum()
    await store.save(c)
    retrieved = await store.get(c.capsule_id)
    assert retrieved.capsule_id == c.capsule_id


async def test_store_get_nonexistent_raises(store: CapsuleStore) -> None:
    with pytest.raises(CapsuleNotFoundError):
        await store.get("nonexistent_id")


async def test_store_merge(store: CapsuleStore) -> None:
    c1 = _make_stored_capsule(
        facts_data=[{"key": "lang", "value": "Python", "confidence": 0.9}],
        summary="Python project",
        tags=["python"],
    )
    c2 = _make_stored_capsule(
        facts_data=[
            {"key": "lang", "value": "Python 3.11", "confidence": 0.95},
            {"key": "framework", "value": "Django", "confidence": 0.8},
        ],
        summary="Django project",
        tags=["django"],
    )
    c1.integrity.checksum = c1.compute_checksum()
    c2.integrity.checksum = c2.compute_checksum()
    await store.save(c1)
    await store.save(c2)

    merged = await store.merge([c1.capsule_id, c2.capsule_id], title="Merged")
    assert merged.capsule_type in (CapsuleType.MEMORY, CapsuleType.HYBRID)

    # lang key should have kept the higher-confidence version (0.95)
    facts = merged.payload.get("facts", merged.payload.get("memory", {}).get("facts", []))
    lang_facts = [f for f in facts if f.get("key") == "lang"]
    assert len(lang_facts) == 1
    assert lang_facts[0]["confidence"] == 0.95

    # framework fact should be present
    framework_facts = [f for f in facts if f.get("key") == "framework"]
    assert len(framework_facts) == 1


async def test_store_diff(store: CapsuleStore) -> None:
    c1 = _make_stored_capsule(
        facts_data=[
            {"key": "lang", "value": "Python", "confidence": 0.9},
            {"key": "removed_key", "value": "old", "confidence": 0.5},
        ],
        summary="Old summary",
    )
    c2 = _make_stored_capsule(
        facts_data=[
            {"key": "lang", "value": "Python 3.11", "confidence": 0.95},
            {"key": "new_key", "value": "new", "confidence": 0.7},
        ],
        summary="New summary",
    )
    c1.integrity.checksum = c1.compute_checksum()
    c2.integrity.checksum = c2.compute_checksum()
    await store.save(c1)
    await store.save(c2)

    diff = await store.diff(c1.capsule_id, c2.capsule_id)
    assert diff["summary_changed"] is True
    assert len(diff["added_facts"]) >= 1  # new_key
    assert len(diff["removed_facts"]) >= 1  # removed_key
    assert len(diff["modified_facts"]) >= 1  # lang value changed


async def test_store_fork(store: CapsuleStore) -> None:
    c = _make_stored_capsule(tags=["original"])
    c.integrity.checksum = c.compute_checksum()
    await store.save(c)

    forked = await store.fork(c.capsule_id, new_user_id="u2")
    assert forked.identity.user_id == "u2"
    assert forked.lifecycle.status == CapsuleStatus.IMPORTED
    assert forked.metadata.forked_from == c.capsule_id
    assert forked.capsule_id != c.capsule_id

    # Original should be unchanged
    original = await store.get(c.capsule_id)
    assert original.identity.user_id == "u1"


async def test_store_get_context_for_injection(store: CapsuleStore) -> None:
    c = _make_stored_capsule(summary="Python Django optimization guide")
    c.integrity.checksum = c.compute_checksum()
    await store.save(c)

    result = await store.get_context_for_injection("Python optimization", "u1")
    assert "prompt_injection" in result
    assert "facts" in result
    assert "sources" in result
