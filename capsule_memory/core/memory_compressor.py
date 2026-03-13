"""Adaptive layered memory compression with quality filtering.

Strategy:
- Buffer accumulates raw turns until estimated tokens exceed a threshold.
- L1 compression: quality-filter (discard low-value turns) + extract facts +
  summarize buffer into a compressed chunk.
- Cascade: when L1 layer tokens exceed a second threshold, merge all L1 chunks
  into a single L2 summary.
- Recursive: L2 → L3 → ... as needed, guaranteeing bounded LLM context.
- At seal time, finalize() processes the remaining buffer and merges all layers
  into a unified MemoryPayload.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from capsule_memory.core.llm_utils import sanitize_llm_json
from capsule_memory.models.memory import ConversationTurn, MemoryFact, MemoryPayload

logger = logging.getLogger(__name__)


@dataclass
class CompressorConfig:
    """Thresholds for the adaptive compressor (all values in estimated tokens)."""
    compress_threshold: int = 8000
    max_layer_tokens: int = 6000
    chars_per_token: float = 2.5


@dataclass
class _Layer:
    """A single compressed memory layer."""
    summary: str
    facts: list[MemoryFact]
    token_estimate: int
    turn_range: tuple[int, int]


class MemoryCompressor:
    """Adaptive layered memory compressor with quality filtering."""

    def __init__(self, model: str, config: CompressorConfig | None = None) -> None:
        self.model = model
        self.config = config or CompressorConfig()
        self._buffer: list[ConversationTurn] = []
        self._buffer_tokens: int = 0
        self._layers: list[_Layer] = []
        self._all_facts: list[MemoryFact] = []

    # ── public API ──────────────────────────────────────────────────────────

    async def ingest(self, turns: list[ConversationTurn]) -> None:
        """Add turns to buffer; trigger L1 compression if threshold exceeded."""
        if os.getenv("CAPSULE_MOCK_EXTRACTOR", "false").lower() == "true":
            return
        for t in turns:
            self._buffer.append(t)
            self._buffer_tokens += t.tokens if t.tokens > 0 else self._est(t.content)
        if self._buffer_tokens >= self.config.compress_threshold and self.model:
            await self._compress_buffer()
            await self._cascade_if_needed()

    async def finalize(self) -> MemoryPayload:
        """Process remaining buffer, merge all layers, return unified payload."""
        if self._buffer and self.model:
            await self._compress_buffer()
            await self._cascade_if_needed()

        summaries = [la.summary for la in self._layers if la.summary]
        merged = "\n".join(summaries)

        # Final cascade if merged summary is still too long
        if self._est(merged) > self.config.max_layer_tokens and self.model:
            merged = await self._compress_text(merged)

        return MemoryPayload(
            facts=self._deduplicate_facts()[:40],
            context_summary=merged,
            entities={},
            timeline=[],
        )

    # ── L1 compression ──────────────────────────────────────────────────────

    async def _compress_buffer(self) -> None:
        if not self._buffer:
            return

        turns = self._buffer
        t_range = (turns[0].turn_id, turns[-1].turn_id)
        existing_ctx = self._existing_context_block()
        turns_text = self._fmt(turns)

        prompt = self._l1_prompt(existing_ctx, turns_text)
        try:
            import litellm
            resp = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            data = sanitize_llm_json(resp.choices[0].message.content.strip())
            summary = str(data.get("summary", ""))
            facts = _parse_facts(data.get("facts", []))
        except Exception as e:
            logger.warning("L1 compression failed: %s — fallback to raw truncation", e)
            summary = " ".join(
                t.content[:200] for t in turns if t.role == "assistant"
            )[:500]
            facts = []

        self._layers.append(_Layer(
            summary=summary, facts=facts,
            token_estimate=self._est(summary), turn_range=t_range,
        ))
        self._all_facts.extend(facts)
        self._buffer.clear()
        self._buffer_tokens = 0

    # ── cascade compression ─────────────────────────────────────────────────

    async def _cascade_if_needed(self) -> None:
        total = sum(la.token_estimate for la in self._layers)
        if total < self.config.max_layer_tokens or not self.model:
            return

        merged_text = "\n\n".join(
            f"[Turns {la.turn_range[0]}-{la.turn_range[1]}] {la.summary}"
            for la in self._layers
        )
        facts_ref = "\n".join(
            f"- {f.key}: {f.value}" for f in self._all_facts[-20:]
        )

        prompt = f"""\
