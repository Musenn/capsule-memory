"""Advanced tests for capsule_memory/core/store.py — merge with skills, CONTEXT/SKILL summaries, fork edge cases."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import pytest
from datetime import datetime
from pathlib import Path

from capsule_memory.models.capsule import (
    Capsule, CapsuleType, CapsuleStatus, CapsuleIdentity, CapsuleLifecycle,
    CapsuleMetadata,
)
from capsule_memory.core.store import CapsuleStore
from capsule_memory.storage.local import LocalStorage
from capsule_memory.exceptions import CapsuleNotFoundError, StorageError


@pytest.fixture
def store(tmp_path: Path) -> CapsuleStore:
    return CapsuleStore(LocalStorage(path=tmp_path))


def _make_capsule(
    user_id: str = "u1",
    capsule_type: CapsuleType = CapsuleType.MEMORY,
    title: str = "Test",
    tags: list[str] | None = None,
    payload: dict | None = None,
) -> Capsule:
    c = Capsule(
        capsule_type=capsule_type,
        identity=CapsuleIdentity(user_id=user_id, session_id="s1"),
        lifecycle=CapsuleLifecycle(status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow()),
        metadata=CapsuleMetadata(title=title, tags=tags or ["test"], turn_count=2),
        payload=payload or {
            "facts": [{"key": "lang", "value": "Python", "confidence": 0.9}],
            "context_summary": "test summary",
            "entities": {}, "timeline": [], "raw_turns": [],
        },
    )
    c.integrity.checksum = c.compute_checksum()
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# merge — with skills (HYBRID output)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeWithSkills:
    async def test_merge_hybrid_capsules(self, store: CapsuleStore) -> None:
        """Merging capsules with both facts and skills should produce HYBRID."""
        c1 = _make_capsule(
            capsule_type=CapsuleType.HYBRID,
            payload={
                "memory": {
                    "facts": [{"key": "lang", "value": "Python", "confidence": 0.9}],
                    "context_summary": "Python expertise",
                },
                "skills": [
                    {"skill_name": "code_review", "description": "Review code", "instructions": "..."},
                ],
            },
        )
        c2 = _make_capsule(
            capsule_type=CapsuleType.HYBRID,
            payload={
                "memory": {
                    "facts": [{"key": "framework", "value": "Django", "confidence": 0.8}],
                    "context_summary": "Django expertise",
                },
                "skills": [
                    {"skill_name": "db_optimize", "description": "Optimize DB", "instructions": "..."},
                ],
            },
        )
        await store.save(c1)
        await store.save(c2)

        merged = await store.merge([c1.capsule_id, c2.capsule_id], title="Merged Skills")
        assert merged.capsule_type == CapsuleType.HYBRID
        assert "skills" in merged.payload
        assert len(merged.payload["skills"]) == 2
        assert "memory" in merged.payload

    async def test_merge_skill_only_capsules(self, store: CapsuleStore) -> None:
        """Merging SKILL capsules (no facts) should produce SKILL output."""
        c1 = _make_capsule(
            capsule_type=CapsuleType.SKILL,
            payload={
                "skill_name": "format_code",
                "trigger_pattern": "format",
                "description": "Format code with black",
                "instructions": "Run black",
            },
        )
        c2 = _make_capsule(
            capsule_type=CapsuleType.SKILL,
            payload={
                "skill_name": "lint_code",
                "trigger_pattern": "lint",
                "description": "Lint code with ruff",
                "instructions": "Run ruff",
            },
        )
        await store.save(c1)
        await store.save(c2)

        merged = await store.merge([c1.capsule_id, c2.capsule_id], title="Tools")
        # Two skills + no facts → HYBRID because has_skills=True, has_facts=False → actually SKILL
        # but wait, let me check: has_skills=True, has_facts=False → elif has_skills → CapsuleType.SKILL
        # SKILL type only stores the first skill
        assert merged.capsule_type == CapsuleType.SKILL

    async def test_merge_fewer_than_two_raises(self, store: CapsuleStore) -> None:
        with pytest.raises(StorageError, match="at least 2"):
            await store.merge(["single_id"])


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_summary — CONTEXT type
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractSummary:
    def test_context_type_summary(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.CONTEXT,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={"content": "This is imported context from a text file"},
        )
        summary = CapsuleStore._extract_summary(c)
        assert "imported context" in summary

    def test_skill_type_summary_with_description(self) -> None:
        """SKILL type: when no context_summary, falls back to description."""
        c = Capsule(
            capsule_type=CapsuleType.SKILL,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={
                "skill_name": "test",
                "description": "A test skill description",
            },
        )
        summary = CapsuleStore._extract_summary(c)
        assert "test skill description" in summary

    def test_skill_type_summary_with_context_summary(self) -> None:
        """SKILL type: when context_summary exists, returns it (even if description also exists)."""
        c = Capsule(
            capsule_type=CapsuleType.SKILL,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={
                "skill_name": "test",
                "description": "fallback desc",
                "context_summary": "skill context summary",
            },
        )
        summary = CapsuleStore._extract_summary(c)
        assert summary == "skill context summary"

    def test_memory_type_summary(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.MEMORY,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={"context_summary": "Memory summary content"},
        )
        summary = CapsuleStore._extract_summary(c)
        assert summary == "Memory summary content"


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_facts — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractFacts:
    def test_skill_type_has_no_facts(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.SKILL,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={"skill_name": "test"},
        )
        assert CapsuleStore._extract_facts(c) == []

    def test_hybrid_type_extracts_from_memory(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.HYBRID,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={
                "memory": {"facts": [{"key": "k1", "value": "v1"}]},
                "skills": [],
            },
        )
        facts = CapsuleStore._extract_facts(c)
        assert len(facts) == 1
        assert facts[0]["key"] == "k1"


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_skills — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractSkills:
    def test_skill_type_with_name(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.SKILL,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={"skill_name": "test_skill", "description": "desc"},
        )
        skills = CapsuleStore._extract_skills(c)
        assert len(skills) == 1
        assert skills[0]["skill_name"] == "test_skill"

    def test_skill_type_without_name(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.SKILL,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={"description": "no name"},
        )
        skills = CapsuleStore._extract_skills(c)
        assert skills == []

    def test_memory_type_has_no_skills(self) -> None:
        c = Capsule(
            capsule_type=CapsuleType.MEMORY,
            identity=CapsuleIdentity(user_id="u1", session_id="s1"),
            payload={"facts": []},
        )
        assert CapsuleStore._extract_skills(c) == []


# ═══════════════════════════════════════════════════════════════════════════════
# fork — with additional tags
# ═══════════════════════════════════════════════════════════════════════════════

class TestForkAdvanced:
    async def test_fork_with_additional_tags(self, store: CapsuleStore) -> None:
        c = _make_capsule(tags=["python"])
        await store.save(c)

        forked = await store.fork(
            c.capsule_id, new_user_id="u2",
            additional_tags=["forked", "python"],  # "python" deduplicates
        )
        assert "python" in forked.metadata.tags
        assert "forked" in forked.metadata.tags
        # Deduplicated
        assert forked.metadata.tags.count("python") == 1

    async def test_fork_with_agent_id(self, store: CapsuleStore) -> None:
        c = _make_capsule()
        await store.save(c)

        forked = await store.fork(c.capsule_id, new_user_id="u2", new_agent_id="agent_1")
        assert forked.identity.agent_id == "agent_1"

    async def test_fork_nonexistent_raises(self, store: CapsuleStore) -> None:
        with pytest.raises(CapsuleNotFoundError):
            await store.fork("nonexistent", new_user_id="u2")


# ═══════════════════════════════════════════════════════════════════════════════
# get_context_for_injection — with skills
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetContextWithSkills:
    async def test_context_includes_skills(self, store: CapsuleStore) -> None:
        c = _make_capsule(
            capsule_type=CapsuleType.HYBRID,
            title="Python Optimization",
            tags=["python"],
            payload={
                "memory": {
                    "facts": [{"key": "lang", "value": "Python", "confidence": 0.9}],
                    "context_summary": "Python optimization guide",
                },
                "skills": [
                    {
                        "skill_name": "optimize_queries",
                        "description": "Optimize database queries",
                        "instructions": "Use select_related",
                    },
                ],
            },
        )
        await store.save(c)

        result = await store.get_context_for_injection("Python", "u1")
        assert len(result["skills"]) >= 1
        assert "optimize_queries" in result["skills"][0]["skill_name"]
        assert "Available Skills" in result["prompt_injection"]

    async def test_context_empty_result(self, store: CapsuleStore) -> None:
        result = await store.get_context_for_injection("nonexistent", "nobody")
        assert result["facts"] == []
        assert result["skills"] == []
        assert result["sources"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# diff — with skills
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiffWithSkills:
    async def test_diff_detects_skill_changes(self, store: CapsuleStore) -> None:
        c1 = _make_capsule(
            capsule_type=CapsuleType.HYBRID,
            payload={
                "memory": {"facts": [], "context_summary": "same"},
                "skills": [{"skill_name": "old_skill", "description": "old"}],
            },
        )
        c2 = _make_capsule(
            capsule_type=CapsuleType.HYBRID,
            payload={
                "memory": {"facts": [], "context_summary": "same"},
                "skills": [{"skill_name": "new_skill", "description": "new"}],
            },
        )
        await store.save(c1)
        await store.save(c2)

        diff = await store.diff(c1.capsule_id, c2.capsule_id)
        assert len(diff["added_skills"]) == 1
        assert len(diff["removed_skills"]) == 1
        assert diff["summary_changed"] is False
