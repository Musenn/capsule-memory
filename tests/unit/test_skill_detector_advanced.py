"""Advanced tests for capsule_memory/core/skill_detector.py — RepeatPattern, LLM scorer, edge cases."""
from __future__ import annotations

import json
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

from types import SimpleNamespace
from unittest.mock import patch


from capsule_memory.core.skill_detector import (
    RepeatPatternRule,
    SkillDetector,
    StructuredOutputRule,
    LengthSignificanceRule,
    UserAffirmationRule,
)
from capsule_memory.models.events import SkillTriggerRule
from capsule_memory.models.memory import ConversationTurn


def _make_turn(turn_id: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(turn_id=turn_id, role=role, content=content)


# ═══════════════════════════════════════════════════════════════════════════════
# RepeatPatternRule
# ═══════════════════════════════════════════════════════════════════════════════

class TestRepeatPatternRule:
    async def test_triggers_on_similar_repeated_code(self) -> None:
        """RepeatPatternRule should trigger when 2+ previous turns have similar code blocks."""
        rule = RepeatPatternRule()
        code_block = """```python
import os
from pathlib import Path

class FileProcessor:
    def __init__(self, path):
        self.path = Path(path)

    def process(self):
        for f in self.path.iterdir():
            if f.is_file():
                self._handle(f)

    def _handle(self, file_path):
        with open(file_path) as f:
            data = f.read()
        return data
```"""
        # Create 3 turns with very similar code blocks (similarity > 0.6)
        prev1 = _make_turn(2, "assistant", code_block + "\n\nThis handles file processing.")
        prev2 = _make_turn(4, "assistant", code_block + "\n\nUse this for file operations.")
        current = _make_turn(6, "assistant", code_block + "\n\nFile processor implementation.")
        all_turns = [
            _make_turn(1, "user", "Show me file processing"),
            prev1,
            _make_turn(3, "user", "Show me again"),
            prev2,
            _make_turn(5, "user", "One more time"),
            current,
        ]

        result = await rule.evaluate(current, all_turns)
        assert result is not None
        assert result.trigger_rule == SkillTriggerRule.REPEAT_PATTERN
        assert result.confidence == 0.67

    async def test_no_trigger_on_short_content(self) -> None:
        rule = RepeatPatternRule()
        turn = _make_turn(2, "assistant", "Short reply")
        result = await rule.evaluate(turn, [turn])
        assert result is None

    async def test_no_trigger_on_user_role(self) -> None:
        rule = RepeatPatternRule()
        turn = _make_turn(1, "user", "```python\nprint('hello')\n```" * 20)
        result = await rule.evaluate(turn, [turn])
        assert result is None

    async def test_no_trigger_on_dissimilar_content(self) -> None:
        rule = RepeatPatternRule()
        current = _make_turn(6, "assistant", "```python\n" + "x = 1\n" * 50 + "```")
        prev1 = _make_turn(2, "assistant", "```javascript\n" + "let y = 2;\n" * 50 + "```")
        prev2 = _make_turn(4, "assistant", "```rust\n" + "fn main() {}\n" * 50 + "```")
        all_turns = [
            _make_turn(1, "user", "q"), prev1,
            _make_turn(3, "user", "q"), prev2,
            _make_turn(5, "user", "q"), current,
        ]
        result = await rule.evaluate(current, all_turns)
        assert result is None

    def test_extract_code_and_steps(self) -> None:
        content = """Here's how:
1. Install the package
2. Configure settings

```python
import os
x = 1
```

3. Run migrations"""
        result = RepeatPatternRule._extract_code_and_steps(content)
        assert "```python" in result
        assert "Install the package" in result


# ═══════════════════════════════════════════════════════════════════════════════
# StructuredOutputRule edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestStructuredOutputEdgeCases:
    async def test_triggers_on_table_content(self) -> None:
        """StructuredOutput should trigger on table-formatted content with technical keywords."""
        rule = StructuredOutputRule()
        content = """Here's the comparison of approaches:

| Feature | import Option A | def Option B |
|---------|----------|----------|
| Speed   | Fast     | class Slow    |
| Memory  | Low      | High     |
| Ease    | pip install Easy    | Hard     |

For the best approach, use this class configuration:

```python
class Config:
    pass
```

This def handles all configuration needs."""
        turn = _make_turn(2, "assistant", content)
        result = await rule.evaluate(turn, [turn])
        assert result is not None
        assert result.trigger_rule == SkillTriggerRule.STRUCTURED_OUTPUT

    async def test_no_trigger_without_technical_keywords(self) -> None:
        """No trigger when code block exists but no technical keywords."""
        rule = StructuredOutputRule()
        content = """Here's a poem:

```
roses are red
violets are blue
""" + "x " * 100 + """
the end
```

What a lovely day it is today."""
        turn = _make_turn(2, "assistant", content)
        result = await rule.evaluate(turn, [turn])
        assert result is None

    async def test_named_code_block(self) -> None:
        """Test that language-specific code block generates named skill."""
        rule = StructuredOutputRule()
        content = """Here's the solution:
1. First install dependencies
2. Then configure settings
3. Run the migrations

```python
import os
from django.conf import settings

class DatabaseManager:
    def __init__(self):
        self.host = os.getenv('DB_HOST')

    def connect(self):
        # Connect logic here with proper import
        pass

    def migrate(self):
        # def migration logic
        pass
```

This class handles database management."""
        turn = _make_turn(2, "assistant", content)
        result = await rule.evaluate(turn, [turn])
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# UserAffirmationRule edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserAffirmationEdgeCases:
    async def test_no_trigger_when_no_user_turns(self) -> None:
        rule = UserAffirmationRule()
        turn = _make_turn(1, "assistant", "Some content here")
        result = await rule.evaluate(turn, [turn])
        assert result is None

    async def test_no_trigger_on_user_turn_with_empty_preview(self) -> None:
        """No trigger when the current turn is a user turn (preview would be empty)."""
        rule = UserAffirmationRule()
        user_turn = _make_turn(1, "user", "This is perfect!")
        result = await rule.evaluate(user_turn, [user_turn])
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# LengthSignificanceRule edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestLengthSignificanceEdgeCases:
    async def test_no_trigger_on_long_non_technical(self) -> None:
        """Long content without technical keywords should not trigger."""
        rule = LengthSignificanceRule()
        content = "The weather today is quite pleasant. " * 50
        turn = _make_turn(2, "assistant", content)
        result = await rule.evaluate(turn, [turn])
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# SkillDetector — LLM scorer path
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMScorer:
    async def test_llm_scorer_accepts_high_score(self) -> None:
        """LLM scorer with high score should keep the draft."""
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            scores_json = json.dumps({
                "generality": 0.9, "reusability": 0.8, "completeness": 0.85
            })

            async def mock_acompletion(*args, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=scores_json))]
                )

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                detector = SkillDetector(
                    rules=[UserAffirmationRule()],
                    enable_llm_scorer=True,
                )
                user_turn = _make_turn(1, "user", "This is perfect! Save this!")
                assistant_turn = _make_turn(
                    2, "assistant",
                    "Here is the optimization guide for Django ORM prefetch_related..."
                )
                event = await detector.check(assistant_turn, [user_turn, assistant_turn])

            assert event is not None
            # Confidence should be boosted by LLM score
            assert event.skill_draft.confidence > 0.65
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

    async def test_llm_scorer_rejects_low_score(self) -> None:
        """LLM scorer with low score should reject the draft."""
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            scores_json = json.dumps({
                "generality": 0.1, "reusability": 0.1, "completeness": 0.1
            })

            async def mock_acompletion(*args, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=scores_json))]
                )

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                detector = SkillDetector(
                    rules=[UserAffirmationRule()],
                    enable_llm_scorer=True,
                )
                user_turn = _make_turn(1, "user", "This is perfect! Save this!")
                assistant_turn = _make_turn(
                    2, "assistant",
                    "Here is the answer to your specific one-off question..."
                )
                event = await detector.check(assistant_turn, [user_turn, assistant_turn])

            # Score (0.1+0.1+0.1)/3 = 0.1 < 0.65 → rejected
            assert event is None
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

    async def test_llm_scorer_timeout_fallback(self) -> None:
        """LLM scorer timeout should fallback to 0.75."""
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            import asyncio

            async def mock_acompletion(*args, **kwargs):
                await asyncio.sleep(10)  # Will be cancelled by timeout

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                detector = SkillDetector(
                    rules=[UserAffirmationRule()],
                    enable_llm_scorer=True,
                )
                user_turn = _make_turn(1, "user", "Perfect! Save this approach!")
                assistant_turn = _make_turn(
                    2, "assistant",
                    "Complete optimization guide for Django prefetch_related..."
                )
                event = await detector.check(assistant_turn, [user_turn, assistant_turn])

            # Fallback score 0.75 >= 0.65, so event should still be returned
            assert event is not None
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

    async def test_safe_evaluate_handles_exception(self) -> None:
        """_safe_evaluate should catch exceptions from rules."""
        os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            class BrokenRule:
                async def evaluate(self, turn, session_turns):
                    raise ValueError("Rule broken")

            detector = SkillDetector(rules=[BrokenRule()])
            turn = _make_turn(2, "assistant", "test content")
            event = await detector.check(turn, [turn])
            assert event is None
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
