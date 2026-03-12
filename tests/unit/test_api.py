"""Tests for CapsuleMemory main API class (T1.11, includes Patch #3 verification)."""
from __future__ import annotations
import os
import pytest
from pathlib import Path
from capsule_memory import CapsuleMemory, CapsuleMemoryConfig
from capsule_memory.models.capsule import CapsuleStatus
from capsule_memory.storage.local import LocalStorage


@pytest.fixture(autouse=True)
def mock_extractor_mode():
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    yield
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)


@pytest.fixture
def cm(tmp_path: Path) -> CapsuleMemory:
    storage = LocalStorage(path=tmp_path)
    config = CapsuleMemoryConfig(storage_path=str(tmp_path))
    return CapsuleMemory(
        storage=storage,
        config=config,
        on_skill_trigger=lambda evt: None,
    )


async def test_session_creates_and_seals(cm: CapsuleMemory) -> None:
    async with cm.session("test_user") as session:
        await session.ingest("Hello", "Hi there!")
        await session.ingest("How are you?", "I'm doing well!")

    capsules = await cm.store.list(user_id="test_user")
    assert len(capsules) == 1
    assert capsules[0].lifecycle.status == CapsuleStatus.SEALED


async def test_session_id_format_patch3(cm: CapsuleMemory) -> None:
    """
    Patch #3 verification: session_id should be generated safely without
    accessing dataclass default_factory internals.
    Format: sess_{uuid_hex[:12]}
    """
    ctx = cm.session("test_user")
    tracker = ctx._tracker
    assert tracker.config.session_id.startswith("sess_")
    assert len(tracker.config.session_id) == 17  # "sess_" + 12 hex chars


async def test_session_custom_id(cm: CapsuleMemory) -> None:
    ctx = cm.session("test_user", session_id="custom_session_123")
    tracker = ctx._tracker
    assert tracker.config.session_id == "custom_session_123"


async def test_recall(cm: CapsuleMemory) -> None:
    async with cm.session("test_user") as session:
        await session.ingest("I use Python and Django", "Great choices!")

    result = await cm.recall("Python", user_id="test_user")
    assert "prompt_injection" in result
    assert "facts" in result
    assert "sources" in result


async def test_export_import(cm: CapsuleMemory, tmp_path: Path) -> None:
    async with cm.session("test_user") as session:
        await session.ingest("msg", "resp")

    capsules = await cm.store.list(user_id="test_user")
    capsule_id = capsules[0].capsule_id

    export_path = str(tmp_path / "exported.json")
    await cm.export_capsule(capsule_id, export_path, format="json")
    assert Path(export_path).exists()

    imported = await cm.import_capsule(export_path, user_id="new_user")
    assert imported.identity.user_id == "new_user"
    assert imported.lifecycle.status == CapsuleStatus.IMPORTED


async def test_export_universal(cm: CapsuleMemory, tmp_path: Path) -> None:
    async with cm.session("test_user") as session:
        await session.ingest("msg", "resp")

    capsules = await cm.store.list(user_id="test_user")
    capsule_id = capsules[0].capsule_id

    export_path = str(tmp_path / "universal.json")
    await cm.export_capsule(capsule_id, export_path, format="universal")
    import json
    data = json.loads(Path(export_path).read_text())
    assert data["schema"] == "universal-memory/1.0"


async def test_store_property(cm: CapsuleMemory) -> None:
    assert cm.store is not None
    # CapsuleStore should be accessible for merge/diff/fork operations
    assert hasattr(cm.store, "merge")
    assert hasattr(cm.store, "diff")
    assert hasattr(cm.store, "fork")


async def test_config_from_env() -> None:
    os.environ["CAPSULE_STORAGE_TYPE"] = "local"
    os.environ["CAPSULE_STORAGE_PATH"] = "/tmp/test_capsules"
    try:
        config = CapsuleMemoryConfig.from_env()
        assert config.storage_type == "local"
        assert config.storage_path == "/tmp/test_capsules"
    finally:
        os.environ.pop("CAPSULE_STORAGE_TYPE", None)
        os.environ.pop("CAPSULE_STORAGE_PATH", None)
