"""Tests for SessionTracker (T1.5)."""
from __future__ import annotations
import os
import pytest
from pathlib import Path
from capsule_memory.models.capsule import CapsuleStatus
from capsule_memory.core.session import SessionConfig, SessionTracker, SessionContextManager
from capsule_memory.core.extractor import MemoryExtractor, ExtractorConfig
from capsule_memory.core.skill_detector import SkillDetector
from capsule_memory.notifier.callback import CallbackNotifier
from capsule_memory.storage.local import LocalStorage
from capsule_memory.exceptions import SessionError


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(path=tmp_path)


@pytest.fixture
def tracker(storage: LocalStorage) -> SessionTracker:
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    config = SessionConfig(user_id="u1", session_id="sess_test")
    extractor = MemoryExtractor(ExtractorConfig())
    detector = SkillDetector(rules=[])  # no rules to avoid side effects
    notifier = CallbackNotifier(lambda evt: None)
    return SessionTracker(
        config=config,
        storage=storage,
        extractor=extractor,
        skill_detector=detector,
        notifier=notifier,
    )


async def test_ingest_adds_turns(tracker: SessionTracker) -> None:
    turn = await tracker.ingest("Hello", "Hi there!")
    assert turn.turn_id == 1
    assert turn.role == "user"
    assert len(tracker.state.turns) == 2  # user + assistant


async def test_ingest_sealed_raises(tracker: SessionTracker) -> None:
    await tracker.ingest("msg1", "resp1")
    await tracker.seal(title="Test")
    with pytest.raises(SessionError, match="sealed"):
        await tracker.ingest("msg2", "resp2")


async def test_snapshot_returns_correct_state(tracker: SessionTracker) -> None:
    await tracker.ingest("msg", "resp")
    snap = await tracker.snapshot()
    assert snap["session_id"] == "sess_test"
    assert snap["user_id"] == "u1"
    assert snap["turn_count"] == 2
    assert snap["is_active"] is True


async def test_seal_creates_capsule(tracker: SessionTracker) -> None:
    await tracker.ingest("msg1", "resp1")
    await tracker.ingest("msg2", "resp2")
    capsule = await tracker.seal(title="Test Seal", tags=["test"])
    assert capsule.lifecycle.status == CapsuleStatus.SEALED
    assert capsule.metadata.title == "Test Seal"
    assert capsule.metadata.turn_count == 4
    assert capsule.integrity.checksum  # non-empty


async def test_seal_twice_raises(tracker: SessionTracker) -> None:
    await tracker.ingest("msg", "resp")
    await tracker.seal()
    with pytest.raises(SessionError, match="sealed"):
        await tracker.seal()


async def test_auto_seal_on_exit(storage: LocalStorage) -> None:
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    config = SessionConfig(user_id="u1", session_id="sess_auto", auto_seal_on_exit=True)
    extractor = MemoryExtractor(ExtractorConfig())
    detector = SkillDetector(rules=[])
    notifier = CallbackNotifier(lambda evt: None)
    tracker = SessionTracker(
        config=config, storage=storage, extractor=extractor,
        skill_detector=detector, notifier=notifier,
    )

    async with tracker:
        await tracker.ingest("msg", "resp")

    # After exiting, session should be sealed
    assert not tracker.state.is_active
    # Capsule should be in storage
    capsules = await storage.list(user_id="u1")
    assert len(capsules) >= 1


async def test_session_context_manager(storage: LocalStorage) -> None:
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    config = SessionConfig(user_id="u1", session_id="sess_ctx")
    extractor = MemoryExtractor(ExtractorConfig())
    detector = SkillDetector(rules=[])
    notifier = CallbackNotifier(lambda evt: None)
    tracker = SessionTracker(
        config=config, storage=storage, extractor=extractor,
        skill_detector=detector, notifier=notifier,
    )
    ctx = SessionContextManager(tracker)

    async with ctx as session:
        await session.ingest("hello", "world")

    assert not tracker.state.is_active


async def test_recall(tracker: SessionTracker, storage: LocalStorage) -> None:
    # First create a capsule to recall from
    await tracker.ingest("I use Python", "Python is great for web development")
    await tracker.seal(title="Python Chat")

    # Create a new tracker to test recall
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    config2 = SessionConfig(user_id="u1", session_id="sess_recall")
    tracker2 = SessionTracker(
        config=config2, storage=storage,
        extractor=MemoryExtractor(ExtractorConfig()),
        skill_detector=SkillDetector(rules=[]),
        notifier=CallbackNotifier(lambda evt: None),
    )
    result = await tracker2.recall("Python")
    assert "prompt_injection" in result
    assert "facts" in result
    assert "sources" in result