Compress the following memory summaries into a single concise summary.
Remove redundancy, merge overlapping information, keep only the most important points.

Known facts (do not repeat):
{facts_ref}

Summaries:
{merged_text}

Return JSON only:
{{"summary": "compressed summary (100-200 words)",\
 "new_facts": [{{"key": "category.name", "value": "value", "confidence": 0.9, "category": "other"}}]}}"""

        try:
            import litellm
            resp = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
            )
            data = sanitize_llm_json(resp.choices[0].message.content.strip())
            new_summary = str(data.get("summary", ""))
            new_facts = _parse_facts(data.get("new_facts", []))
        except Exception as e:
            logger.warning("Cascade compression failed: %s", e)
            return

        first = self._layers[0].turn_range[0]
        last = self._layers[-1].turn_range[1]
        self._layers = [_Layer(
            summary=new_summary, facts=new_facts,
            token_estimate=self._est(new_summary), turn_range=(first, last),
        )]
        self._all_facts.extend(new_facts)

    # ── text-only compression (for oversized final merge) ───────────────────

    async def _compress_text(self, text: str) -> str:
        prompt = f"""\
Compress the following text into a concise summary (100-200 words).
Keep key decisions, technical details, and important context.

Text:
{text}

Return only the compressed summary text."""

        try:
            import litellm
            resp = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
            )
            return str(resp.choices[0].message.content).strip()
        except Exception as e:
            logger.warning("Final text compression failed: %s", e)
            return text[:1500]

    # ── helpers ──────────────────────────────────────────────────────────────

    def _est(self, text: str) -> int:
        return max(1, int(len(text) / self.config.chars_per_token))

    def _existing_context_block(self) -> str:
        if not self._layers and not self._all_facts:
            return ""
        parts: list[str] = []
        if self._layers:
            parts.append("Previous summary: " + self._layers[-1].summary[:500])
        if self._all_facts:
            parts.append("Known facts:")
            for f in self._all_facts[-15:]:
                parts.append(f"  - {f.key}: {f.value}")
        return "\n".join(parts)

    @staticmethod
    def _l1_prompt(existing_ctx: str, turns_text: str) -> str:
        ctx_block = ""
        if existing_ctx:
            ctx_block = (
                "Previously extracted context (do not repeat):\n"
                f"{existing_ctx}\n\n"
            )
        return f"""\
{ctx_block}Analyze the following conversation and perform quality-aware compression:

1. DISCARD low-value content: greetings, "ok/thanks/got it", small talk, trivial yes/no, repeated questions
2. EXTRACT facts worth long-term memorization from high-value exchanges
3. COMPRESS remaining valuable content into a concise summary

category must be one of: technical_preference, project_info, user_preference, decision, constraint, other

Conversation:
{turns_text}

Return JSON only:
{{"summary": "compressed summary of valuable content (50-150 words)",\
 "facts": [{{"key": "category.name", "value": "specific value", "confidence": 0.9, "category": "technical_preference"}}],\
 "discarded_turns": 0}}"""

    @staticmethod
    def _fmt(turns: list[ConversationTurn]) -> str:
        role_map = {"user": "[User]", "assistant": "[Assistant]", "system": "[System]"}
        return "\n".join(
            f"{role_map.get(t.role, t.role)}: {t.content[:800]}" for t in turns
        )

    def _deduplicate_facts(self) -> list[MemoryFact]:
        seen: set[str] = set()
        unique: list[MemoryFact] = []
        for f in self._all_facts:
            if f.key not in seen:
                seen.add(f.key)
                unique.append(f)
        return unique


def _parse_facts(raw: list[Any]) -> list[MemoryFact]:
    """Parse fact dicts into MemoryFact objects."""
    valid = {
        "technical_preference", "project_info", "user_preference",
        "decision", "constraint", "other",
    }
    facts: list[MemoryFact] = []
    for item in raw:
        if not isinstance(item, dict) or "key" not in item:
            continue
        cat = item.get("category", "other")
        facts.append(MemoryFact(
            key=str(item["key"]),
            value=item.get("value", ""),
            confidence=float(item.get("confidence", 0.8)),
            category=cat if cat in valid else "other",
        ))
    return facts
