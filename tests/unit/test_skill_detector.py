"""Tests for skill detector rules and priority ordering (T1.7, includes Patch #1 verification)."""
from __future__ import annotations
import os
from capsule_memory.models.memory import ConversationTurn
from capsule_memory.models.events import SkillTriggerRule
from capsule_memory.core.skill_detector import (
    SkillDetector,
    UserAffirmationRule,
    StructuredOutputRule,
    LengthSignificanceRule,
)


def _make_turn(turn_id: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(turn_id=turn_id, role=role, content=content)


# ── UserAffirmationRule ──

async def test_user_affirmation_triggers_on_positive_words() -> None:
    rule = UserAffirmationRule()
    user_turn = _make_turn(1, "user", "This is perfect, save this approach")
    assistant_turn = _make_turn(2, "assistant", "Here is the solution: use prefetch_related for N+1 queries...")
    result = await rule.evaluate(assistant_turn, [user_turn, assistant_turn])
    assert result is not None
    assert result.trigger_rule == SkillTriggerRule.USER_AFFIRMATION
    assert result.confidence == 0.65


async def test_user_affirmation_no_trigger_on_neutral() -> None:
    rule = UserAffirmationRule()
    user_turn = _make_turn(1, "user", "What about the database schema?")
    assistant_turn = _make_turn(2, "assistant", "The schema should have these tables...")
    result = await rule.evaluate(assistant_turn, [user_turn, assistant_turn])
    assert result is None


# ── StructuredOutputRule ──

async def test_structured_output_triggers_on_code() -> None:
    rule = StructuredOutputRule()
    long_code = """Here's how to set up the project:
1. Install dependencies
2. Configure the database
3. Run migrations

```python
import os
from django.conf import settings

class DatabaseConfig:
    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT', 5432))

    def connect(self):
        # Connect to the database
        pass

    def migrate(self):
        # Run all pending migrations
        pass
```

This class handles all database configuration needs."""
    assistant_turn = _make_turn(2, "assistant", long_code)
    result = await rule.evaluate(assistant_turn, [assistant_turn])
    assert result is not None
    assert result.trigger_rule == SkillTriggerRule.STRUCTURED_OUTPUT


async def test_structured_output_no_trigger_on_short() -> None:
    rule = StructuredOutputRule()
    assistant_turn = _make_turn(2, "assistant", "Just use pip install django")
    result = await rule.evaluate(assistant_turn, [assistant_turn])
    assert result is None


# ── LengthSignificanceRule ──

async def test_length_significance_triggers_on_long_technical() -> None:
    rule = LengthSignificanceRule()
    content = ("Here is the complete guide to setting up a Django project with all necessary configuration.\n"
               "import os\ndef setup():\n    pass\n" * 50 +
               "class Config:\n    pass\n" * 20)
    assistant_turn = _make_turn(2, "assistant", content)
    result = await rule.evaluate(assistant_turn, [assistant_turn])
    assert result is not None
    assert result.trigger_rule == SkillTriggerRule.LENGTH_SIGNIFICANCE
    assert result.confidence == 0.62


async def test_length_significance_no_trigger_on_short() -> None:
    rule = LengthSignificanceRule()
    assistant_turn = _make_turn(2, "assistant", "Short reply")
    result = await rule.evaluate(assistant_turn, [assistant_turn])
    assert result is None


# ── SkillDetector priority (Patch #1 test) ──

async def test_detector_priority_user_affirmation_first() -> None:
    """
    Patch #1 verification: When multiple rules would match simultaneously,
    UserAffirmation (highest priority) should be returned, not lower-priority rules.
    Sequential short-circuit ensures this deterministically.
    """
    # Construct a scenario where both UserAffirmation and StructuredOutput would match
    user_turn = _make_turn(1, "user", "This is perfect! Remember this approach.")
    long_structured = """Here's the complete solution:
1. First install the packages
2. Then configure the settings
3. Finally run the migrations

```python
import django
from django.conf import settings

class ProjectSetup:
    def __init__(self):
        self.settings = settings

    def configure(self):
        # Full configuration setup with all needed steps
        pass

    def deploy(self):
        # Deploy to production server
        pass
```

Follow these steps carefully to avoid any issues."""
    assistant_turn = _make_turn(2, "assistant", long_structured)
    turns = [user_turn, assistant_turn]

    detector = SkillDetector()
    # Unset mock mode
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
    event = await detector.check(assistant_turn, turns)

    assert event is not None
    # UserAffirmation should win because it has highest priority
    assert event.trigger_rule == SkillTriggerRule.USER_AFFIRMATION


async def test_detector_returns_none_when_no_match() -> None:
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
    detector = SkillDetector()
    user_turn = _make_turn(1, "user", "What time is it?")
    assistant_turn = _make_turn(2, "assistant", "It's 3 PM.")
    event = await detector.check(assistant_turn, [user_turn, assistant_turn])
    assert event is None


async def test_detector_mock_mode_returns_none() -> None:
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    try:
        detector = SkillDetector()
        user_turn = _make_turn(1, "user", "Perfect! Save this!")
        assistant_turn = _make_turn(2, "assistant", "Here is the solution")
        event = await detector.check(assistant_turn, [user_turn, assistant_turn])
        assert event is None
    finally:
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)


async def test_detector_empty_rules_returns_none() -> None:
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
    detector = SkillDetector(rules=[])
    assistant_turn = _make_turn(2, "assistant", "Some content")
    event = await detector.check(assistant_turn, [assistant_turn])
    assert event is None
