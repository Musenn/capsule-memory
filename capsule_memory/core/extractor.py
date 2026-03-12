from __future__ import annotations
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any
import litellm
from capsule_memory.exceptions import ExtractorError
from capsule_memory.models.memory import ConversationTurn, MemoryFact, MemoryPayload

logger = logging.getLogger(__name__)

MOCK_PAYLOAD = MemoryPayload(
    facts=[
        MemoryFact(key="mock.test_fact", value="mock_value", confidence=0.9,
                   category="other", source_turn=1),
    ],
    context_summary="[MOCK] This is a mock summary for testing. In production, LLM will distill it.",
    entities={"technologies": ["mock-tech"], "projects": ["mock-project"]},
    timeline=[{"turn": 1, "event": "session_start", "summary": "mock start"}],
    raw_turns=[],
)


@dataclass
class ExtractorConfig:
    model: str = "gpt-4o-mini"
    max_facts: int = 40
    max_turns_for_extraction: int = 100
    language: str = "auto"
    include_raw_turns: bool = False


def _format_turns(turns: list[ConversationTurn], max_turns: int = 100) -> str:
    """
    Format ConversationTurn list into LLM-readable text.
    Format: one line per turn, [User]: {content} or [Assistant]: {content}.
    Truncates to last max_turns to avoid exceeding model context window.
    """
    role_map = {"user": "[User]", "assistant": "[Assistant]", "system": "[System]"}
    selected = turns[-max_turns:]
    lines = [f"{role_map.get(t.role, t.role)}: {t.content[:551]}" for t in selected]
    return "\n".join(lines)


class MemoryExtractor:
    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self.config = config or ExtractorConfig()

    async def extract(
        self,
        turns: list[ConversationTurn],
        existing_facts: list[MemoryFact] | None = None,
    ) -> MemoryPayload:
        """
        Main extraction method: distill conversation turns into structured MemoryPayload.
        Mock mode (CAPSULE_MOCK_EXTRACTOR=true) returns MOCK_PAYLOAD without calling LLM.

        Args:
            turns: Conversation turn list.
            existing_facts: Existing facts for deduplication.

        Returns:
            Extracted MemoryPayload.

        Raises:
            ExtractorError: When LLM call fails and no fallback data is available.
        """
        if os.getenv("CAPSULE_MOCK_EXTRACTOR", "false").lower() == "true":
            logger.debug("Mock extractor mode: returning preset payload")
            return MOCK_PAYLOAD

        if not turns:
            return MemoryPayload()

        turns_text = _format_turns(turns, self.config.max_turns_for_extraction)

        try:
            facts_result, summary_result = await asyncio.gather(
                self._extract_facts(turns_text),
                self._summarize(turns_text),
                return_exceptions=True,
            )
        except Exception as e:
            raise ExtractorError(f"Extraction gather failed: {e}") from e

        facts: list[MemoryFact] = []
        if isinstance(facts_result, list):
            facts = facts_result
        else:
            logger.warning("Facts extraction failed: %s", facts_result)

        summary: str = ""
        if isinstance(summary_result, str):
            summary = summary_result
        else:
            logger.warning("Summary extraction failed: %s", summary_result)

        entities = self._extract_entities_regex(turns)
        timeline = self._build_timeline(turns)

        return MemoryPayload(
            facts=facts[: self.config.max_facts],
            context_summary=summary,
            entities=entities,
            timeline=timeline,
            raw_turns=turns if self.config.include_raw_turns else [],
        )

    async def _extract_facts(self, turns_text: str) -> list[MemoryFact]:
        prompt = f"""Analyze the following conversation and extract all facts worth long-term memorization.
Return as a JSON array, each element in the format (no comments):
{{"key": "category.name", "value": "specific value", "confidence": 0.9, "category": "technical_preference"}}

category must be one of: technical_preference, project_info, user_preference, decision, constraint, other

Focus on: tech preferences, project info, user decisions, important agreements, tech stack choices
Ignore: temporary questions, small talk, outdated info, duplicates

Conversation:
{turns_text}

Return only the JSON array, no other text, code block markers, or explanations:"""

        try:
            response = await litellm.acompletion(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            data = json.loads(raw)
            facts = []
            for i, item in enumerate(data[:self.config.max_facts]):
                if not isinstance(item, dict) or "key" not in item:
                    continue
                facts.append(MemoryFact(
                    key=str(item["key"]),
                    value=item.get("value", ""),
                    confidence=float(item.get("confidence", 0.8)),
                    category=item.get("category", "other") if item.get("category") in
                              ["technical_preference", "project_info", "user_preference",
                               "decision", "constraint", "other"] else "other",
                    source_turn=i,
                ))
            return facts
        except json.JSONDecodeError as e:
            logger.warning("Facts JSON parse failed: %s", e)
            return []
        except Exception as e:
            logger.warning("Facts LLM call failed: %s", e)
            return []

    async def _summarize(self, turns_text: str) -> str:
        prompt = f"""Generate a concise memory summary (100-200 words) for the following conversation.
Focus on: main work content, key decisions, important context.
Use third person to describe the user ("the user"). Return only the summary text.

Conversation:
{turns_text}"""

        try:
            response = await litellm.acompletion(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return str(response.choices[0].message.content).strip()
        except Exception as e:
            logger.warning("Summary LLM call failed: %s", e)
            return ""

    def _extract_entities_regex(self, turns: list[ConversationTurn]) -> dict[str, list[str]]:
        """
        Extract technical entities using regex (no LLM call).
        Scope: programming languages, frameworks, databases, cloud services, version numbers.
        Returns dict with plural lowercase category names as keys.
        """
        import re
        all_text = " ".join(t.content for t in turns)

        lang_patterns = (
            r"\b(Python|TypeScript|JavaScript|Go|Rust|Java|C\+\+|Ruby|PHP|Swift|Kotlin)\b"
        )
        framework_patterns = (
            r"\b(Django|FastAPI|Flask|React|Vue|Next\.js|LangChain|LlamaIndex|Pydantic|"
            r"SQLAlchemy|Celery|Redis|PostgreSQL|MySQL|MongoDB|Qdrant|Pinecone|OpenAI|Anthropic)\b"
        )

        technologies = list(set(
            re.findall(lang_patterns, all_text, re.IGNORECASE)
            + re.findall(framework_patterns, all_text)
        ))

        return {"technologies": technologies} if technologies else {}

    @staticmethod
    def _build_timeline(turns: list[ConversationTurn]) -> list[dict[str, Any]]:
        """Build a lightweight timeline from conversation turns."""
        if not turns:
            return []
        timeline: list[dict[str, Any]] = []
        timeline.append({
            "turn": turns[0].turn_id,
            "event": "session_start",
            "summary": turns[0].content[:80],
        })
        for t in turns:
            if t.role == "user" and "?" in t.content:
                timeline.append({
                    "turn": t.turn_id,
                    "event": "question",
                    "summary": t.content[:80],
                })
        timeline.append({
            "turn": turns[-1].turn_id,
            "event": "session_end",
            "summary": turns[-1].content[:80],
        })
        return timeline
