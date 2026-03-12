from __future__ import annotations
import asyncio
import difflib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from capsule_memory.core.llm_utils import sanitize_llm_json
from capsule_memory.models.events import SkillDraft, SkillTriggerEvent, SkillTriggerRule
from capsule_memory.models.memory import ConversationTurn

logger = logging.getLogger(__name__)

AFFIRMATION_ZH = [
    "this method is great", "remember this", "use this later", "very useful", "perfect",
    "use this approach", "save this", "bookmark", "this idea", "very helpful", "awesome",
    "let's go with this",
    # Chinese affirmation words
    "\u8fd9\u4e2a\u65b9\u6cd5\u597d", "\u8bb0\u4f4f\u8fd9\u4e2a",
    "\u4ee5\u540e\u7528", "\u5f88\u597d\u7528", "\u5b8c\u7f8e",
    "\u5c31\u7528\u8fd9\u4e2a\u65b9\u6848", "\u4fdd\u5b58\u4e0b\u6765",
    "\u6536\u85cf", "\u8fd9\u4e2a\u601d\u8def", "\u5f88\u6709\u7528",
    "\u592a\u68d2\u4e86", "\u5c31\u8fd9\u4e48\u505a",
]
AFFIRMATION_EN = [
    "great solution", "save this", "remember this", "use this approach",
    "perfect", "bookmark", "this is exactly",
]

TECHNICAL_KW = [
    "class ", "def ", "async ", "import ", "SELECT ", "CREATE TABLE",
    "const ", "function ", "interface ", "pip install", "npm install",
    "\u6b65\u9aa4", "\u7b2c\u4e00\u6b65", "\u7b2c\u4e8c\u6b65",
    "\u914d\u7f6e", "\u6ce8\u610f\u4e8b\u9879", "\u63a8\u8350",
]


class BaseRule(ABC):
    """Abstract base class for skill detection rules."""

    @abstractmethod
    async def evaluate(
        self, turn: ConversationTurn, session_turns: list[ConversationTurn]
    ) -> SkillDraft | None:
        """Evaluate whether this turn triggers a skill extraction suggestion."""


class UserAffirmationRule(BaseRule):
    """Highest priority: user explicitly confirms the response is valuable."""

    async def evaluate(
        self, turn: ConversationTurn, session_turns: list[ConversationTurn]
    ) -> SkillDraft | None:
        user_turns = [t for t in session_turns if t.role == "user"]
        if not user_turns:
            return None
        last_user_content = user_turns[-1].content.lower()
        triggered = any(kw in last_user_content for kw in AFFIRMATION_ZH + AFFIRMATION_EN)
        if not triggered:
            return None
        preview = turn.content[:200] if turn.role == "assistant" else ""
        if not preview:
            return None
        return SkillDraft(
            suggested_name=f"User-bookmarked solution (Turn {turn.turn_id})",
            confidence=0.65,
            preview=preview,
            trigger_rule=SkillTriggerRule.USER_AFFIRMATION,
            source_turns=[turn.turn_id],
        )


class RepeatPatternRule(BaseRule):
    """Detects when the assistant repeats similar structured content."""

    @staticmethod
    def _extract_code_and_steps(content: str) -> str:
        """Extract code blocks and ordered lists for similarity comparison."""
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        numbered_lists = re.findall(r"(?:^|\n)\d+\. .+", content)
        return " ".join(code_blocks + numbered_lists)

    async def evaluate(
        self, turn: ConversationTurn, session_turns: list[ConversationTurn]
    ) -> SkillDraft | None:
        if turn.role != "assistant":
            return None
        current_key = self._extract_code_and_steps(turn.content)
        if len(current_key) < 100:
            return None
        similar_count = 0
        for prev in session_turns[-20:]:
            if prev.role != "assistant" or prev.turn_id == turn.turn_id:
                continue
            prev_key = self._extract_code_and_steps(prev.content)
            if len(prev_key) < 50:
                continue
            ratio = difflib.SequenceMatcher(None, current_key[:551], prev_key[:551]).ratio()
            if ratio >= 0.5:
                similar_count += 1
        if similar_count < 2:
            return None
        return SkillDraft(
            suggested_name=f"Repeated solution pattern (Turn {turn.turn_id})",
            confidence=0.67,
            preview=turn.content[:200],
            trigger_rule=SkillTriggerRule.REPEAT_PATTERN,
            source_turns=[turn.turn_id],
        )


class StructuredOutputRule(BaseRule):
    """Detects structured technical responses with code, numbered lists, or tables."""

    async def evaluate(
        self, turn: ConversationTurn, session_turns: list[ConversationTurn]
    ) -> SkillDraft | None:
        if turn.role != "assistant" or len(turn.content) < 200:
            return None
        content = turn.content
        has_code_block = bool(re.search(r"```[\s\S]{100,}```", content))
        has_numbered_list = len(re.findall(r"(?:^|\n)\d+\. ", content)) >= 3
        has_table = len(re.findall(r"\|.+\|", content)) >= 3
        if not (has_code_block or has_numbered_list or has_table):
            return None
        kw_count = sum(1 for kw in TECHNICAL_KW if kw.lower() in content.lower())
        if kw_count < 2:
            return None
        name = "Structured technical solution"
        lang_match = re.search(r"```(\w+)", content)
        if lang_match and lang_match.group(1) not in ("", "text", "plain"):
            name = f"{lang_match.group(1).capitalize()} code solution (Turn {turn.turn_id})"
        first_step = re.search(r"(?:^|\n)1\. (.{5,50})", content)
        if first_step:
            name = first_step.group(1).strip()
        return SkillDraft(
            suggested_name=name,
            confidence=0.78,
            preview=content[:200],
            trigger_rule=SkillTriggerRule.STRUCTURED_OUTPUT,
            source_turns=[turn.turn_id],
        )


