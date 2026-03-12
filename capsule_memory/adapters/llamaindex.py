"""
LlamaIndex deep adapter for CapsuleMemory.

Provides CapsuleMemoryLlamaIndexMemory — a drop-in replacement for
ChatMemoryBuffer that persists conversation history to CapsuleMemory capsules.

Does not inherit from llama_index.core.memory.ChatMemoryBuffer to avoid
a hard dependency on the llama_index package.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from capsule_memory.api import CapsuleMemory
    from capsule_memory.core.session import SessionTracker

logger = logging.getLogger(__name__)


@dataclass
class SimpleChatMessage:
    """
    Lightweight chat message compatible with LlamaIndex ChatMessage interface.

    Attributes:
        role: Message role (user, assistant, system).
        content: Message text content.
        additional_kwargs: Extra metadata.
    """

    role: str = "user"
    content: str = ""
    additional_kwargs: dict[str, Any] = field(default_factory=dict)


class CapsuleMemoryLlamaIndexMemory:
    """
    Drop-in replacement for ChatMemoryBuffer that writes to CapsuleMemory.

    Implements the LlamaIndex memory interface (put, get, get_all, reset)
    without inheriting from any LlamaIndex class to avoid hard dependencies.

    Usage:
        from capsule_memory import CapsuleMemory
        cm = CapsuleMemory()
        memory = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="user_123")

        # Use with LlamaIndex
        from llama_index.core.agent import ReActAgent
        agent = ReActAgent.from_tools(tools, memory=memory)

    Args:
        cm: CapsuleMemory instance.
        user_id: User identifier for session management.
        session_id: Optional custom session ID.
        token_limit: Maximum tokens to return in get(). Defaults to 3000.
        auto_recall: Whether to auto-recall from sealed capsules. Defaults to True.
    """

    def __init__(
        self,
        cm: CapsuleMemory,
        user_id: str,
        session_id: str | None = None,
        token_limit: int = 3000,
        auto_recall: bool = True,
    ) -> None:
        self._cm = cm
        self._user_id = user_id
        self._token_limit = token_limit
        self._auto_recall = auto_recall
        self._messages: list[SimpleChatMessage] = []
        self._session_ctx = cm.session(user_id, session_id=session_id, auto_seal_on_exit=False)
        self._session: SessionTracker | None = None
        self._pending_user_msg: str | None = None

    def _ensure_session(self) -> SessionTracker:
        """Ensure the session tracker is initialized."""
        if self._session is None:
            self._session = self._session_ctx._tracker
        return self._session

    def _run_async(self, coro: Any) -> Any:
        """Run an async coroutine from sync context.

        Uses a dedicated background event loop thread when called from
        within an already-running loop (e.g. Jupyter, async frameworks).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import threading

            if not hasattr(self, "_bg_loop"):
                self._bg_loop = asyncio.new_event_loop()
                t = threading.Thread(
                    target=self._bg_loop.run_forever, daemon=True
                )
                t.start()
            future = asyncio.run_coroutine_threadsafe(coro, self._bg_loop)
            return future.result()
        else:
            return asyncio.run(coro)

    def put(self, message: Any) -> None:
        """
        Add a message to the memory buffer.

        When receiving alternating user/assistant messages, pairs them
        and ingests into the CapsuleMemory session.

        Args:
            message: A ChatMessage-like object with role and content attributes,
                     or a SimpleChatMessage instance.
        """
        role = getattr(message, "role", "user")
        content = getattr(message, "content", str(message))

        # Normalize role to string
        role_str = str(role).lower()
        if "human" in role_str or "user" in role_str:
            role_str = "user"
        elif "ai" in role_str or "assistant" in role_str:
            role_str = "assistant"

        msg = SimpleChatMessage(role=role_str, content=content)
        self._messages.append(msg)

        # Pair user + assistant messages for ingestion
        if role_str == "user":
            self._pending_user_msg = content
        elif role_str == "assistant" and self._pending_user_msg is not None:
            session = self._ensure_session()
            try:
                self._run_async(session.ingest(self._pending_user_msg, content))
            except Exception as e:
                logger.warning("Failed to ingest turn: %s", e)
            self._pending_user_msg = None

    def get(self, input: str | None = None, **kwargs: Any) -> list[Any]:
        """
        Get chat history messages, optionally enriched with recalled context.

        When auto_recall is enabled and input is provided, prepends a system
        message with recalled context from sealed capsules.

        Args:
            input: Current user query (used for context recall).

        Returns:
            List of SimpleChatMessage objects representing the conversation history.
        """
        result: list[SimpleChatMessage] = []

        # Recall from sealed capsules if enabled
        if self._auto_recall and input:
            try:
                recall_result = self._run_async(
                    self._cm.recall(input, user_id=self._user_id)
                )
                prompt_injection = recall_result.get("prompt_injection", "")
                if prompt_injection:
                    result.append(
                        SimpleChatMessage(role="system", content=prompt_injection)
                    )
            except Exception as e:
                logger.warning("Failed to recall context: %s", e)

        # Truncate to approximate token limit (rough estimate: 1 token ≈ 4 chars)
        char_limit = self._token_limit * 4
        total_chars = 0
        truncated: list[SimpleChatMessage] = []

        for msg in reversed(self._messages):
            total_chars += len(msg.content)
            if total_chars > char_limit:
                break
            truncated.insert(0, msg)

        result.extend(truncated)
        return result

    def get_all(self) -> list[Any]:
        """
        Get all messages without truncation.

        Returns:
            Full list of SimpleChatMessage objects.
        """
        return list(self._messages)

    def reset(self) -> None:
        """
        Reset the memory buffer and create a fresh session.

        Does not delete sealed capsules.
        """
        self._messages.clear()
        self._pending_user_msg = None
        self._session = None
        self._session_ctx = self._cm.session(
            self._user_id, auto_seal_on_exit=False
        )

    def seal(self, title: str = "", tags: list[str] | None = None) -> None:
        """
        Seal the current session into a persistent capsule.

        Args:
            title: Optional capsule title.
            tags: Optional capsule tags.
        """
        session = self._ensure_session()
        if session.state.is_active and len(session.state.turns) > 0:
            self._run_async(session.seal(title=title, tags=tags or []))

    @property
    def chat_store_key(self) -> str:
        """Compatible with LlamaIndex ChatMemoryBuffer interface."""
        return f"capsule_memory:{self._user_id}"
