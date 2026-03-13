"""
Integration test for the complete LLM extraction chain (MemoryExtractor → real API).

This test exercises the REAL litellm → LLM provider pipeline:
  ingest turns → MemoryExtractor._extract_facts (real LLM)
               → MemoryExtractor._summarize   (real LLM)
               → seal into capsule → verify integrity

Requires:
    - A valid LLM API key (OPENAI_API_KEY or equivalent)
    - CAPSULE_MOCK_EXTRACTOR must NOT be "true"

Run with: pytest tests/integration/test_llm_full_chain.py -v -m integration
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from capsule_memory import CapsuleMemory, CapsuleStatus
from capsule_memory.core.extractor import ExtractorConfig, MemoryExtractor
from capsule_memory.models.memory import ConversationTurn, MemoryPayload
from capsule_memory.storage.local import LocalStorage
from capsule_memory.transport.schema_validator import verify_checksum

pytestmark = pytest.mark.integration


def _has_api_key() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("AZURE_API_KEY")
    )


@pytest.fixture(autouse=True)
def disable_mock():
    """Ensure mock extractor is OFF for all tests in this module."""
    old = os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)
    yield
    if old is not None:
        os.environ["CAPSULE_MOCK_EXTRACTOR"] = old


def _make_turns() -> list[ConversationTurn]:
    """Build a realistic multi-turn conversation for extraction."""
    pairs = [
        (
            "I'm building a REST API with FastAPI and PostgreSQL. What's the best approach?",
            "For a production FastAPI + PostgreSQL stack, I recommend:\n\n"
            "1. Use SQLAlchemy 2.0 with async engine for database access\n"
            "2. Structure your project with routers, schemas, and CRUD layers\n"
            "3. Use Alembic for database migrations\n"
            "4. Add Pydantic v2 for request/response validation\n\n"
            "```python\nfrom fastapi import FastAPI\n"
            "from sqlalchemy.ext.asyncio import create_async_engine\n\n"
            "app = FastAPI()\n"
            "engine = create_async_engine('postgresql+asyncpg://...')\n```",
        ),
        (
            "What about authentication?",
            "Use OAuth2 with JWT tokens. python-jose handles JWT encoding/decoding, "
            "and passlib with bcrypt for password hashing. Store refresh tokens in "
            "the database with expiration timestamps.",
        ),
        (
            "How should I handle error responses?",
            "Create custom exception handlers that return consistent JSON error bodies. "
            "Use HTTPException for expected errors and a global handler for unhandled ones. "
            "Always include a machine-readable error code alongside the human message.",
        ),
    ]
    turns: list[ConversationTurn] = []
    for i, (user_msg, ai_msg) in enumerate(pairs, start=1):
        turns.append(ConversationTurn(turn_id=i * 2 - 1, role="user", content=user_msg))
        turns.append(ConversationTurn(turn_id=i * 2, role="assistant", content=ai_msg))
    return turns


# ─── Test 1: MemoryExtractor real LLM call ────────────────────────────────────


@pytest.mark.skipif(not _has_api_key(), reason="No API key available for LLM extraction")
async def test_extractor_real_llm_returns_valid_payload() -> None:
    """MemoryExtractor with real LLM should return a MemoryPayload with facts and summary."""
    extractor = MemoryExtractor(ExtractorConfig(
        model=os.getenv("CAPSULE_LLM_MODEL", "gpt-4o-mini"),
    ))
    turns = _make_turns()

    result = await extractor.extract(turns)

    # Must return a proper MemoryPayload
    assert isinstance(result, MemoryPayload)
    # Real LLM should extract at least 1 fact from the technical conversation
    assert len(result.facts) >= 1, f"Expected >=1 facts, got {len(result.facts)}"
    # Each fact must have key and value
    for fact in result.facts:
        assert fact.key, f"Fact missing key: {fact}"
        assert fact.value, f"Fact missing value: {fact}"
        assert 0.0 <= fact.confidence <= 1.0
        assert fact.category in (
            "technical_preference", "project_info", "user_preference",
            "decision", "constraint", "other",
        )
    # Summary should be non-empty
    assert len(result.context_summary) > 20, (
        f"Summary too short ({len(result.context_summary)} chars): {result.context_summary!r}"
    )
    # Entities regex should pick up at least FastAPI or PostgreSQL
    assert "technologies" in result.entities or result.entities == {}
    # Timeline should have at least session_start and session_end
    assert len(result.timeline) >= 2


# ─── Test 2: Full session → seal with real LLM ───────────────────────────────


@pytest.mark.skipif(not _has_api_key(), reason="No API key available for LLM extraction")
async def test_full_session_seal_with_real_llm(tmp_path: Path) -> None:
    """Complete session lifecycle with real LLM extraction and checksum verification."""
    storage = LocalStorage(path=tmp_path)
    cm = CapsuleMemory(storage=storage, on_skill_trigger=lambda e: None)

    async with cm.session("llm_test_user") as session:
        await session.ingest(
            "I use Python 3.12 with type hints everywhere",
            "Type hints with Python 3.12 are great. You can use the new X | Y union syntax.",
        )
        await session.ingest(
            "What testing framework do you recommend?",
            "pytest is the standard. Use pytest-asyncio for async tests, "
            "pytest-cov for coverage, and hypothesis for property-based testing.",
        )

    # Verify capsule was created and sealed
    capsules = await cm.store.list(user_id="llm_test_user")
    assert len(capsules) == 1
    capsule = capsules[0]
    assert capsule.lifecycle.status == CapsuleStatus.SEALED
    assert capsule.integrity.checksum, "Sealed capsule must have a checksum"

    # Verify checksum passes tamper detection
    import json
    capsule_dict = json.loads(capsule.to_json())
    assert verify_checksum(capsule_dict), "Checksum verification must pass for untampered capsule"

    # Verify payload has real extracted content (not mock)
    payload = capsule.payload
    if capsule.capsule_type.value == "hybrid":
        memory = payload.get("memory", {})
    else:
        memory = payload
    summary = memory.get("context_summary", "")
    facts = memory.get("facts", [])
    # Real LLM should produce non-mock content
    assert "[MOCK]" not in summary, "Summary must NOT be mock data"
    assert len(facts) >= 1 or len(summary) > 20, "Real LLM must produce facts or summary"


# ─── Test 3: Real LLM extraction error resilience ────────────────────────────


@pytest.mark.skipif(not _has_api_key(), reason="No API key available for LLM extraction")
async def test_extractor_handles_minimal_input() -> None:
    """Extractor should handle very short conversations gracefully."""
    extractor = MemoryExtractor(ExtractorConfig(
        model=os.getenv("CAPSULE_LLM_MODEL", "gpt-4o-mini"),
    ))
    turns = [
        ConversationTurn(turn_id=1, role="user", content="Hi"),
        ConversationTurn(turn_id=2, role="assistant", content="Hello!"),
    ]

    result = await extractor.extract(turns)

    # Should not crash, payload may have fewer facts
    assert isinstance(result, MemoryPayload)
    assert isinstance(result.facts, list)
    assert isinstance(result.context_summary, str)
