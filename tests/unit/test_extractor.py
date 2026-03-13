"""Tests for capsule_memory/core/extractor.py — MemoryExtractor."""
from __future__ import annotations

import json
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from capsule_memory.core.extractor import (
    ExtractorConfig,
    MemoryExtractor,
    MOCK_PAYLOAD,
    _format_turns,
)
from capsule_memory.models.memory import ConversationTurn, MemoryPayload


@pytest.fixture(autouse=True)
def _ensure_mock_extractor_env():
    """Guarantee CAPSULE_MOCK_EXTRACTOR is restored after every test."""
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    yield
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_turn(turn_id: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(turn_id=turn_id, role=role, content=content)


def _make_turns(*pairs: tuple[str, str]) -> list[ConversationTurn]:
    turns = []
    for i, (user_msg, ai_msg) in enumerate(pairs, start=1):
        turns.append(_make_turn(i * 2 - 1, "user", user_msg))
        turns.append(_make_turn(i * 2, "assistant", ai_msg))
    return turns


# ═══════════════════════════════════════════════════════════════════════════════
# _format_turns
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatTurns:
    def test_basic_formatting(self) -> None:
        turns = [
            _make_turn(1, "user", "Hello"),
            _make_turn(2, "assistant", "Hi"),
        ]
        result = _format_turns(turns)
        assert "[User]: Hello" in result
        assert "[Assistant]: Hi" in result

    def test_system_role(self) -> None:
        turns = [_make_turn(1, "system", "You are helpful")]
        result = _format_turns(turns)
        assert "[System]: You are helpful" in result

    def test_truncation(self) -> None:
        turns = _make_turns(*[("q", "a") for _ in range(200)])
        result = _format_turns(turns, max_turns=10)
        lines = [line for line in result.strip().split("\n") if line]
        assert len(lines) == 10

    def test_content_truncation(self) -> None:
        long_content = "x" * 1000
        turns = [_make_turn(1, "user", long_content)]
        result = _format_turns(turns)
        # Content should be truncated to 551 chars
        assert len(result.split(": ", 1)[1]) == 551

    def test_empty_turns(self) -> None:
        result = _format_turns([])
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════════
# ExtractorConfig
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractorConfig:
    def test_defaults(self) -> None:
        config = ExtractorConfig()
        assert config.model == ""
        assert config.max_facts == 40
        assert config.max_turns_for_extraction == 100
        assert config.language == "auto"
        assert config.include_raw_turns is False

    def test_custom(self) -> None:
        config = ExtractorConfig(model="gpt-4", max_facts=10)
        assert config.model == "gpt-4"
        assert config.max_facts == 10


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryExtractor — mock mode
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryExtractorMockMode:
    async def test_mock_mode_returns_preset(self) -> None:
        extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
        turns = _make_turns(("hello", "world"))
        result = await extractor.extract(turns)
        assert result is MOCK_PAYLOAD
        assert result.context_summary.startswith("[MOCK]")
        assert len(result.facts) == 1
        assert result.facts[0].key == "mock.test_fact"


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryExtractor — with mocked litellm
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryExtractorWithMockedLLM:
    async def test_extract_with_llm(self) -> None:
        """Test real extraction path with mocked litellm.acompletion."""
        # Temporarily disable mock mode
        old_val = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            facts_json = json.dumps([
                {
                    "key": "tech.python",
                    "value": "User prefers Python",
                    "confidence": 0.95,
                    "category": "technical_preference",
                },
            ])

            facts_response = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=facts_json))]
            )
            summary_response = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="A test summary."))]
            )

            call_count = 0

            async def mock_acompletion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                prompt = kwargs.get("messages", [{}])[0].get("content", "")
                if "extract all facts" in prompt.lower() or "JSON array" in prompt:
                    return facts_response
                return summary_response

            with patch("litellm.acompletion", side_effect=mock_acompletion):
                extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
                turns = _make_turns(("I use Python for everything", "Python is great!"))
                result = await extractor.extract(turns)

            assert isinstance(result, MemoryPayload)
            assert len(result.facts) == 1
            assert result.facts[0].key == "tech.python"
            assert result.context_summary == "A test summary."
        finally:
            if old_val:
                os.environ["CAPSULE_MOCK_EXTRACTOR"] = old_val
            else:
                os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

    async def test_extract_empty_turns(self) -> None:
        old_val = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
            result = await extractor.extract([])
            assert isinstance(result, MemoryPayload)
            assert result.facts == []
            assert result.context_summary == ""
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old_val or "true"

    async def test_extract_facts_llm_failure(self) -> None:
        old_val = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            async def mock_acompletion(*args, **kwargs):
                prompt = kwargs.get("messages", [{}])[0].get("content", "")
                if "JSON array" in prompt or "extract all facts" in prompt.lower():
                    raise RuntimeError("LLM error")
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="Summary text"))]
                )

            with patch("litellm.acompletion", side_effect=mock_acompletion):
                extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
                turns = _make_turns(("hello", "world"))
                result = await extractor.extract(turns)

            # facts extraction failed but summary should still work
            assert isinstance(result, MemoryPayload)
            # facts_result will be an exception, so facts list is empty
            assert result.facts == []
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old_val or "true"

    async def test_extract_facts_json_with_code_block(self) -> None:
        old_val = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            # LLM returns JSON wrapped in ```json ... ```
            code_block = '```json\n[{"key": "test.fact", "value": "v", "confidence": 0.8, "category": "other"}]\n```'

            async def mock_acompletion(*args, **kwargs):
                prompt = kwargs.get("messages", [{}])[0].get("content", "")
                if "JSON array" in prompt or "extract all facts" in prompt.lower():
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=code_block))]
                    )
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))]
                )

            with patch("litellm.acompletion", side_effect=mock_acompletion):
                extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
                turns = _make_turns(("q", "a"))
                result = await extractor.extract(turns)

            assert len(result.facts) == 1
            assert result.facts[0].key == "test.fact"
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old_val or "true"

    async def test_extract_invalid_fact_skipped(self) -> None:
        old_val = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            facts_json = json.dumps([
                {"value": "no key field"},  # missing "key" → should be skipped
                {"key": "valid.fact", "value": "ok"},
            ])

            async def mock_acompletion(*args, **kwargs):
                prompt = kwargs.get("messages", [{}])[0].get("content", "")
                if "JSON array" in prompt or "extract all facts" in prompt.lower():
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=facts_json))]
                    )
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="sum"))]
                )

            with patch("litellm.acompletion", side_effect=mock_acompletion):
                extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
                turns = _make_turns(("q", "a"))
                result = await extractor.extract(turns)

            # Only the valid fact should be kept
            assert len(result.facts) == 1
            assert result.facts[0].key == "valid.fact"
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old_val or "true"


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_entities_regex
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractEntitiesRegex:
    def test_detects_languages(self) -> None:
        extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
        turns = [_make_turn(1, "user", "I love Python and TypeScript")]
        result = extractor._extract_entities_regex(turns)
        assert "technologies" in result
        assert "Python" in result["technologies"]
        assert "TypeScript" in result["technologies"]

    def test_detects_frameworks(self) -> None:
        extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
        turns = [_make_turn(1, "user", "I use FastAPI and React for my project")]
        result = extractor._extract_entities_regex(turns)
        assert "technologies" in result
        assert "FastAPI" in result["technologies"]
        assert "React" in result["technologies"]

    def test_empty_when_no_tech(self) -> None:
        extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
        turns = [_make_turn(1, "user", "I like cats and dogs")]
        result = extractor._extract_entities_regex(turns)
        assert result == {}

    def test_deduplicates(self) -> None:
        extractor = MemoryExtractor(ExtractorConfig(model="test-model"))
        turns = [
            _make_turn(1, "user", "Python Python Python"),
            _make_turn(2, "assistant", "Python is great"),
        ]
        result = extractor._extract_entities_regex(turns)
        # Should contain Python only once (set deduplication)
        python_count = result["technologies"].count("Python") + result["technologies"].count("python")
        assert python_count == 1
