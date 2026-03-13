from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4 as _uuid4
from capsule_memory.models.capsule import Capsule
from capsule_memory.storage.base import BaseStorage
from capsule_memory.storage.local import LocalStorage
from capsule_memory.adapters.base import BaseAdapter
from capsule_memory.adapters.raw import RawAdapter
from capsule_memory.notifier.base import BaseNotifier
from capsule_memory.notifier.callback import CallbackNotifier
from capsule_memory.notifier.cli import CLINotifier
from capsule_memory.notifier.multi import MultiNotifier
from capsule_memory.core.extractor import MemoryExtractor, ExtractorConfig
from capsule_memory.core.memory_compressor import MemoryCompressor, CompressorConfig
from capsule_memory.core.skill_detector import SkillDetector
from capsule_memory.core.skill_refiner import SkillRefiner
from capsule_memory.core.session import SessionConfig, SessionTracker, SessionContextManager
from capsule_memory.core.store import CapsuleStore

logger = logging.getLogger(__name__)


@dataclass
class CapsuleMemoryConfig:
    storage_type: Literal["local", "sqlite", "redis", "qdrant"] = "local"
    storage_path: str = "~/.capsules"
    storage_url: str = ""
    skill_detection: bool = True
    enable_llm_scorer: bool = False
    llm_model: str = ""
    default_notifier: Literal["cli", "none"] = "cli"
    encrypt_by_default: bool = False
    compress_threshold: int = 8000
    compress_layer_max: int = 6000
    default_user: str = "default"

    @classmethod
    def from_env(cls) -> CapsuleMemoryConfig:
        """Build config from environment variables (env vars take priority over defaults)."""
        return cls(
            storage_type=os.getenv("CAPSULE_STORAGE_TYPE", "local"),        # type: ignore[arg-type]
            storage_path=os.getenv("CAPSULE_STORAGE_PATH", "~/.capsules"),
            storage_url=os.getenv("CAPSULE_STORAGE_URL", ""),
            skill_detection=os.getenv("CAPSULE_SKILL_DETECTION", "true").lower() == "true",
            enable_llm_scorer=os.getenv("CAPSULE_SKILL_LLM_SCORE", "false").lower() == "true",
            llm_model=os.getenv("CAPSULE_LLM_MODEL", ""),
            default_notifier=os.getenv("CAPSULE_NOTIFIER", "cli"),          # type: ignore[arg-type]
            encrypt_by_default=os.getenv("CAPSULE_ENCRYPT_DEFAULT", "false").lower() == "true",
            compress_threshold=int(os.getenv("CAPSULE_COMPRESS_THRESHOLD", "8000")),
            compress_layer_max=int(os.getenv("CAPSULE_COMPRESS_LAYER_MAX", "6000")),
            default_user=os.getenv("CAPSULE_DEFAULT_USER", "default"),
        )


def _build_storage(config: CapsuleMemoryConfig) -> BaseStorage:
    """Create the corresponding Storage instance based on config.storage_type."""
    if config.storage_type == "local":
        return LocalStorage(path=config.storage_path)
    elif config.storage_type == "sqlite":
        from capsule_memory.storage.sqlite import SQLiteStorage
        return SQLiteStorage(path=config.storage_path)
    elif config.storage_type == "redis":
        from capsule_memory.storage.redis_store import RedisStorage
        return RedisStorage(url=config.storage_url)
    elif config.storage_type == "qdrant":
        from capsule_memory.storage.qdrant_store import QdrantStorage
        return QdrantStorage(url=config.storage_url)
    else:
        raise ValueError(f"Unknown storage_type: {config.storage_type}. "
                         f"Valid values: local, sqlite, redis, qdrant")


