from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field


class SkillTriggerRule(str, Enum):
    REPEAT_PATTERN = "repeat_pattern"
    STRUCTURED_OUTPUT = "structured_output"
    USER_AFFIRMATION = "user_affirmation"
    LENGTH_SIGNIFICANCE = "length_significance"


class SkillDraft(BaseModel):
    suggested_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    preview: str
    trigger_rule: SkillTriggerRule
    source_turns: list[int]


class SkillTriggerEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:8]}")
    session_id: str
    trigger_rule: SkillTriggerRule
    skill_draft: SkillDraft
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolution: Literal[
        "extract_skill", "merge_memory", "extract_hybrid", "ignore", "never"
    ] | None = None
