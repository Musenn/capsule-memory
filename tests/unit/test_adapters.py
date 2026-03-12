"""Tests for all adapters: openai, anthropic, langchain, llamaindex, raw."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

from pathlib import Path
from types import SimpleNamespace

import pytest

from capsule_memory.adapters.base import TurnData
from capsule_memory.adapters.openai import OpenAIAdapter
from capsule_memory.adapters.anthropic import AnthropicAdapter
from capsule_memory.adapters.langchain import LangChainAdapter, CapsuleMemoryLangChainMemory
from capsule_memory.adapters.llamaindex import (
    CapsuleMemoryLlamaIndexMemory,
    SimpleChatMessage,
)
from capsule_memory.adapters.raw import RawAdapter
from capsule_memory.exceptions import AdapterError


# ═══════════════════════════════════════════════════════════════════════════════
# RawAdapter
# ═══════════════════════════════════════════════════════════════════════════════

class TestRawAdapter:
    def test_adapter_name(self) -> None:
        assert RawAdapter.adapter_name == "raw"

    def test_extract_turn_basic(self) -> None:
        adapter = RawAdapter()
        result = adapter.extract_turn("hello", "world")
        assert isinstance(result, TurnData)
        assert result.user_message == "hello"
        assert result.assistant_response == "world"
        assert result.model == ""
        assert result.tokens_used == 0

    def test_extract_turn_with_kwargs(self) -> None:
        adapter = RawAdapter()
        result = adapter.extract_turn("q", "a", model="gpt-4", tokens=100)
        assert result.model == "gpt-4"
        assert result.tokens_used == 100


# ═══════════════════════════════════════════════════════════════════════════════
# OpenAIAdapter
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpenAIAdapter:
    def test_adapter_name(self) -> None:
        assert OpenAIAdapter.adapter_name == "openai"

    def test_extract_from_dict_response(self) -> None:
        adapter = OpenAIAdapter()
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        response = {
            "choices": [{"message": {"content": "Hi there!"}}],
            "model": "gpt-4",
            "usage": {"total_tokens": 42},
        }
        result = adapter.extract_turn(messages, response)
        assert result.user_message == "Hello"
        assert result.assistant_response == "Hi there!"
        assert result.model == "gpt-4"
        assert result.tokens_used == 42
        assert result.raw_response == response

    def test_extract_from_object_response(self) -> None:
        adapter = OpenAIAdapter()
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What is Python?"},
        ]
        msg_obj = SimpleNamespace(content="Python is a language.")
        usage_obj = SimpleNamespace(total_tokens=100)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=msg_obj)],
            model="gpt-4o",
            usage=usage_obj,
            model_dump=lambda: {"model": "gpt-4o"},
        )
        result = adapter.extract_turn(messages, response)
        assert result.user_message == "What is Python?"
        assert result.assistant_response == "Python is a language."
        assert result.model == "gpt-4o"
        assert result.tokens_used == 100

    def test_extract_unknown_type_raises(self) -> None:
        adapter = OpenAIAdapter()
        with pytest.raises(AdapterError, match="Unknown OpenAI response type"):
            adapter.extract_turn([{"role": "user", "content": "hi"}], 42)

    def test_extract_missing_key_raises(self) -> None:
        adapter = OpenAIAdapter()
        with pytest.raises(AdapterError, match="extraction failed"):
            adapter.extract_turn(
                [{"role": "user", "content": "hi"}],
                {"choices": []},  # empty choices → IndexError
            )

    def test_extract_no_user_message(self) -> None:
        adapter = OpenAIAdapter()
        messages = [{"role": "system", "content": "sys"}]
        response = {
            "choices": [{"message": {"content": "reply"}}],
            "model": "m",
            "usage": {"total_tokens": 0},
        }
        result = adapter.extract_turn(messages, response)
        assert result.user_message == ""

    def test_extract_object_no_model_dump(self) -> None:
        adapter = OpenAIAdapter()
        messages = [{"role": "user", "content": "hi"}]
        msg_obj = SimpleNamespace(content="reply")
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=msg_obj)],
            model="m",
            usage=SimpleNamespace(total_tokens=10),
        )
        result = adapter.extract_turn(messages, response)
        assert result.raw_response == {}


# ═══════════════════════════════════════════════════════════════════════════════
# AnthropicAdapter
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnthropicAdapter:
    def test_adapter_name(self) -> None:
        assert AnthropicAdapter.adapter_name == "anthropic"

    def test_extract_from_dict_response(self) -> None:
        adapter = AnthropicAdapter()
        messages = [{"role": "user", "content": "Hello Anthropic"}]
        response = {
            "content": [{"text": "I am Claude."}],
            "model": "claude-3-opus",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        result = adapter.extract_turn(messages, response)
        assert result.user_message == "Hello Anthropic"
        assert result.assistant_response == "I am Claude."
        assert result.model == "claude-3-opus"
        assert result.tokens_used == 30
        assert result.raw_response == response

    def test_extract_from_object_response(self) -> None:
        adapter = AnthropicAdapter()
        messages = [{"role": "user", "content": "Hi"}]
        text_block = SimpleNamespace(text="Hello!")
        usage = SimpleNamespace(input_tokens=5, output_tokens=15)
        response = SimpleNamespace(
            content=[text_block],
            model="claude-3-sonnet",
            usage=usage,
            model_dump=lambda: {"model": "claude-3-sonnet"},
        )
        result = adapter.extract_turn(messages, response)
        assert result.assistant_response == "Hello!"
        assert result.model == "claude-3-sonnet"
        assert result.tokens_used == 20

    def test_extract_unknown_type_raises(self) -> None:
        adapter = AnthropicAdapter()
        with pytest.raises(AdapterError, match="Unknown Anthropic response type"):
            adapter.extract_turn([{"role": "user", "content": "hi"}], 123)

    def test_extract_missing_key_raises(self) -> None:
        adapter = AnthropicAdapter()
        with pytest.raises(AdapterError, match="extraction failed"):
            adapter.extract_turn(
                [{"role": "user", "content": "hi"}],
                {"content": []},  # empty content → IndexError
            )

    def test_extract_object_no_model_dump(self) -> None:
        adapter = AnthropicAdapter()
        messages = [{"role": "user", "content": "hi"}]
        text_block = SimpleNamespace(text="reply")
        response = SimpleNamespace(
            content=[text_block],
            model="m",
            usage=SimpleNamespace(input_tokens=1, output_tokens=2),
        )
        result = adapter.extract_turn(messages, response)
        assert result.raw_response == {}


# ═══════════════════════════════════════════════════════════════════════════════
# LangChainAdapter
# ═══════════════════════════════════════════════════════════════════════════════

class TestLangChainAdapter:
    def test_adapter_name(self) -> None:
        assert LangChainAdapter.adapter_name == "langchain"

    def test_extract_from_objects(self) -> None:
        adapter = LangChainAdapter()
        human = SimpleNamespace(content="user question")
        ai = SimpleNamespace(content="ai answer")
        result = adapter.extract_turn(human, ai)
        assert result.user_message == "user question"
        assert result.assistant_response == "ai answer"

    def test_extract_from_plain_strings(self) -> None:
        adapter = LangChainAdapter()
        result = adapter.extract_turn("question", "answer")
        # Without .content attribute, falls back to str()
        assert result.user_message == "question"
        assert result.assistant_response == "answer"


# ═══════════════════════════════════════════════════════════════════════════════
# CapsuleMemoryLangChainMemory
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapsuleMemoryLangChainMemory:
    def _make_memory(self, tmp_path: Path, auto_recall: bool = True):
        from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
        from capsule_memory.storage.local import LocalStorage

        storage = LocalStorage(path=tmp_path)
        config = CapsuleMemoryConfig(storage_path=str(tmp_path))
        cm = CapsuleMemory(storage=storage, config=config, on_skill_trigger=lambda e: None)
        return CapsuleMemoryLangChainMemory(
            cm=cm, user_id="test_user", auto_recall=auto_recall
        )

    def test_memory_variables(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        assert mem.memory_variables == ["history"]

    def test_save_context(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        mem.save_context({"input": "hello"}, {"output": "world"})
        # Should not raise; session internals handle ingest

    def test_load_memory_variables_no_recall(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path, auto_recall=False)
        result = mem.load_memory_variables({"input": "test"})
        assert result == {"history": ""}

    def test_load_memory_variables_empty_query(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path, auto_recall=True)
        result = mem.load_memory_variables({})
        assert result == {"history": ""}

    def test_clear(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        mem.save_context({"input": "a"}, {"output": "b"})
        mem.clear()
        assert mem._session is None
        assert mem._initialized is False

    def test_seal_no_turns(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        # Seal with no turns should not raise
        mem.seal(title="empty")

    def test_custom_memory_key(self, tmp_path: Path) -> None:
        from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
        from capsule_memory.storage.local import LocalStorage

        storage = LocalStorage(path=tmp_path)
        config = CapsuleMemoryConfig(storage_path=str(tmp_path))
        cm = CapsuleMemory(storage=storage, config=config, on_skill_trigger=lambda e: None)
        mem = CapsuleMemoryLangChainMemory(
            cm=cm, user_id="u", memory_key="chat_history"
        )
        assert mem.memory_key == "chat_history"
        assert mem.memory_variables == ["chat_history"]


# ═══════════════════════════════════════════════════════════════════════════════
# SimpleChatMessage
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimpleChatMessage:
    def test_defaults(self) -> None:
        msg = SimpleChatMessage()
        assert msg.role == "user"
        assert msg.content == ""
        assert msg.additional_kwargs == {}

    def test_custom_values(self) -> None:
        msg = SimpleChatMessage(role="assistant", content="hi", additional_kwargs={"k": "v"})
        assert msg.role == "assistant"
        assert msg.content == "hi"


# ═══════════════════════════════════════════════════════════════════════════════
# CapsuleMemoryLlamaIndexMemory
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapsuleMemoryLlamaIndexMemory:
    def _make_memory(self, tmp_path: Path, auto_recall: bool = False):
        from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
        from capsule_memory.storage.local import LocalStorage

        storage = LocalStorage(path=tmp_path)
        config = CapsuleMemoryConfig(storage_path=str(tmp_path))
        cm = CapsuleMemory(storage=storage, config=config, on_skill_trigger=lambda e: None)
        return CapsuleMemoryLlamaIndexMemory(
            cm=cm, user_id="test_user", auto_recall=auto_recall
        )

    def test_put_user_message(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        msg = SimpleChatMessage(role="user", content="hello")
        mem.put(msg)
        assert len(mem._messages) == 1
        assert mem._pending_user_msg == "hello"

    def test_put_user_assistant_pair(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        mem.put(SimpleChatMessage(role="user", content="hello"))
        mem.put(SimpleChatMessage(role="assistant", content="hi"))
        assert len(mem._messages) == 2
        assert mem._pending_user_msg is None

    def test_put_role_normalization(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        # "human" should normalize to "user"
        human_msg = SimpleNamespace(role="human", content="test")
        mem.put(human_msg)
        assert mem._messages[-1].role == "user"
        assert mem._pending_user_msg == "test"

        # "ai" should normalize to "assistant"
        ai_msg = SimpleNamespace(role="ai", content="response")
        mem.put(ai_msg)
        assert mem._messages[-1].role == "assistant"

    def test_get_without_recall(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path, auto_recall=False)
        mem.put(SimpleChatMessage(role="user", content="q"))
        mem.put(SimpleChatMessage(role="assistant", content="a"))
        result = mem.get(input="query")
        # Should just return messages, no system recall msg
        assert all(isinstance(m, SimpleChatMessage) for m in result)

    def test_get_truncation(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path, auto_recall=False)
        mem._token_limit = 1  # ~4 chars
        # Add messages that exceed the limit
        for i in range(5):
            mem.put(SimpleChatMessage(role="user", content="x" * 100))
            mem.put(SimpleChatMessage(role="assistant", content="y" * 100))
        result = mem.get()
        assert len(result) < len(mem._messages)

    def test_get_all(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        mem.put(SimpleChatMessage(role="user", content="a"))
        mem.put(SimpleChatMessage(role="assistant", content="b"))
        all_msgs = mem.get_all()
        assert len(all_msgs) == 2

    def test_reset(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        mem.put(SimpleChatMessage(role="user", content="a"))
        mem.reset()
        assert len(mem._messages) == 0
        assert mem._pending_user_msg is None
        assert mem._session is None

    def test_seal_no_turns(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        mem.seal(title="empty")  # should not raise

    def test_chat_store_key(self, tmp_path: Path) -> None:
        mem = self._make_memory(tmp_path)
        assert mem.chat_store_key == "capsule_memory:test_user"
