from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from capsule_memory.exceptions import SessionError
from capsule_memory.models.capsule import Capsule, CapsuleType
from capsule_memory.models.events import SkillTriggerEvent
from capsule_memory.models.memory import ConversationTurn

if TYPE_CHECKING:
    from capsule_memory.core.extractor import MemoryExtractor
    from capsule_memory.core.memory_compressor import MemoryCompressor
    from capsule_memory.core.skill_detector import SkillDetector
    from capsule_memory.core.skill_refiner import SkillRefiner
    from capsule_memory.notifier.base import BaseNotifier
    from capsule_memory.storage.base import BaseStorage

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    user_id: str
    session_id: str = field(
        default_factory=lambda: (
            f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        )
    )
    agent_id: str | None = None
    origin_platform: str = "unknown"
    max_turns: int = 500
    auto_seal_on_exit: bool = True
    include_raw_turns: bool = False


@dataclass
class SessionState:
    config: SessionConfig
    turns: list[ConversationTurn] = field(default_factory=list)
    draft_capsule: Capsule | None = None
    pending_triggers: list[SkillTriggerEvent] = field(default_factory=list)
    confirmed_skill_payloads: list[dict[str, Any]] = field(default_factory=list)
    never_trigger_patterns: set[str] = field(default_factory=set)
    extra_context: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True