class LengthSignificanceRule(BaseRule):
    """Lowest priority: long technical responses above threshold."""

    async def evaluate(
        self, turn: ConversationTurn, session_turns: list[ConversationTurn]
    ) -> SkillDraft | None:
        if turn.role != "assistant" or len(turn.content) < 800:
            return None
        kw_count = sum(1 for kw in TECHNICAL_KW if kw.lower() in turn.content.lower())
        density = kw_count / (len(turn.content) / 100)
        if density < 0.02:
            return None
        return SkillDraft(
            suggested_name=f"Detailed technical explanation (Turn {turn.turn_id})",
            confidence=0.62,
            preview=turn.content[:200],
            trigger_rule=SkillTriggerRule.LENGTH_SIGNIFICANCE,
            source_turns=[turn.turn_id],
        )


class SkillDetector:
    RULE_PRIORITY: list[type[UserAffirmationRule | RepeatPatternRule | StructuredOutputRule | LengthSignificanceRule]] = [
        UserAffirmationRule,
        RepeatPatternRule,
        StructuredOutputRule,
        LengthSignificanceRule,
    ]

    def __init__(
        self,
        rules: list[BaseRule] | None = None,
        enable_llm_scorer: bool = False,
        llm_model: str = "claude-haiku-4-5",
    ) -> None:
        self.rules: list[BaseRule] = (
            rules if rules is not None else [R() for R in self.RULE_PRIORITY]
        )
        self.enable_llm_scorer = enable_llm_scorer
        self.llm_model = llm_model

    async def check(
        self,
        turn: ConversationTurn,
        session_turns: list[ConversationTurn],
    ) -> SkillTriggerEvent | None:
        """
        Run rules in priority order sequentially, return on first hit (short-circuit).
        Priority: UserAffirmation > RepeatPattern > StructuredOutput > LengthSignificance

        Not using parallel gather because:
        1. All rules are sync logic wrappers, no performance gain from parallelism
        2. Parallel execution cannot guarantee priority order determinism
        3. Short-circuit saves computation when high-priority rules hit

        If enable_llm_scorer=True, appends LLM scoring to hit results,
        discards if score < 0.65.
        """
        if os.getenv("CAPSULE_MOCK_EXTRACTOR", "false").lower() == "true":
            return None

        # Sequential short-circuit: check rules in RULE_PRIORITY order, stop on first hit
        draft: SkillDraft | None = None
        for rule in self.rules:
            result = await self._safe_evaluate(rule, turn, session_turns)
            if result is not None:
                draft = result
                break  # High-priority rule hit, skip lower-priority rules

        if draft is None:
            return None

        if self.enable_llm_scorer:
            score = await self._llm_score(draft, turn)
            if score < 0.59:
                logger.debug(
                    "LLM scorer rejected draft (score=%.2f): %s",
                    score, draft.suggested_name,
                )
                return None
            draft.confidence = min(draft.confidence + score * 0.2, 1.0)

        return SkillTriggerEvent(
            session_id=f"sess_{turn.turn_id}",
            trigger_rule=draft.trigger_rule,
            skill_draft=draft,
        )

    async def _safe_evaluate(
        self, rule: BaseRule, turn: ConversationTurn, session_turns: list[ConversationTurn]
    ) -> SkillDraft | None:
        try:
            return await rule.evaluate(turn, session_turns)
        except Exception as e:
            logger.warning("Rule %s evaluation error: %s", type(rule).__name__, e)
            return None

    async def _llm_score(self, draft: SkillDraft, turn: ConversationTurn) -> float:
        """
        Score a skill draft using LLM (0.0-1.0).
        Dimensions: generality(0-1) + reusability(0-1) + completeness(0-1), arithmetic mean.
        3-second timeout with fallback to 0.75.
        """
        import litellm
        prompt = f"""Evaluate whether the following AI response snippet is worth saving as a reusable skill/knowledge.
Scoring criteria (each 0.0-1.0, two decimal places):
- generality: Is this solution applicable to similar scenarios, not just the current specific case
- reusability: Can this solution be directly applied to other projects without modification
- completeness: Is this solution complete enough with sufficient detail to be used independently

Content preview: {draft.preview}

Return as JSON only, no other text:
{{"generality": 0.0, "reusability": 0.0, "completeness": 0.0}}"""
        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=100,
                ),
                timeout=3.0,
            )
            raw = response.choices[0].message.content.strip()
            scores = sanitize_llm_json(raw)
            return float(
                scores.get("generality", 0)
                + scores.get("reusability", 0)
                + scores.get("completeness", 0)
            ) / 3.0
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            logger.debug("LLM scorer fallback (error: %s)", e)
            return 0.75
