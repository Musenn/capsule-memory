from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any

from capsule_memory.adapters.base import BaseAdapter, TurnData
from capsule_memory.exceptions import AdapterError

if TYPE_CHECKING:
    from capsule_memory.api import CapsuleMemory
    from capsule_memory.core.session import SessionTracker

logger = logging.getLogger(__name__)


class LangChainAdapter(BaseAdapter):
    """
    T1.4: Extract TurnData from LangChain AIMessage and HumanMessage objects.

    Usage:
        adapter = LangChainAdapter()
        turn_data = adapter.extract_turn(human_msg, ai_msg)
    """

    adapter_name = "langchain"

    def extract_turn(self, human_message: object, ai_message: object) -> TurnData:
        """
        Extract TurnData from LangChain message objects.

        Args:
            human_message: LangChain HumanMessage or compatible object.
            ai_message: LangChain AIMessage or compatible object.

        Returns:
            Extracted TurnData.

        Raises:
            AdapterError: If extraction fails.
        """
        try:
            user_message = getattr(human_message, "content", str(human_message))
            assistant_response = getattr(ai_message, "content", str(ai_message))
            return TurnData(user_message=user_message, assistant_response=assistant_response)
        except Exception as e:
            raise AdapterError(f"LangChain adapter extraction failed: {e}") from e


class CapsuleMemoryLangChainMemory:
    """
    Drop-in replacement for ConversationBufferMemory that persists to CapsuleMemory.

    Does not inherit from langchain.memory.BaseChatMemory to avoid a hard dependency
    on the langchain package. Instead, it implements the same interface methods
    (save_context, load_memory_variables, clear) that LangChain chains call.

    Usage:
        from capsule_memory import CapsuleMemory
        cm = CapsuleMemory()
        memory = CapsuleMemoryLangChainMemory(cm=cm, user_id="user_123")

        # Use with LangChain
        from langchain.chains import LLMChain
        chain = LLMChain(llm=llm, prompt=prompt, memory=memory)
        chain.run("Hello!")

    Args:
        cm: CapsuleMemory instance.
        user_id: User identifier for session management.
        session_id: Optional custom session ID.
        memory_key: Key used by LangChain to inject history. Defaults to "history".
        auto_recall: Whether to auto-recall relevant context on load. Defaults to True.
    """

    memory_key: str = "history"

    def __init__(
        self,
        cm: CapsuleMemory,
        user_id: str,
        session_id: str | None = None,
        memory_key: str = "history",
        auto_recall: bool = True,
    ) -> None:
        self._cm = cm
        self._user_id = user_id
        self._session_ctx = cm.session(user_id, session_id=session_id, auto_seal_on_exit=False)
        self._session: SessionTracker | None = None
        self.memory_key = memory_key
        self._auto_recall = auto_recall
        self._initialized = False

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
            if not hasattr(self, "_bg_lock"):
                self._bg_lock = threading.Lock()
            with self._bg_lock:
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

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, Any]) -> None:
        """
        Called by LangChain after each chain run to save the interaction.

        Args:
            inputs: Chain input dict (typically contains "input" key).
            outputs: Chain output dict (typically contains "output" key).
        """
        session = self._ensure_session()
        user_msg = inputs.get("input", inputs.get("question", str(inputs)))
        ai_msg = outputs.get("output", outputs.get("text", str(outputs)))
        self._run_async(session.ingest(str(user_msg), str(ai_msg)))

    def load_memory_variables(self, inputs: dict[str, Any]) -> dict[str, str]:
        """
        Called by LangChain before each chain run to load history context.

        Args:
            inputs: Chain input dict used for recall query.

        Returns:
            Dict with memory_key mapping to recalled context text.
        """
        if not self._auto_recall:
            return {self.memory_key: ""}

        query = inputs.get("input", inputs.get("question", ""))
        if not query:
            return {self.memory_key: ""}

        try:
            result = self._run_async(
                self._cm.recall(str(query), user_id=self._user_id)
            )
            return {self.memory_key: result.get("prompt_injection", "")}
        except Exception as e:
            logger.warning("Failed to recall context: %s", e)
            return {self.memory_key: ""}

    def clear(self) -> None:
        """
        Clear the current session state (does not delete sealed capsules).

        Creates a fresh session tracker for subsequent interactions.
        """
        self._session = None
        self._session_ctx = self._cm.session(
            self._user_id, auto_seal_on_exit=False
        )
        self._initialized = False

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
    def memory_variables(self) -> list[str]:
        """Return the list of memory variable keys (LangChain interface)."""
        return [self.memory_key]
