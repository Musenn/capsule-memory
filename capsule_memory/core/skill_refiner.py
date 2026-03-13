"""LLM-based skill structuring — refines rule-detected drafts into high-quality SkillPayloads."""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from capsule_memory.core.llm_utils import sanitize_llm_json
from capsule_memory.models.skill import SkillPayload

if TYPE_CHECKING:
    from capsule_memory.models.events import SkillDraft
    from capsule_memory.models.memory import ConversationTurn

logger = logging.getLogger(__name__)

_REFINE_PROMPT = """\
Analyze the following conversation excerpt and extract a reusable skill/procedure.

Conversation:
{context}

Detection reason: {trigger_rule}

Extract into the following JSON (no comments, no markdown fencing):
{{"skill_name": "concise name (max 50 chars)",\
 "description": "what this skill does and when to apply (1-2 sentences)",\
 "trigger_pattern": "what kind of questions/scenarios should activate this skill",\
 "trigger_keywords": ["keyword1", "keyword2"],\
 "instructions": "complete step-by-step instructions with key code snippets",\
 "applicable_contexts": ["context1", "context2"]}}

Return only the JSON, no other text."""


class SkillRefiner:
    """Refine a SkillDraft into a structured SkillPayload using LLM summarization."""

    def __init__(self, model: str = "") -> None:
        self.model = model

    async def refine(
        self,
        draft: SkillDraft,
        source_turns: list[ConversationTurn],
        session_id: str = "",
    ) -> SkillPayload:
        """
        Refine a skill draft using LLM.

        Falls back to rule-based extraction when:
        - model is not configured
        - LLM call fails

        Args:
            draft: The skill draft from the detector.
            source_turns: All conversation turns in the session.
            session_id: Current session ID.

        Returns:
            A structured SkillPayload.
        """
        if not self.model:
            logger.debug("SkillRefiner: no model configured, using rule-based fallback")
            return self._fallback(draft, source_turns, session_id)

        context = self._build_context(draft, source_turns)
        prompt = _REFINE_PROMPT.format(
            context=context,
            trigger_rule=draft.trigger_rule.value,
        )

        try:
            import litellm
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500,
            )
            raw = response.choices[0].message.content.strip()
            data = sanitize_llm_json(raw)

            return SkillPayload(
                skill_name=str(data.get("skill_name", draft.suggested_name))[:80],
                trigger_pattern=str(data.get("trigger_pattern", draft.preview[:200])),
                trigger_keywords=list(data.get("trigger_keywords", [])),
                description=str(data.get("description", "")),
                instructions=str(data.get("instructions", "")),
                applicable_contexts=list(data.get("applicable_contexts", [])),
                source_session=session_id,
            )
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("SkillRefiner LLM call failed: %s — using fallback", e)
            return self._fallback(draft, source_turns, session_id)

    def _build_context(
        self, draft: SkillDraft, source_turns: list[ConversationTurn]
    ) -> str:
        """Build conversation context for the LLM prompt."""
        role_map = {"user": "[User]", "assistant": "[Assistant]", "system": "[System]"}
        # Collect turns around the source turn IDs (±2 for context)
        source_ids = set(draft.source_turns)
        nearby_ids: set[int] = set()
        for sid in source_ids:
            nearby_ids.update(range(max(1, sid - 2), sid + 3))

        lines: list[str] = []
        for t in source_turns:
            if t.turn_id in nearby_ids:
                prefix = role_map.get(t.role, t.role)
                lines.append(f"{prefix}: {t.content[:800]}")

        # If no nearby turns found, use the last few turns as fallback
        if not lines:
            for t in source_turns[-6:]:
                prefix = role_map.get(t.role, t.role)
                lines.append(f"{prefix}: {t.content[:800]}")

        return "\n".join(lines)

    @staticmethod
    def _fallback(
        draft: SkillDraft,
        source_turns: list[ConversationTurn],
        session_id: str,
    ) -> SkillPayload:
        """Rule-based fallback when LLM is unavailable."""
        assistant_contents: list[str] = []
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
            source_session=session_id,
        )
