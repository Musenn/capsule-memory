"""Tests for capsule_memory/core/llm_utils.py — sanitize_llm_json."""
from __future__ import annotations

import json

import pytest

from capsule_memory.core.llm_utils import sanitize_llm_json


class TestSanitizeLlmJson:
    def test_direct_json_object(self) -> None:
        raw = '{"key": "value", "count": 42}'
        result = sanitize_llm_json(raw)
        assert result == {"key": "value", "count": 42}

    def test_direct_json_array(self) -> None:
        raw = '[{"a": 1}, {"b": 2}]'
        result = sanitize_llm_json(raw)
        assert len(result) == 2
        assert result[0]["a"] == 1

    def test_fenced_code_block_json(self) -> None:
        raw = '```json\n{"skill": "Django ORM"}\n```'
        result = sanitize_llm_json(raw)
        assert result == {"skill": "Django ORM"}

    def test_fenced_code_block_no_language(self) -> None:
        raw = '```\n{"skill": "test"}\n```'
        result = sanitize_llm_json(raw)
        assert result == {"skill": "test"}

    def test_fenced_code_block_with_surrounding_text(self) -> None:
        raw = 'Here is the result:\n\n```json\n[1, 2, 3]\n```\n\nHope this helps!'
        result = sanitize_llm_json(raw)
        assert result == [1, 2, 3]

    def test_brace_matching_with_prefix(self) -> None:
        raw = 'The answer is: {"summary": "Python guide", "facts": []}'
        result = sanitize_llm_json(raw)
        assert result["summary"] == "Python guide"

    def test_bracket_matching_with_decoration(self) -> None:
        raw = 'Sure! Here are the facts:\n[{"key": "lang"}, {"key": "db"}]\nEnd.'
        result = sanitize_llm_json(raw)
        # Brace matching tries { } first but outermost { to } span is invalid.
        # Falls through to bracket matching which succeeds.
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["key"] == "lang"

    def test_bracket_matching_array_only(self) -> None:
        raw = 'Result: [1, 2, 3] done.'
        result = sanitize_llm_json(raw)
        assert result == [1, 2, 3]

    def test_invalid_json_raises(self) -> None:
        raw = "This is just plain text with no JSON at all."
        with pytest.raises(json.JSONDecodeError):
            sanitize_llm_json(raw)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            sanitize_llm_json("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            sanitize_llm_json("   \n\n  ")

    def test_nested_json_object(self) -> None:
        raw = '{"outer": {"inner": [1, 2, 3]}, "flag": true}'
        result = sanitize_llm_json(raw)
        assert result["outer"]["inner"] == [1, 2, 3]
        assert result["flag"] is True

    def test_fenced_block_with_invalid_json_falls_to_brace(self) -> None:
        raw = '```json\nnot valid json\n```\nBut here: {"valid": true}'
        result = sanitize_llm_json(raw)
        assert result == {"valid": True}

    def test_leading_trailing_whitespace(self) -> None:
        raw = '  \n  {"key": "value"}  \n  '
        result = sanitize_llm_json(raw)
        assert result == {"key": "value"}
