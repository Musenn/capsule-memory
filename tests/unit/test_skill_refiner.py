"""Tests for capsule_memory/core/skill_refiner.py — SkillRefiner."""
from __future__ import annotations

import importlib.util
import json
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from capsule_memory.core.skill_refiner import SkillRefiner
from capsule_memory.models.events import SkillDraft, SkillTriggerRule
from capsule_memory.models.memory import ConversationTurn
from capsule_memory.models.skill import SkillPayload

_has_litellm = importlib.util.find_spec("litellm") is not None


def _make_turn(turn_id: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(turn_id=turn_id, role=role, content=content)


def _make_draft(
    name: str = "Django ORM optimization",
    source_turns: list[int] | None = None,
) -> SkillDraft:
    return SkillDraft(
        suggested_name=name,
        confidence=0.8,
        preview="Use prefetch_related for N+1 queries",
        trigger_rule=SkillTriggerRule.USER_AFFIRMATION,
        source_turns=source_turns or [2],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback (no model)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSkillRefinerFallback:
    async def test_no_model_uses_fallback(self) -> None:
        refiner = SkillRefiner(model="")
        draft = _make_draft()
        turns = [
            _make_turn(1, "user", "How to optimize Django queries?"),
            _make_turn(2, "assistant", "Use prefetch_related and select_related"),
        ]
        result = await refiner.refine(draft, turns, session_id="sess1")

        assert isinstance(result, SkillPayload)
        assert result.skill_name == "Django ORM optimization"
        assert "prefetch_related" in result.instructions
        assert result.source_session == "sess1"

    async def test_fallback_extracts_keywords(self) -> None:
        refiner = SkillRefiner(model="")
        draft = _make_draft(name="FastAPI Auth Setup")
        turns = [_make_turn(1, "user", "q"), _make_turn(2, "assistant", "answer")]
        result = await refiner.refine(draft, turns)
        assert len(result.trigger_keywords) > 0

    async def test_fallback_with_no_matching_source_turns(self) -> None:
        refiner = SkillRefiner(model="")
        draft = _make_draft(source_turns=[99])  # Non-existent turn ID
        turns = [
            _make_turn(1, "user", "Hello"),
            _make_turn(2, "assistant", "Hi there"),
        ]
        result = await refiner.refine(draft, turns)
        assert isinstance(result, SkillPayload)
        # Instructions will be empty since no matching source turns
        assert result.instructions == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _build_context
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildContext:
    def test_includes_nearby_turns(self) -> None:
        refiner = SkillRefiner(model="test")
        draft = _make_draft(source_turns=[3])
        turns = [
            _make_turn(1, "user", "Turn 1"),
            _make_turn(2, "assistant", "Turn 2"),
            _make_turn(3, "user", "Turn 3"),
            _make_turn(4, "assistant", "Turn 4"),
            _make_turn(5, "user", "Turn 5"),
            _make_turn(6, "assistant", "Turn 6"),
        ]
        context = refiner._build_context(draft, turns)
        # Should include turns 1-5 (source=3, range ±2)
        assert "Turn 1" in context
        assert "Turn 5" in context
        # Turn 6 is outside range
        assert "Turn 6" not in context

    def test_fallback_to_last_turns_when_no_match(self) -> None:
        refiner = SkillRefiner(model="test")
        draft = _make_draft(source_turns=[99])  # Non-existent turn
        turns = [
            _make_turn(1, "user", "Only turn 1"),
            _make_turn(2, "assistant", "Only turn 2"),
        ]
        context = refiner._build_context(draft, turns)
        assert "Only turn 1" in context
        assert "Only turn 2" in context


# ═══════════════════════════════════════════════════════════════════════════════
# With mocked LLM
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _has_litellm, reason="litellm not installed")
class TestSkillRefinerWithMockedLLM:
    async def test_refine_with_llm(self) -> None:
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            llm_response = json.dumps({
                "skill_name": "Django N+1 Fix",
                "description": "Fix N+1 queries using prefetch_related",
                "trigger_pattern": "query optimization",
                "trigger_keywords": ["django", "N+1", "prefetch"],
                "instructions": "Step 1: Identify N+1. Step 2: Use prefetch_related.",
                "applicable_contexts": ["Django ORM", "database optimization"],
            })

            async def mock_acompletion(*args, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=llm_response))]
                )

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                refiner = SkillRefiner(model="test-model")
                draft = _make_draft()
                turns = [
                    _make_turn(1, "user", "How to fix N+1?"),
                    _make_turn(2, "assistant", "Use prefetch_related"),
                ]
                result = await refiner.refine(draft, turns, session_id="s1")

            assert result.skill_name == "Django N+1 Fix"
            assert "prefetch" in result.trigger_keywords
            assert result.source_session == "s1"
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

    async def test_refine_llm_failure_falls_back(self) -> None:
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            async def mock_acompletion(*args, **kwargs):
                raise RuntimeError("LLM unavailable")

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                refiner = SkillRefiner(model="test-model")
                draft = _make_draft()
                turns = [
                    _make_turn(1, "user", "Q"),
                    _make_turn(2, "assistant", "Use prefetch_related for Django ORM"),
                ]
                result = await refiner.refine(draft, turns)

            assert isinstance(result, SkillPayload)
            assert result.skill_name == "Django ORM optimization"
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

    async def test_refine_llm_returns_invalid_json_falls_back(self) -> None:
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            async def mock_acompletion(*args, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="not json at all"))]
                )

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                refiner = SkillRefiner(model="test-model")
                draft = _make_draft()
                turns = [
                    _make_turn(1, "user", "Q"),
                    _make_turn(2, "assistant", "Answer content"),
                ]
                result = await refiner.refine(draft, turns)

            assert isinstance(result, SkillPayload)
            # Falls back to rule-based
            assert result.skill_name == "Django ORM optimization"
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
