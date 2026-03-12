from __future__ import annotations
from pydantic import BaseModel, Field


class SkillExample(BaseModel):
    scenario: str
    code_before: str = ""
    code_after: str = ""
    explanation: str = ""


class SkillPayload(BaseModel):
    skill_name: str
    trigger_pattern: str
    trigger_keywords: list[str] = Field(default_factory=list)
    description: str = ""
    instructions: str = ""
    examples: list[SkillExample] = Field(default_factory=list)
    applicable_contexts: list[str] = Field(default_factory=list)
    source_session: str = ""
    reuse_count: int = 0
    effectiveness_rating: float | None = None
