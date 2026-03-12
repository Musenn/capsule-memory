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
from capsule_memory.core.skill_detector import SkillDetector
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
    extractor_model: str = "gpt-4o-mini"
    default_notifier: Literal["cli", "none"] = "cli"
    encrypt_by_default: bool = False

    @classmethod
    def from_env(cls) -> CapsuleMemoryConfig:
        """Build config from environment variables (env vars take priority over defaults)."""
        return cls(
            storage_type=os.getenv("CAPSULE_STORAGE_TYPE", "local"),        # type: ignore[arg-type]
            storage_path=os.getenv("CAPSULE_STORAGE_PATH", "~/.capsules"),
            storage_url=os.getenv("CAPSULE_STORAGE_URL", ""),
            skill_detection=os.getenv("CAPSULE_SKILL_DETECTION", "true").lower() == "true",
            enable_llm_scorer=os.getenv("CAPSULE_SKILL_LLM_SCORE", "false").lower() == "true",
            extractor_model=os.getenv("CAPSULE_EXTRACTOR_MODEL", "gpt-4o-mini"),
            default_notifier=os.getenv("CAPSULE_NOTIFIER", "cli"),          # type: ignore[arg-type]
            encrypt_by_default=os.getenv("CAPSULE_ENCRYPT_DEFAULT", "false").lower() == "true",
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
        self._extractor = MemoryExtractor(ExtractorConfig(model=self._config.extractor_model))
        self._skill_detector = SkillDetector(
            enable_llm_scorer=self._config.enable_llm_scorer
        ) if skill_detection and self._config.skill_detection else SkillDetector(rules=[])

        notifiers: list[BaseNotifier] = []
        if on_skill_trigger is not None:
            notifiers.append(CallbackNotifier(on_skill_trigger))
        if self._config.default_notifier == "cli" and not notifiers:
            notifiers.append(CLINotifier())
        self._notifier: BaseNotifier = MultiNotifier(notifiers) if notifiers else CLINotifier()

    def session(
        self,
        user_id: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        origin_platform: str = "unknown",
        auto_seal_on_exit: bool = True,
        include_raw_turns: bool = False,
    ) -> SessionContextManager:
        """Create and return a SessionContextManager, supports async with syntax."""
        # Patch #3: safely generate session_id without accessing dataclass internals
        resolved_session_id = session_id if session_id else f"sess_{_uuid4().hex[:12]}"
        config = SessionConfig(
            user_id=user_id,
            session_id=resolved_session_id,
            agent_id=agent_id,
            origin_platform=origin_platform,
            auto_seal_on_exit=auto_seal_on_exit,
            include_raw_turns=include_raw_turns,
        )
        tracker = SessionTracker(
            config=config,
            storage=self._storage,
            extractor=self._extractor,
            skill_detector=self._skill_detector,
            notifier=self._notifier,
        )
        return SessionContextManager(tracker)

    async def recall(self, query: str, user_id: str, top_k: int = 5) -> dict[str, Any]:
        """Recall historical memories across sessions (no new session required)."""
        return await self._store.get_context_for_injection(query, user_id, top_k)

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
        user_id: str,
        passphrase: str = "",
    ) -> Capsule:
        """Import a capsule from file."""
        return await self._storage.import_capsule_file(file_path, user_id, passphrase)

    @property
    def store(self) -> CapsuleStore:
        """Direct access to the underlying CapsuleStore for advanced operations (merge/diff/fork/list)."""
        return self._store