class CapsuleMemory:
    """
    Main entry point for the CapsuleMemory system.

    Simplest usage (zero config, local file storage):
        cm = CapsuleMemory()
        async with cm.session("user_123") as session:
            await session.ingest(user_msg, ai_response)
        # auto-seals on exiting the with block

    With callback notification:
        cm = CapsuleMemory(on_skill_trigger=lambda evt: print(evt.skill_draft.suggested_name))
    """

    def __init__(
        self,
        adapter: BaseAdapter | None = None,
        storage: BaseStorage | None = None,
        config: CapsuleMemoryConfig | None = None,
        skill_detection: bool = True,
        on_skill_trigger: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config or CapsuleMemoryConfig.from_env()
        self._adapter = adapter or RawAdapter()
        self._storage = storage or _build_storage(self._config)
        self._store = CapsuleStore(self._storage)
        self._extractor = MemoryExtractor(ExtractorConfig(model=self._config.llm_model))
        self._skill_refiner = SkillRefiner(model=self._config.llm_model)
        self._skill_detector = SkillDetector(
            enable_llm_scorer=self._config.enable_llm_scorer,
            llm_model=self._config.llm_model,
        ) if skill_detection and self._config.skill_detection else SkillDetector(rules=[])

        self._managed_sessions: dict[str, SessionTracker] = {}

        notifiers: list[BaseNotifier] = []
        if on_skill_trigger is not None:
            notifiers.append(CallbackNotifier(on_skill_trigger))
        if self._config.default_notifier == "cli" and not notifiers:
            notifiers.append(CLINotifier())
        self._notifier: BaseNotifier = MultiNotifier(notifiers) if notifiers else CLINotifier()

    def session(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        origin_platform: str = "unknown",
        auto_seal_on_exit: bool = True,
        include_raw_turns: bool = False,
    ) -> SessionContextManager:
        """Create and return a SessionContextManager, supports async with syntax."""
        resolved_user_id = user_id or self._config.default_user
        # Patch #3: safely generate session_id without accessing dataclass internals
        resolved_session_id = session_id if session_id else f"sess_{_uuid4().hex[:12]}"
        config = SessionConfig(
            user_id=resolved_user_id,
            session_id=resolved_session_id,
            agent_id=agent_id,
            origin_platform=origin_platform,
            auto_seal_on_exit=auto_seal_on_exit,
            include_raw_turns=include_raw_turns,
        )
        compressor = (
            MemoryCompressor(
                model=self._config.llm_model,
                config=CompressorConfig(
                    compress_threshold=self._config.compress_threshold,
                    max_layer_tokens=self._config.compress_layer_max,
                ),
            )
            if self._config.llm_model else None
        )
        tracker = SessionTracker(
            config=config,
            storage=self._storage,
            extractor=self._extractor,
            skill_detector=self._skill_detector,
            notifier=self._notifier,
            skill_refiner=self._skill_refiner,
            compressor=compressor,
        )
        return SessionContextManager(tracker)

    # ─── Managed sessions for remember() ─────────────────────────────────

    async def remember(
        self,
        user_message: str,
        assistant_response: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        One-call passive memory: ingest a turn, auto-recall on first turn.

        Call this once per exchange. It handles session lifecycle automatically:
        - Creates a session on first call for a user_id
        - Recalls relevant history on the first turn (returned in result)
        - Subsequent calls add turns to the same session

        To persist the session, call seal_session() or let the process exit
        (MCP/REST servers auto-seal on shutdown).

        Args:
            user_message: The user's message.
            assistant_response: The AI's response.
            user_id: User identifier.
            session_id: Optional session ID (auto-generated if omitted).

        Returns:
            Dict with turn_id, session_id, total_turns.
            On first turn: also recalled_context and recalled_facts_count.

        Example::

            cm = CapsuleMemory()
            result = await cm.remember("I use vim", "Great editor choice!", user_id="alice")
            if "recalled_context" in result:
                print("History:", result["recalled_context"])
        """
        user_id = user_id or self._config.default_user
        is_new = False
        if user_id not in self._managed_sessions or not self._managed_sessions[user_id].state.is_active:
            resolved_sid = session_id or f"sess_{_uuid4().hex[:12]}"
            ctx = self.session(user_id=user_id, session_id=resolved_sid, auto_seal_on_exit=False)
            tracker = ctx._tracker
            self._managed_sessions[user_id] = tracker
            is_new = True

        tracker = self._managed_sessions[user_id]
        turn = await tracker.ingest(user_message, assistant_response)

        result: dict[str, Any] = {
            "turn_id": turn.turn_id,
            "session_id": tracker.config.session_id,
            "total_turns": len(tracker.state.turns),
        }

        if is_new:
            try:
                recall_result = await self.recall(user_message, user_id=user_id, top_k=3)
                recalled_facts = recall_result.get("facts", [])
                if recalled_facts:
                    result["recalled_context"] = recall_result.get("prompt_injection", "")
                    result["recalled_facts_count"] = len(recalled_facts)
            except Exception:
                logger.debug("Auto-recall failed on new session, skipping", exc_info=True)

        return result

    async def seal_session(
        self,
        user_id: str | None = None,
        title: str = "",
        tags: list[str] | None = None,
        pre_extracted: Any = None,
    ) -> Capsule | None:
        """
        Seal the managed session for a user (companion to remember()).

        Args:
            user_id: User whose session to seal.
            title: Capsule title.
            tags: Tags for the capsule.
            pre_extracted: Optional MemoryPayload with pre-extracted facts/summary.

        Returns:
            The sealed Capsule, or None if no active session exists.
        """
        user_id = user_id or self._config.default_user
        if user_id not in self._managed_sessions:
            return None
        tracker = self._managed_sessions[user_id]
        if not tracker.state.is_active or len(tracker.state.turns) == 0:
            return None
        capsule = await tracker.seal(title=title, tags=tags or [], pre_extracted=pre_extracted)
        del self._managed_sessions[user_id]
        return capsule

    async def recall(self, query: str, user_id: str | None = None, top_k: int = 5) -> dict[str, Any]:
        """Recall historical memories across sessions (no new session required)."""
        resolved_user_id = user_id or self._config.default_user
        return await self._store.get_context_for_injection(query, resolved_user_id, top_k)

    async def export_capsule(
        self,
        capsule_id: str,
        output_path: str,
        format: Literal["json", "msgpack", "universal", "prompt"] = "json",
        encrypt: bool = False,
        passphrase: str = "",
    ) -> Path:
        """Export a capsule to file."""
        return await self._storage.export_capsule(
            capsule_id, output_path, format, encrypt, passphrase
        )

    async def import_capsule(
        self,
        file_path: str,
        user_id: str | None = None,
        passphrase: str = "",
    ) -> Capsule:
        """Import a capsule from file."""
        resolved_user_id = user_id or self._config.default_user
        return await self._storage.import_capsule_file(file_path, resolved_user_id, passphrase)

    @property
    def store(self) -> CapsuleStore:
        """Direct access to the underlying CapsuleStore for advanced operations (merge/diff/fork/list)."""
        return self._store
