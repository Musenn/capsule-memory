"""Tests for capsule_memory/core/memory_compressor.py — MemoryCompressor."""
from __future__ import annotations

import importlib.util
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from capsule_memory.core.memory_compressor import (
    CompressorConfig,
    MemoryCompressor,
    _parse_facts,
)
from capsule_memory.models.memory import ConversationTurn, MemoryFact, MemoryPayload

_has_litellm = importlib.util.find_spec("litellm") is not None


def _make_turn(turn_id: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(turn_id=turn_id, role=role, content=content)


# ═══════════════════════════════════════════════════════════════════════════════
# CompressorConfig
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompressorConfig:
    def test_defaults(self) -> None:
        config = CompressorConfig()
        assert config.compress_threshold == 8000
        assert config.max_layer_tokens == 6000
        assert config.chars_per_token == 2.5

    def test_custom(self) -> None:
        config = CompressorConfig(compress_threshold=1000, max_layer_tokens=500)
        assert config.compress_threshold == 1000
        assert config.max_layer_tokens == 500


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_facts
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseFacts:
    def test_valid_facts(self) -> None:
        raw = [
            {"key": "lang", "value": "Python", "confidence": 0.9, "category": "technical_preference"},
            {"key": "db", "value": "PostgreSQL", "confidence": 0.8, "category": "project_info"},
        ]
        facts = _parse_facts(raw)
        assert len(facts) == 2
        assert facts[0].key == "lang"
        assert facts[0].category == "technical_preference"

    def test_missing_key_skipped(self) -> None:
        raw = [{"value": "no key"}, {"key": "valid", "value": "ok"}]
        facts = _parse_facts(raw)
        assert len(facts) == 1
        assert facts[0].key == "valid"

    def test_invalid_category_defaults_to_other(self) -> None:
        raw = [{"key": "k", "value": "v", "category": "nonexistent_category"}]
        facts = _parse_facts(raw)
        assert facts[0].category == "other"

    def test_non_dict_item_skipped(self) -> None:
        raw = ["string_item", 42, {"key": "ok", "value": "v"}]
        facts = _parse_facts(raw)
        assert len(facts) == 1

    def test_empty_list(self) -> None:
        assert _parse_facts([]) == []

    def test_default_confidence(self) -> None:
        raw = [{"key": "k", "value": "v"}]
        facts = _parse_facts(raw)
        assert facts[0].confidence == 0.8


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryCompressor — mock mode
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryCompressorMockMode:
    async def test_ingest_in_mock_mode_is_noop(self) -> None:
        compressor = MemoryCompressor(model="test-model")
        turns = [_make_turn(1, "user", "Hello"), _make_turn(2, "assistant", "Hi")]
        await compressor.ingest(turns)
        # Buffer should remain empty in mock mode
        assert len(compressor._buffer) == 0

    async def test_finalize_empty_returns_empty_payload(self) -> None:
        compressor = MemoryCompressor(model="test-model")
        result = await compressor.finalize()
        assert isinstance(result, MemoryPayload)
        assert result.facts == []
        assert result.context_summary == ""


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryCompressor — no model (rule-based)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryCompressorNoModel:
    async def test_ingest_buffers_when_no_model(self) -> None:
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            compressor = MemoryCompressor(model="")
            turns = [_make_turn(1, "user", "Hi"), _make_turn(2, "assistant", "Hello")]
            await compressor.ingest(turns)
            assert len(compressor._buffer) == 2
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"

    async def test_finalize_without_model_returns_empty(self) -> None:
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            compressor = MemoryCompressor(model="")
            turns = [_make_turn(1, "user", "Hi"), _make_turn(2, "assistant", "Hello")]
            await compressor.ingest(turns)
            result = await compressor.finalize()
            assert isinstance(result, MemoryPayload)
            # No model → no compression → empty summary from empty layers
            assert result.context_summary == ""
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryCompressor — with mocked litellm
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _has_litellm, reason="litellm not installed")
class TestMemoryCompressorWithMockedLLM:
    async def test_compress_buffer_produces_layer(self) -> None:
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            llm_response = json.dumps({
                "summary": "User discusses Python optimization.",
                "facts": [{"key": "lang", "value": "Python", "confidence": 0.9, "category": "technical_preference"}],
                "discarded_turns": 0,
            })

            async def mock_acompletion(*args, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=llm_response))]
                )

            config = CompressorConfig(compress_threshold=10)  # Low threshold to trigger
            compressor = MemoryCompressor(model="test-model", config=config)

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                turns = [
                    _make_turn(1, "user", "I use Python for everything"),
                    _make_turn(2, "assistant", "Python is great for many tasks"),
                ]
                await compressor.ingest(turns)

            assert len(compressor._layers) == 1
            assert "Python" in compressor._layers[0].summary
            assert len(compressor._all_facts) == 1
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"

    async def test_finalize_merges_layers(self) -> None:
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            call_count = 0

            async def mock_acompletion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content=json.dumps({
                            "summary": f"Compressed summary {call_count}.",
                            "facts": [{"key": f"fact{call_count}", "value": "v", "confidence": 0.8, "category": "other"}],
                            "discarded_turns": 0,
                        })
                    ))]
                )

            config = CompressorConfig(compress_threshold=10)
            compressor = MemoryCompressor(model="test-model", config=config)

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                await compressor.ingest([
                    _make_turn(1, "user", "Message 1"),
                    _make_turn(2, "assistant", "Response 1"),
                ])
                result = await compressor.finalize()

            assert isinstance(result, MemoryPayload)
            assert len(result.context_summary) > 0
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"

    async def test_compress_buffer_llm_failure_fallback(self) -> None:
        old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
        try:
            async def mock_acompletion(*args, **kwargs):
                raise RuntimeError("LLM error")

            config = CompressorConfig(compress_threshold=10)
            compressor = MemoryCompressor(model="test-model", config=config)

            import litellm
            with patch.object(litellm, "acompletion", side_effect=mock_acompletion):
                await compressor.ingest([
                    _make_turn(1, "user", "Hello"),
                    _make_turn(2, "assistant", "This is a response about Python"),
                ])

            # Should fallback to raw truncation
            assert len(compressor._layers) == 1
            assert compressor._layers[0].facts == []
        finally:
            os.environ["CAPSULE_MOCK_EXTRACTOR"] = old or "true"


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryCompressor — helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompressorHelpers:
    def test_est_token_count(self) -> None:
        compressor = MemoryCompressor(model="")
        assert compressor._est("hello") == 2  # 5 chars / 2.5 = 2
        assert compressor._est("") == 1  # min 1

    def test_fmt_formats_turns(self) -> None:
        turns = [
            _make_turn(1, "user", "Hello"),
            _make_turn(2, "assistant", "Hi there"),
        ]
        result = MemoryCompressor._fmt(turns)
        assert "[User]: Hello" in result
        assert "[Assistant]: Hi there" in result

    def test_deduplicate_facts(self) -> None:
        compressor = MemoryCompressor(model="")
        compressor._all_facts = [
            MemoryFact(key="lang", value="Python", confidence=0.9, category="other"),
            MemoryFact(key="lang", value="Python 3.11", confidence=0.95, category="other"),
            MemoryFact(key="db", value="PostgreSQL", confidence=0.8, category="other"),
        ]
        result = compressor._deduplicate_facts()
        assert len(result) == 2
        # First occurrence is kept
        assert result[0].value == "Python"
        assert result[1].key == "db"

    def test_existing_context_block_empty(self) -> None:
        compressor = MemoryCompressor(model="")
        assert compressor._existing_context_block() == ""

    def test_l1_prompt_without_context(self) -> None:
        prompt = MemoryCompressor._l1_prompt("", "[User]: test")
        assert "Analyze the following conversation" in prompt
        assert "Previously extracted" not in prompt

    def test_l1_prompt_with_context(self) -> None:
        prompt = MemoryCompressor._l1_prompt("Previous summary: x", "[User]: test")
        assert "Previously extracted context" in prompt
