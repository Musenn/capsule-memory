from __future__ import annotations
from datetime import datetime
from capsule_memory.models import (
    Capsule, CapsuleType, CapsuleStatus, CapsuleIdentity, CapsuleLifecycle,
    CapsuleMetadata, SkillTriggerEvent, SkillDraft, SkillTriggerRule,
)

def make_memory_capsule() -> Capsule:
    return Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        lifecycle=CapsuleLifecycle(status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow()),
        metadata=CapsuleMetadata(title="Test", tags=["python"]),
        payload={
            "facts": [{"fact_id": "f001", "key": "user.lang", "value": "Python",
                       "confidence": 0.9, "category": "technical_preference",
                       "created_at": datetime.utcnow().isoformat()}],
            "context_summary": "User prefers Python",
            "entities": {"technologies": ["Python"]},
            "timeline": [],
            "raw_turns": [],
        },
    )

def make_skill_capsule() -> Capsule:
    return Capsule(
        capsule_type=CapsuleType.SKILL,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={
            "skill_name": "Django ORM Optimization",
            "trigger_pattern": "when optimizing queries",
            "description": "Use prefetch_related",
            "instructions": "Use prefetch_related for ManyToMany, select_related for ForeignKey",
            "trigger_keywords": ["N+1", "query"],
            "examples": [],
            "applicable_contexts": [],
            "source_session": "s1",
            "reuse_count": 0,
            "effectiveness_rating": None,
        },
    )

def make_hybrid_capsule() -> Capsule:
    return Capsule(
        capsule_type=CapsuleType.HYBRID,
        identity=CapsuleIdentity(user_id="u1", session_id="s1"),
        payload={
            "memory": {
                "facts": [{"fact_id": "f001", "key": "project.name", "value": "E-commerce Backend",
                           "confidence": 0.95, "category": "project_info",
                           "created_at": datetime.utcnow().isoformat()}],
                "context_summary": "Django e-commerce project",
                "entities": {}, "timeline": [], "raw_turns": [],
            },
            "skills": [{
                "skill_name": "Django Optimization",
                "trigger_pattern": "performance optimization",
                "description": "ORM query optimization",
                "instructions": "Use select_related",
                "trigger_keywords": [],
                "examples": [],
                "applicable_contexts": [],
                "source_session": "s1",
                "reuse_count": 0,
                "effectiveness_rating": None,
            }],
        },
    )

def test_memory_capsule_instantiation() -> None:
    c = make_memory_capsule()
    assert c.capsule_type == CapsuleType.MEMORY
    assert c.capsule_id.startswith("cap_")

def test_json_roundtrip() -> None:
    c = make_memory_capsule()
    restored = Capsule.from_json(c.to_json())
    assert restored.capsule_id == c.capsule_id
    assert restored.payload == c.payload

def test_msgpack_roundtrip() -> None:
    c = make_memory_capsule()
    restored = Capsule.from_msgpack(c.to_msgpack())
    assert restored.capsule_id == c.capsule_id
    assert restored.payload == c.payload

def test_compute_checksum_idempotent() -> None:
    c = make_memory_capsule()
    assert c.compute_checksum() == c.compute_checksum()

def test_to_universal_memory_structure() -> None:
    c = make_memory_capsule()
    u = c.to_universal_memory()
    assert u["schema"] == "universal-memory/1.0"
    assert "prompt_injection" in u
    assert len(u["prompt_injection"]) > 0
    assert isinstance(u["facts"], list)
    assert isinstance(u["skills"], list)

def test_to_universal_memory_skill_capsule() -> None:
    c = make_skill_capsule()
    u = c.to_universal_memory()
    assert len(u["skills"]) == 1
    assert u["skills"][0]["name"] == "Django ORM Optimization"

def test_to_universal_memory_hybrid_capsule() -> None:
    c = make_hybrid_capsule()
    u = c.to_universal_memory()
    assert len(u["facts"]) > 0
    assert len(u["skills"]) > 0

def test_to_prompt_snippet_nonempty() -> None:
    for c in [make_memory_capsule(), make_skill_capsule(), make_hybrid_capsule()]:
        snippet = c.to_prompt_snippet()
        assert "=== Memory Context ===" in snippet
        assert "=== Memory Context End ===" in snippet

def test_from_universal_memory_roundtrip() -> None:
    c = make_hybrid_capsule()
    c.lifecycle.sealed_at = datetime.utcnow()
    u = c.to_universal_memory()
    restored = Capsule.from_universal_memory(u, user_id="new_user")
    assert restored.identity.user_id == "new_user"
    assert restored.lifecycle.status == CapsuleStatus.IMPORTED
    assert len(restored.payload) > 0

def test_skill_trigger_event() -> None:
    evt = SkillTriggerEvent(
        session_id="s1",
        trigger_rule=SkillTriggerRule.STRUCTURED_OUTPUT,
        skill_draft=SkillDraft(
            suggested_name="test skill",
            confidence=0.8,
            preview="test preview",
            trigger_rule=SkillTriggerRule.STRUCTURED_OUTPUT,
            source_turns=[1, 2],
        ),
    )
    assert evt.event_id.startswith("evt_")
    assert not evt.resolved
