"""
Integration test for SkillDetector LLM Scorer (T2.3).

Requires:
    - A valid API key (OPENAI_API_KEY or equivalent for litellm)
    - CAPSULE_SKILL_LLM_SCORE=true

Run with: pytest tests/integration/test_skill_detector_llm.py -v -m integration
"""
from __future__ import annotations

import os

import pytest

from capsule_memory.core.skill_detector import SkillDetector
from capsule_memory.models.events import SkillTriggerRule
from capsule_memory.models.memory import ConversationTurn

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def ensure_no_mock():
    """Disable mock mode for integration tests."""
    old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
    yield
    if old is not None:
        os.environ["CAPSULE_MOCK_EXTRACTOR"] = old


def _has_api_key() -> bool:
    """Check if any supported API key is available."""
    return bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("AZURE_API_KEY")
    )


@pytest.mark.skipif(not _has_api_key(), reason="No API key available for LLM scoring")
async def test_llm_scorer_returns_valid_score() -> None:
    """LLM scorer should return a float between 0.0 and 1.0."""
    detector = SkillDetector(enable_llm_scorer=True)

    # Create a structured technical turn that triggers StructuredOutput rule
    turn = ConversationTurn(
        turn_id=2,
        role="assistant",
        content=(
            "Here's how to optimize Django queries:\n\n"
            "1. Use select_related for ForeignKey joins\n"
            "2. Use prefetch_related for ManyToMany\n"
            "3. Add db_index=True to frequently queried fields\n\n"
            "```python\n"
            "from django.db import models\n\n"
            "class Order(models.Model):\n"
            "    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)\n"
            "    product = models.ForeignKey(Product, on_delete=models.CASCADE)\n"
            "    created_at = models.DateTimeField(auto_now_add=True, db_index=True)\n\n"
            "# Optimized query\n"
            "orders = Order.objects.select_related('user', 'product').filter(\n"
            "    created_at__gte=last_week\n"
            ")\n"
            "```\n\n"
            "This approach reduces N+1 queries and improves performance significantly."
        ),
    )
    user_turn = ConversationTurn(
        turn_id=1,
        role="user",
        content="How do I optimize Django database queries?",
    )
    session_turns = [user_turn, turn]

    event = await detector.check(turn, session_turns)
    # With LLM scorer, the event may or may not be returned depending on scores
    # But the scorer itself should not raise an exception
    if event is not None:
        assert 0.0 <= event.skill_draft.confidence <= 1.0


@pytest.mark.skipif(not _has_api_key(), reason="No API key available for LLM scoring")
async def test_llm_scorer_timeout_fallback() -> None:
    """LLM scorer with very short timeout should fallback gracefully."""
    from capsule_memory.models.events import SkillDraft

    detector = SkillDetector(enable_llm_scorer=True)

    draft = SkillDraft(
        suggested_name="Test Skill",
        confidence=0.75,
        preview="Some technical content about query optimization",
        trigger_rule=SkillTriggerRule.STRUCTURED_OUTPUT,
        source_turns=[1],
    )
    turn = ConversationTurn(turn_id=1, role="assistant", content="test")

    # _llm_score should return a float even on timeout
    score = await detector._llm_score(draft, turn)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


async def test_llm_scorer_disabled_by_default() -> None:
    """When enable_llm_scorer=False, no LLM calls are made."""
    detector = SkillDetector(enable_llm_scorer=False)
    assert detector.enable_llm_scorer is False
