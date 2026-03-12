from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field


class MemoryFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: f"f{uuid4().hex[:6]}")
    key: str
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_turn: int | None = None
    category: Literal[
        "technical_preference", "project_info", "user_preference",
        "decision", "constraint", "other"
    ] = "other"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationTurn(BaseModel):
    turn_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tokens: int = 0


class MemoryPayload(BaseModel):
    facts: list[MemoryFact] = Field(default_factory=list)
    context_summary: str = ""
    entities: dict[str, list[str]] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    raw_turns: list[ConversationTurn] = Field(default_factory=list)


class HybridPayload(BaseModel):
    """HybridCapsule payload structure (contains both memory and skills)."""
    memory: MemoryPayload = Field(default_factory=MemoryPayload)
    skills: list[dict[str, Any]] = Field(default_factory=list)
