"""Advanced tests for capsule_memory/core/session.py — confirm_skill_trigger paths, background detection."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from capsule_memory.core.session import SessionConfig, SessionTracker
from capsule_memory.core.extractor import MemoryExtractor, ExtractorConfig
from capsule_memory.core.skill_detector import SkillDetector
from capsule_memory.notifier.callback import CallbackNotifier
from capsule_memory.storage.local import LocalStorage
from capsule_memory.models.events import SkillDraft, SkillTriggerEvent, SkillTriggerRule
from capsule_memory.models.memory import ConversationTurn
from capsule_memory.models.capsule import Capsule, CapsuleType
from capsule_memory.exceptions import SessionError


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(path=tmp_path)


def _make_tracker(storage: LocalStorage, rules=None) -> SessionTracker:
    config = SessionConfig(user_id="u1", session_id="sess_adv")
    extractor = MemoryExtractor(ExtractorConfig())
    detector = SkillDetector(rules=rules if rules is not None else [])
    notifier = CallbackNotifier(lambda evt: None)
    return SessionTracker(
        config=config,
        storage=storage,
        extractor=extractor,
        skill_detector=detector,
        notifier=notifier,
    )


def _make_draft(rule: SkillTriggerRule = SkillTriggerRule.USER_AFFIRMATION) -> SkillDraft:
    return SkillDraft(
        suggested_name="Test skill",
        confidence=0.85,
        preview="Use prefetch_related for N+1 optimization in Django ORM queries",
        trigger_rule=rule,
        source_turns=[2],
    )


def _make_event(
    session_id: str = "sess_adv",
    rule: SkillTriggerRule = SkillTriggerRule.USER_AFFIRMATION,
) -> SkillTriggerEvent:
    return SkillTriggerEvent(
        session_id=session_id,
        trigger_rule=rule,
        skill_draft=_make_draft(rule),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# confirm_skill_trigger — all resolution paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfirmSkillTrigger:
    async def test_extract_skill(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        await tracker.ingest("How to optimize?", "Use prefetch_related and select_related")
        event = _make_event()
        tracker.state.pending_triggers.append(event)

        result = await tracker.confirm_skill_trigger(event.event_id, "extract_skill")
        assert result is None
        assert event.resolved is True
        assert event.resolution == "extract_skill"
        assert len(tracker.state.confirmed_skill_payloads) == 1

    async def test_extract_hybrid(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        await tracker.ingest("How to optimize?", "Use select_related for FK lookups")
        event = _make_event()
        tracker.state.pending_triggers.append(event)

        result = await tracker.confirm_skill_trigger(event.event_id, "extract_hybrid")
        assert result is None
        assert event.resolved is True
        assert len(tracker.state.confirmed_skill_payloads) == 1

    async def test_merge_memory(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        await tracker.ingest("query tip", "Use indexes on FK columns")
        event = _make_event()
        tracker.state.pending_triggers.append(event)

        result = await tracker.confirm_skill_trigger(event.event_id, "merge_memory")
        assert result is None
        assert event.resolved is True
        assert event.skill_draft.preview in tracker.state.extra_context

    async def test_ignore(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        await tracker.ingest("msg", "resp")
        event = _make_event()
        tracker.state.pending_triggers.append(event)

        result = await tracker.confirm_skill_trigger(event.event_id, "ignore")
        assert result is None
        assert event.resolved is True

    async def test_never(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        await tracker.ingest("msg", "resp")
        event = _make_event()
        tracker.state.pending_triggers.append(event)

        result = await tracker.confirm_skill_trigger(event.event_id, "never")
        assert result is None
        assert event.resolved is True
        assert event.trigger_rule.value in tracker.state.never_trigger_patterns

    async def test_event_not_found_raises(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        with pytest.raises(SessionError, match="not found"):
            await tracker.confirm_skill_trigger("nonexistent_event", "ignore")


# ═══════════════════════════════════════════════════════════════════════════════
# _detect_skill_background
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectSkillBackground:
    async def test_detection_returns_event(self, storage: LocalStorage) -> None:
        """When MOCK mode is off and a rule matches, pending_triggers should grow."""
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            from capsule_memory.core.skill_detector import UserAffirmationRule
            tracker = _make_tracker(storage, rules=[UserAffirmationRule()])

            user_turn = ConversationTurn(turn_id=1, role="user", content="This is perfect! Save this approach.")
            assistant_turn = ConversationTurn(
                turn_id=2, role="assistant",
                content="Here is the complete optimization guide using prefetch_related for N+1 queries in Django ORM..."
            )
            tracker.state.turns.extend([user_turn, assistant_turn])

            await tracker._detect_skill_background(assistant_turn)
            assert len(tracker.state.pending_triggers) == 1
            assert tracker.state.pending_triggers[0].trigger_rule == SkillTriggerRule.USER_AFFIRMATION
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"

    async def test_detection_skips_never_pattern(self, storage: LocalStorage) -> None:
        """Events with trigger_rule in never_trigger_patterns are suppressed."""
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            from capsule_memory.core.skill_detector import UserAffirmationRule
            tracker = _make_tracker(storage, rules=[UserAffirmationRule()])
            tracker.state.never_trigger_patterns.add("user_affirmation")

            user_turn = ConversationTurn(turn_id=1, role="user", content="Perfect! Save this!")
            assistant_turn = ConversationTurn(
                turn_id=2, role="assistant",
                content="Here is the full solution for query optimization using prefetch_related..."
            )
            tracker.state.turns.extend([user_turn, assistant_turn])

            await tracker._detect_skill_background(assistant_turn)
            assert len(tracker.state.pending_triggers) == 0
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"

    async def test_detection_handles_exception(self, storage: LocalStorage) -> None:
        """Background detection should not raise even if skill_detector throws."""
        tracker = _make_tracker(storage)
        tracker.skill_detector.check = AsyncMock(side_effect=RuntimeError("boom"))

        turn = ConversationTurn(turn_id=1, role="assistant", content="test")
        # Should not raise
        await tracker._detect_skill_background(turn)
        assert len(tracker.state.pending_triggers) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# draft_capsule metadata update during ingest
# ═══════════════════════════════════════════════════════════════════════════════

class TestDraftCapsuleUpdate:
    async def test_draft_capsule_turn_count_updated(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        # Set a draft capsule to test the turn_count update path (line 105-106)
        from capsule_memory.models.capsule import (
            CapsuleIdentity, CapsuleLifecycle, CapsuleMetadata,
        )
        tracker.state.draft_capsule = Capsule(
            capsule_type=CapsuleType.MEMORY,
            identity=CapsuleIdentity(user_id="u1", session_id="sess_adv"),
            lifecycle=CapsuleLifecycle(),
            metadata=CapsuleMetadata(title="Draft"),
            payload={},
        )

        await tracker.ingest("msg1", "resp1")
        assert tracker.state.draft_capsule.metadata.turn_count == 2

        await tracker.ingest("msg2", "resp2")
        assert tracker.state.draft_capsule.metadata.turn_count == 4


# ═══════════════════════════════════════════════════════════════════════════════
# seal with extra_context and confirmed_skill_payloads
# ═══════════════════════════════════════════════════════════════════════════════

class TestSealAdvanced:
    async def test_seal_with_extra_context(self, storage: LocalStorage) -> None:
        tracker = _make_tracker(storage)
        await tracker.ingest("msg", "resp")
        tracker.state.extra_context = "Additional context from merge_memory"

        capsule = await tracker.seal(title="Extra Context Capsule")
        # The extra_context should be appended to context_summary
        payload = capsule.payload
        memory = payload.get("memory", payload)
        assert "Additional context" in memory.get("context_summary", "")

    async def test_seal_with_confirmed_skills_produces_hybrid(self, storage: LocalStorage) -> None:
        """When confirmed_skill_payloads exist, seal should create HYBRID capsule."""
        tracker = _make_tracker(storage)
        await tracker.ingest("How to optimize?", "Use prefetch_related")

        # Add a confirmed skill payload
        event = _make_event()
        tracker.state.pending_triggers.append(event)
        await tracker.confirm_skill_trigger(event.event_id, "extract_skill")

        capsule = await tracker.seal(title="Hybrid Seal")
        assert capsule.capsule_type == CapsuleType.HYBRID

    async def test_seal_strips_raw_turns_by_default(self, storage: LocalStorage) -> None:
        """By default include_raw_turns=False, so raw_turns should be empty."""
        tracker = _make_tracker(storage)
        await tracker.ingest("msg", "resp")
        capsule = await tracker.seal()
        payload = capsule.payload
        memory = payload.get("memory", payload)
        assert memory.get("raw_turns", []) == []


# ═══════════════════════════════════════════════════════════════════════════════
# auto_seal_on_exit with no turns (should NOT seal)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoSealEdgeCases:
    async def test_no_auto_seal_when_no_turns(self, storage: LocalStorage) -> None:
        config = SessionConfig(user_id="u1", session_id="sess_empty", auto_seal_on_exit=True)
        tracker = SessionTracker(
            config=config,
            storage=storage,
            extractor=MemoryExtractor(ExtractorConfig()),
            skill_detector=SkillDetector(rules=[]),
            notifier=CallbackNotifier(lambda evt: None),
        )
        async with tracker:
            pass  # no ingest
        # Session should still be active because no turns were ingested
        assert tracker.state.is_active is True

    async def test_no_auto_seal_when_disabled(self, storage: LocalStorage) -> None:
        config = SessionConfig(user_id="u1", session_id="sess_no_auto", auto_seal_on_exit=False)
        tracker = SessionTracker(
            config=config,
            storage=storage,
            extractor=MemoryExtractor(ExtractorConfig()),
            skill_detector=SkillDetector(rules=[]),
            notifier=CallbackNotifier(lambda evt: None),
        )
        async with tracker:
            await tracker.ingest("msg", "resp")
        # auto_seal_on_exit=False means session stays active
        assert tracker.state.is_active is True
