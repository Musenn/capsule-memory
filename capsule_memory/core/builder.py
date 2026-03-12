from __future__ import annotations
import re
import logging
from datetime import datetime, timezone
from typing import Any
from capsule_memory.models.capsule import (
    Capsule, CapsuleIdentity, CapsuleLifecycle, CapsuleMetadata,
    CapsuleStatus, CapsuleType,
)
from capsule_memory.models.events import SkillDraft
from capsule_memory.models.memory import ConversationTurn, MemoryPayload
from capsule_memory.models.skill import SkillPayload
from capsule_memory.core.session import SessionConfig

logger = logging.getLogger(__name__)


class CapsuleBuilder:
    """Factory class for building capsules from various sources."""

    @staticmethod
    def build_memory(
        config: SessionConfig,
        memory_payload: MemoryPayload,
        title: str = "",
        tags: list[str] | None = None,
    ) -> Capsule:
        """
        Build a MEMORY type capsule from extracted MemoryPayload.

        Args:
            config: Session configuration.
            memory_payload: Extracted memory payload.
            title: Capsule title.
            tags: Tags for the capsule.

        Returns:
            A sealed MEMORY Capsule.
        """
        capsule = Capsule(
            capsule_type=CapsuleType.MEMORY,
            identity=CapsuleIdentity(
                user_id=config.user_id,
                agent_id=config.agent_id,
                session_id=config.session_id,
                origin_platform=config.origin_platform,
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.SEALED,
                sealed_at=datetime.now(timezone.utc),
            ),
            metadata=CapsuleMetadata(
                title=title or f"Session {config.session_id}",
                tags=tags or [],
            ),
            payload=memory_payload.model_dump(mode="json"),
        )
        capsule.integrity.checksum = capsule.compute_checksum()
        return capsule

    @staticmethod
    def build_skill(
        config: SessionConfig,
        skill_payload: SkillPayload,
        tags: list[str] | None = None,
    ) -> Capsule:
        """
        Build a SKILL type capsule from a SkillPayload.

        Args:
            config: Session configuration.
            skill_payload: The skill payload.
            tags: Tags for the capsule.

        Returns:
            A sealed SKILL Capsule.
        """
        capsule = Capsule(
            capsule_type=CapsuleType.SKILL,
            identity=CapsuleIdentity(
                user_id=config.user_id,
                agent_id=config.agent_id,
                session_id=config.session_id,
                origin_platform=config.origin_platform,
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.SEALED,
                sealed_at=datetime.now(timezone.utc),
            ),
            metadata=CapsuleMetadata(
                title=skill_payload.skill_name,
                tags=tags or [],
            ),
            payload=skill_payload.model_dump(mode="json"),
        )
        capsule.integrity.checksum = capsule.compute_checksum()
        return capsule

    @staticmethod
    def build_hybrid(
        config: SessionConfig,
        memory_payload: MemoryPayload,
        skill_payloads: list[dict[str, Any]],
        title: str = "",
        tags: list[str] | None = None,
    ) -> Capsule:
        """
        Build a HYBRID type capsule containing both memory and skills.

        Args:
            config: Session configuration.
            memory_payload: Extracted memory payload.
            skill_payloads: List of skill payload dicts.
            title: Capsule title.
            tags: Tags for the capsule.

        Returns:
            A sealed HYBRID Capsule.
        """
        capsule = Capsule(
            capsule_type=CapsuleType.HYBRID,
            identity=CapsuleIdentity(
                user_id=config.user_id,
                agent_id=config.agent_id,
                session_id=config.session_id,
                origin_platform=config.origin_platform,
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.SEALED,
                sealed_at=datetime.now(timezone.utc),
            ),
            metadata=CapsuleMetadata(
                title=title or f"Session {config.session_id}",
                tags=tags or [],
            ),
            payload={
                "memory": memory_payload.model_dump(mode="json"),
                "skills": skill_payloads,
            },
        )
        capsule.integrity.checksum = capsule.compute_checksum()
        return capsule

    @staticmethod
    def build_skill_from_draft(
        config: SessionConfig,
        draft: SkillDraft,
        source_turns: list[ConversationTurn],
    ) -> SkillPayload:
        """
        Build a SkillPayload from a SkillDraft and source conversation turns.

        Args:
            config: Session configuration.
            draft: The skill draft from the detector.
            source_turns: All conversation turns in the session.

        Returns:
            A SkillPayload ready for capsule building.
        """
        # Find assistant turns matching source_turn IDs
        assistant_contents = []
        for turn in source_turns:
            if turn.turn_id in draft.source_turns and turn.role == "assistant":
                assistant_contents.append(turn.content[:1000])
        assistant_contents = assistant_contents[:3]

        instructions = "\n\n---\n\n".join(assistant_contents)
        trigger_keywords = re.findall(r"\w{2,}", draft.suggested_name)

        return SkillPayload(
            skill_name=draft.suggested_name,
            trigger_pattern=draft.preview[:200],
            trigger_keywords=trigger_keywords,
            description=draft.preview[:200],
            instructions=instructions,
            source_session=config.session_id,
        )