class SessionTracker:
    """Tracks a single user session, managing ingestion, skill detection, and sealing."""

    def __init__(
        self,
        config: SessionConfig,
        storage: BaseStorage,
        extractor: MemoryExtractor,
        skill_detector: SkillDetector,
        notifier: BaseNotifier,
        skill_refiner: SkillRefiner | None = None,
        compressor: MemoryCompressor | None = None,
    ) -> None:
        self.config = config
        self.state = SessionState(config=config)
        self.storage: BaseStorage = storage
        self.extractor: MemoryExtractor = extractor
        self.skill_detector: SkillDetector = skill_detector
        self.notifier: BaseNotifier = notifier
        self.skill_refiner: SkillRefiner | None = skill_refiner
        self.compressor: MemoryCompressor | None = compressor
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def ingest(
        self, user_message: str, assistant_response: str, tokens: int = 0
    ) -> ConversationTurn:
        """
        Ingest a conversation turn pair into the session.

        Args:
            user_message: The user's message.
            assistant_response: The AI's response.
            tokens: Token count for the exchange.

        Returns:
            The user ConversationTurn.

        Raises:
            SessionError: If session is already sealed.
        """
        if not self.state.is_active:
            raise SessionError("Cannot ingest into a sealed session")

        user_turn = ConversationTurn(
            turn_id=len(self.state.turns) + 1,
            role="user",
            content=user_message,
            tokens=tokens,
        )
        self.state.turns.append(user_turn)

        assistant_turn = ConversationTurn(
            turn_id=len(self.state.turns) + 1,
            role="assistant",
            content=assistant_response,
        )
        self.state.turns.append(assistant_turn)

        if self.state.draft_capsule is not None:
            self.state.draft_capsule.metadata.turn_count = len(self.state.turns)

        task = asyncio.create_task(self._detect_skill_background(assistant_turn))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        if self.compressor is not None:
            ct = asyncio.create_task(
                self._compress_background([user_turn, assistant_turn])
            )
            self._background_tasks.add(ct)
            ct.add_done_callback(self._background_tasks.discard)

        return user_turn

    async def _detect_skill_background(self, turn: ConversationTurn) -> None:
        """Run skill detection in background, never raises to caller."""
        try:
            event = await self.skill_detector.check(
                turn, self.state.turns, session_id=self.config.session_id
            )
            if event is None:
                return
            if event.trigger_rule.value in self.state.never_trigger_patterns:
                return
            self.state.pending_triggers.append(event)
            await self.notifier.notify(event)
        except Exception as e:
            logger.warning("Background skill detection failed: %s", e)

    async def _compress_background(self, turns: list[ConversationTurn]) -> None:
        """Run incremental memory compression in background."""
        try:
            if self.compressor is not None:
                await self.compressor.ingest(turns)
        except Exception as e:
            logger.warning("Background compression failed: %s", e)

    async def snapshot(self) -> dict[str, Any]:
        """
        Return a snapshot of the current session state.

        Returns:
            Dict with session_id, user_id, turn_count, is_active,
            pending_triggers, confirmed_skills, started_at.
        """
        return {
            "session_id": self.config.session_id,
            "user_id": self.config.user_id,
            "turn_count": len(self.state.turns),
            "is_active": self.state.is_active,
            "pending_triggers": len(self.state.pending_triggers),
            "confirmed_skills": len(self.state.confirmed_skill_payloads),
            "started_at": self.state.started_at.isoformat(),
        }

    async def seal(
        self,
        title: str = "",
        tags: list[str] | None = None,
        capsule_type: CapsuleType = CapsuleType.HYBRID,
        pre_extracted: "MemoryPayload | None" = None,
    ) -> Capsule:
        """
        Seal the current session into a capsule.

        Args:
            title: Capsule title.
            tags: Tags for the capsule.
            capsule_type: Type of capsule to create.
            pre_extracted: Pre-extracted MemoryPayload from the host LLM.
                If provided, skips the built-in extraction entirely.

        Returns:
            The sealed Capsule.

        Raises:
            SessionError: If session is already sealed.
        """
        if not self.state.is_active:
            raise SessionError("Cannot seal an already sealed session")

        if self._background_tasks:
            await asyncio.wait(self._background_tasks, timeout=4.7)

        if pre_extracted is not None:
            memory_payload = pre_extracted
            # Always fill entities and timeline from turns
            if not memory_payload.entities:
                memory_payload.entities = self.extractor._extract_entities_regex(
                    self.state.turns
                )
            if not memory_payload.timeline:
                memory_payload.timeline = self.extractor._build_timeline(
                    self.state.turns
                )
        elif self.compressor is not None:
            memory_payload = await self.compressor.finalize()
            memory_payload.entities = self.extractor._extract_entities_regex(
                self.state.turns
            )
            memory_payload.timeline = self.extractor._build_timeline(self.state.turns)
        else:
            memory_payload = await self.extractor.extract(self.state.turns)

        if self.state.extra_context:
            memory_payload.context_summary += "\n" + self.state.extra_context

        from capsule_memory.core.builder import CapsuleBuilder

        if self.state.confirmed_skill_payloads or capsule_type == CapsuleType.HYBRID:
            capsule = CapsuleBuilder.build_hybrid(
                self.config,
                memory_payload,
                self.state.confirmed_skill_payloads,
                title=title or f"Session {self.config.session_id}",
                tags=tags or [],
            )
        else:
            capsule = CapsuleBuilder.build_memory(
                self.config,
                memory_payload,
                title=title or f"Session {self.config.session_id}",
                tags=tags or [],
            )

        capsule.metadata.turn_count = len(self.state.turns)

        if not self.config.include_raw_turns:
            if "raw_turns" in capsule.payload:
                capsule.payload["raw_turns"] = []
            elif "memory" in capsule.payload and "raw_turns" in capsule.payload["memory"]:
                capsule.payload["memory"]["raw_turns"] = []

        from capsule_memory.models.capsule import CapsuleStatus
        capsule.lifecycle.sealed_at = datetime.now(timezone.utc)
        capsule.lifecycle.status = CapsuleStatus.SEALED
        capsule.integrity.checksum = capsule.compute_checksum()

        await self.storage.save(capsule)
        self.state.is_active = False

        return capsule

    async def recall(self, query: str, top_k: int = 5, include_skills: bool = True) -> dict[str, Any]:
        """
        Recall historical memories related to the query.

        Args:
            query: The query string.
            top_k: Number of results to return.
            include_skills: Whether to include skills in results.

        Returns:
            Dict with facts, skills, summary, prompt_injection, sources.
        """
        results = await self.storage.search(query, user_id=self.config.user_id, top_k=top_k)
        facts = []
        skills = []
        summaries = []
        sources = []
        for capsule, score in results:
            u = capsule.to_universal_memory()
            facts.extend(u["facts"])
            summaries.append(u["summary"])
            if include_skills:
                skills.extend(u["skills"])
            sources.append(capsule.capsule_id)

        combined_summary = "\n".join(s for s in summaries if s)
        prompt_injection_lines = ["=== Historical Memory Context ==="]
        if combined_summary:
            prompt_injection_lines.append(f"Background: {combined_summary[:500]}")
        if facts:
            prompt_injection_lines.append("Key Facts:")
            for f in facts[:15]:
                prompt_injection_lines.append(f"  - {f['key']}: {f['value']}")
        if skills and include_skills:
            prompt_injection_lines.append("Available Skills:")
            for s in skills[:5]:
                prompt_injection_lines.append(f"  [{s['name']}] {s['description']}")
        prompt_injection_lines.append("=== Historical Memory End ===")

        return {
            "facts": facts[:20],
            "skills": skills[:10],
            "summary": combined_summary[:500],
            "prompt_injection": "\n".join(prompt_injection_lines),
            "sources": sources,
        }

    async def confirm_skill_trigger(self, event_id: str, resolution: str) -> Capsule | None:
        """
        Confirm or dismiss a skill trigger event.

        Args:
            event_id: The event ID to resolve.
            resolution: One of extract_skill, merge_memory, extract_hybrid, ignore, never.

        Returns:
            None (skills are merged during seal).

        Raises:
            SessionError: If event not found.
        """
        event = None
        for e in self.state.pending_triggers:
            if e.event_id == event_id:
                event = e
                break
        if event is None:
            raise SessionError(f"Event {event_id} not found")

        event.resolved = True
        event.resolution = resolution  # type: ignore[assignment]

        if resolution in ("extract_skill", "extract_hybrid"):
            if self.skill_refiner is not None:
                skill_payload = await self.skill_refiner.refine(
                    event.skill_draft, self.state.turns, self.config.session_id
                )
            else:
                from capsule_memory.core.builder import CapsuleBuilder
                skill_payload = CapsuleBuilder.build_skill_from_draft(
                    self.config, event.skill_draft, self.state.turns
                )
            self.state.confirmed_skill_payloads.append(skill_payload.model_dump())
            return None
        elif resolution == "merge_memory":
            self.state.extra_context += "\n" + event.skill_draft.preview
            return None
        elif resolution == "ignore":
            return None
        elif resolution == "never":
            self.state.never_trigger_patterns.add(event.trigger_rule.value)
            return None
        return None

    async def __aenter__(self) -> SessionTracker:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        if (
            self.config.auto_seal_on_exit
            and self.state.is_active
            and len(self.state.turns) > 0
        ):
            try:
                await self.seal()
            except Exception as e:
                logger.error("Auto-seal failed on session exit: %s", e)


class SessionContextManager:
    def __init__(self, tracker: SessionTracker) -> None:
        self._tracker = tracker

    async def __aenter__(self) -> SessionTracker:
        return await self._tracker.__aenter__()

    async def __aexit__(self, *args: Any) -> None:
        await self._tracker.__aexit__(*args)
