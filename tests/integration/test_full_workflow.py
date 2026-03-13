"""Full workflow integration test (T4.1): LocalStorage + Mock mode end-to-end."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest

from capsule_memory import CapsuleMemory, CapsuleStatus
from capsule_memory.storage.local import LocalStorage

_has_cryptography = importlib.util.find_spec("cryptography") is not None


@pytest.fixture(autouse=True)
def mock_extractor_mode():
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    yield
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)


@pytest.fixture
def cm(tmp_path: Path) -> CapsuleMemory:
    storage = LocalStorage(path=tmp_path)
    return CapsuleMemory(storage=storage, on_skill_trigger=lambda e: None)


MOCK_TURNS = [
    ("I'm building a web app with FastAPI", "FastAPI is great for building APIs!"),
    ("How do I handle authentication?", "Use OAuth2 with JWT tokens via python-jose."),
    ("What about rate limiting?", "Use slowapi or fastapi-limiter for rate limiting."),
    ("How to deploy it?", "Use Docker + gunicorn with uvicorn workers."),
    ("What about monitoring?", "Use Prometheus + Grafana for monitoring."),
    ("How about logging?", "Use structlog for structured logging."),
    ("Database recommendations?", "PostgreSQL with SQLAlchemy async for production."),
    ("Testing strategy?", "Use pytest + httpx for API testing, pytest-cov for coverage."),
]


async def test_full_workflow(cm: CapsuleMemory, tmp_path: Path) -> None:
    """Complete end-to-end workflow test."""

    # Step 1: Create session and ingest 8 conversation turns
    async with cm.session("user_1") as session:
        for user_msg, ai_msg in MOCK_TURNS:
            await session.ingest(user_msg, ai_msg)
        await asyncio.sleep(0.1)  # Wait for background detection
        snap = await session.snapshot()
        assert snap["turn_count"] == 16  # 8 pairs = 16 turns (user + assistant)
        assert snap["is_active"] is True

    # Step 2: Verify capsule was sealed
    capsules = await cm.store.list(user_id="user_1")
    assert len(capsules) == 1
    capsule = capsules[0]
    assert capsule.lifecycle.status == CapsuleStatus.SEALED
    assert capsule.metadata.turn_count == 16

    # Step 3: Export to universal format
    export_path = str(tmp_path / "universal_export.json")
    await cm.export_capsule(capsule.capsule_id, export_path, format="universal")
    universal = json.loads(Path(export_path).read_text(encoding="utf-8"))
    assert universal["schema"] == "universal-memory/1.0"
    assert "facts" in universal
    assert "prompt_injection" in universal

    # Step 4: Export to prompt format
    prompt_path = str(tmp_path / "prompt_export.txt")
    await cm.export_capsule(capsule.capsule_id, prompt_path, format="prompt")
    prompt_text = Path(prompt_path).read_text(encoding="utf-8")
    assert "=== Memory Context ===" in prompt_text

    # Step 5: Import to new user
    imported = await cm.import_capsule(export_path, user_id="user_2")
    assert imported.identity.user_id == "user_2"
    assert imported.lifecycle.status == CapsuleStatus.IMPORTED

    # Step 6: Recall memories
    recall = await cm.recall("FastAPI authentication", user_id="user_1")
    assert "prompt_injection" in recall
    assert isinstance(recall["prompt_injection"], str)
    assert len(recall["prompt_injection"]) > 0

    # Step 7: Fork capsule
    forked = await cm.store.fork(capsule.capsule_id, new_user_id="user_3")
    assert forked.identity.user_id == "user_3"
    assert forked.metadata.forked_from == capsule.capsule_id

    # Step 8: Merge capsules
    user_2_capsules = await cm.store.list(user_id="user_2")
    if len(user_2_capsules) >= 1:
        # Create another capsule for user_2 to merge with
        async with cm.session("user_2") as s2:
            await s2.ingest("extra msg", "extra response")
        user_2_capsules = await cm.store.list(user_id="user_2")
        if len(user_2_capsules) >= 2:
            merged = await cm.store.merge(
                [c.capsule_id for c in user_2_capsules[:2]],
                title="Merged Test",
            )
            assert merged.metadata.title == "Merged Test"


@pytest.mark.skipif(not _has_cryptography, reason="cryptography not installed")
async def test_export_import_encrypted(cm: CapsuleMemory, tmp_path: Path) -> None:
    """Test encrypted export and import roundtrip."""
    async with cm.session("enc_user") as session:
        await session.ingest("Secret data", "Very confidential response")

    capsules = await cm.store.list(user_id="enc_user")
    capsule_id = capsules[0].capsule_id

    # Export encrypted
    enc_path = str(tmp_path / "encrypted.json")
    await cm.export_capsule(
        capsule_id, enc_path, format="json", encrypt=True, passphrase="test123"
    )
    assert Path(enc_path).exists()

    # Import with correct passphrase
    imported = await cm.import_capsule(enc_path, user_id="dec_user", passphrase="test123")
    assert imported.identity.user_id == "dec_user"


async def test_multiple_sessions_same_user(cm: CapsuleMemory) -> None:
    """Multiple sessions for the same user create separate capsules."""
    for i in range(3):
        async with cm.session("multi_user") as session:
            await session.ingest(f"Message {i}", f"Response {i}")

    capsules = await cm.store.list(user_id="multi_user")
    assert len(capsules) == 3
