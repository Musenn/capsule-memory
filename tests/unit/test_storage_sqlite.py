"""Tests for SQLiteStorage (T2.1), includes Patch #5 verification."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from capsule_memory.exceptions import CapsuleNotFoundError
from capsule_memory.models.capsule import (
    Capsule,
    CapsuleIdentity,
    CapsuleLifecycle,
    CapsuleMetadata,
    CapsuleStatus,
    CapsuleType,
)

# All tests require sqlite-vec and sentence-transformers
pytestmark = pytest.mark.skipif(
    not (
        _has_deps := (
            __import__("importlib").util.find_spec("sqlite_vec") is not None
            and __import__("importlib").util.find_spec("sentence_transformers") is not None
        )
    ),
    reason="SQLiteStorage requires capsule-memory[sqlite] extras",
)


def _make_capsule(
    user_id: str = "test_user",
    title: str = "Test Capsule",
    capsule_type: CapsuleType = CapsuleType.MEMORY,
    tags: list[str] | None = None,
) -> Capsule:
    """Helper to create a test capsule."""
    return Capsule(
        capsule_type=capsule_type,
        identity=CapsuleIdentity(user_id=user_id, session_id="test_session"),
        lifecycle=CapsuleLifecycle(
            status=CapsuleStatus.SEALED,
            sealed_at=datetime.utcnow(),
        ),
        metadata=CapsuleMetadata(
            title=title,
            tags=tags or ["test"],
            turn_count=3,
        ),
        payload={
            "facts": [
                {
                    "key": "user.lang",
                    "value": "Python",
                    "confidence": 0.9,
                }
            ],
            "context_summary": f"Summary for {title}",
            "entities": {},
            "timeline": [],
            "raw_turns": [],
        },
    )


@pytest.fixture
def storage(tmp_path: Path):
    """Create a SQLiteStorage instance using a temp directory."""
    from capsule_memory.storage.sqlite import SQLiteStorage

    return SQLiteStorage(path=str(tmp_path))


async def test_save_and_get(storage) -> None:
    """Save a capsule and retrieve it by ID."""
    capsule = _make_capsule()
    saved_id = await storage.save(capsule)
    assert saved_id == capsule.capsule_id

    retrieved = await storage.get(capsule.capsule_id)
    assert retrieved is not None
    assert retrieved.capsule_id == capsule.capsule_id
    assert retrieved.metadata.title == "Test Capsule"
    assert retrieved.identity.user_id == "test_user"


async def test_get_nonexistent(storage) -> None:
    """Getting a nonexistent capsule returns None."""
    result = await storage.get("nonexistent_id")
    assert result is None


async def test_delete(storage) -> None:
    """Delete a capsule and verify it's gone."""
    capsule = _make_capsule()
    await storage.save(capsule)

    deleted = await storage.delete(capsule.capsule_id)
    assert deleted is True

    result = await storage.get(capsule.capsule_id)
    assert result is None

    deleted_again = await storage.delete(capsule.capsule_id)
    assert deleted_again is False


async def test_list_filter_by_type(storage) -> None:
    """List capsules filtered by type."""
    mem = _make_capsule(title="Memory Capsule", capsule_type=CapsuleType.MEMORY)
    skill = Capsule(
        capsule_type=CapsuleType.SKILL,
        identity=CapsuleIdentity(user_id="test_user", session_id="s2"),
        lifecycle=CapsuleLifecycle(
            status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow()
        ),
        metadata=CapsuleMetadata(title="Skill Capsule", tags=["skill"]),
        payload={
            "skill_name": "test_skill",
            "description": "A test skill",
            "instructions": "Do the thing",
            "trigger_pattern": "when asked",
        },
    )
    await storage.save(mem)
    await storage.save(skill)

    memory_list = await storage.list(
        user_id="test_user", capsule_type=CapsuleType.MEMORY
    )
    assert len(memory_list) == 1
    assert memory_list[0].capsule_type == CapsuleType.MEMORY

    skill_list = await storage.list(
        user_id="test_user", capsule_type=CapsuleType.SKILL
    )
    assert len(skill_list) == 1
    assert skill_list[0].capsule_type == CapsuleType.SKILL


async def test_list_filter_by_tags(storage) -> None:
    """List capsules filtered by tags."""
    c1 = _make_capsule(title="C1", tags=["python", "django"])
    c2 = _make_capsule(title="C2", tags=["python", "flask"])
    await storage.save(c1)
    await storage.save(c2)

    django_caps = await storage.list(user_id="test_user", tags=["django"])
    assert len(django_caps) == 1
    assert "django" in django_caps[0].metadata.tags

    python_caps = await storage.list(user_id="test_user", tags=["python"])
    assert len(python_caps) == 2


async def test_count(storage) -> None:
    """Count capsules with optional user filter."""
    c1 = _make_capsule(user_id="user_a", title="C1")
    c2 = _make_capsule(user_id="user_a", title="C2")
    c3 = _make_capsule(user_id="user_b", title="C3")
    await storage.save(c1)
    await storage.save(c2)
    await storage.save(c3)

    assert await storage.count() == 3
    assert await storage.count(user_id="user_a") == 2
    assert await storage.count(user_id="user_b") == 1


async def test_search_returns_results(storage) -> None:
    """Vector search returns relevant results."""
    c1 = _make_capsule(title="Python Django optimization")
    c2 = _make_capsule(title="JavaScript React tutorial")
    await storage.save(c1)
    await storage.save(c2)

    results = await storage.search("Django query", user_id="test_user")
    assert len(results) > 0
    # Results are (Capsule, score) tuples
    for capsule, score in results:
        assert isinstance(capsule, Capsule)
        assert 0.0 <= score <= 1.0


async def test_upsert_updates_existing(storage) -> None:
    """Saving a capsule with the same ID updates it."""
    capsule = _make_capsule(title="Original Title")
    await storage.save(capsule)

    # Modify and save again
    capsule.metadata.title = "Updated Title"
    await storage.save(capsule)

    retrieved = await storage.get(capsule.capsule_id)
    assert retrieved is not None
    assert retrieved.metadata.title == "Updated Title"
    assert await storage.count() == 1


async def test_export_json(storage, tmp_path: Path) -> None:
    """Export a capsule to JSON format."""
    capsule = _make_capsule()
    await storage.save(capsule)

    export_path = str(tmp_path / "exported.json")
    result = await storage.export_capsule(capsule.capsule_id, export_path, format="json")
    assert result.exists()
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["capsule_id"] == capsule.capsule_id


async def test_export_universal(storage, tmp_path: Path) -> None:
    """Export a capsule to universal format."""
    capsule = _make_capsule()
    await storage.save(capsule)

    export_path = str(tmp_path / "universal.json")
    result = await storage.export_capsule(
        capsule.capsule_id, export_path, format="universal"
    )
    assert result.exists()
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["schema"] == "universal-memory/1.0"


async def test_export_nonexistent_raises(storage, tmp_path: Path) -> None:
    """Exporting a nonexistent capsule raises CapsuleNotFoundError."""
    with pytest.raises(CapsuleNotFoundError):
        await storage.export_capsule(
            "nonexistent_id", str(tmp_path / "out.json"), format="json"
        )


async def test_import_json_file(storage, tmp_path: Path) -> None:
    """Import a capsule from a JSON file."""
    # First export a capsule
    capsule = _make_capsule()
    await storage.save(capsule)

    export_path = str(tmp_path / "to_import.json")
    await storage.export_capsule(capsule.capsule_id, export_path, format="json")

    # Import it as a new user
    imported = await storage.import_capsule_file(export_path, user_id="new_user")
    assert imported.identity.user_id == "new_user"
    assert imported.lifecycle.status == CapsuleStatus.IMPORTED

    # Verify it's in SQLite
    retrieved = await storage.get(imported.capsule_id)
    assert retrieved is not None


async def test_sqlite_and_local_helper_use_different_dirs(tmp_path: Path) -> None:
    """
    Patch #5 verification: SQLiteStorage's _local_export_helper uses an
    isolated subdirectory to avoid index.json conflicts with .db files.
    """
    from capsule_memory.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(path=str(tmp_path))

    db_dir = tmp_path  # SQLite .db file directory
    helper_dir = Path(storage._local_export_helper.root)

    # The two directories must be different
    assert db_dir.resolve() != helper_dir.resolve(), (
        f"SQLiteStorage and LocalStorage helper use the same directory {db_dir}, "
        f"which could cause index.json / .db file naming conflicts."
    )

    # Helper directory should be a subdirectory of the db directory
    assert str(helper_dir).startswith(str(db_dir)), (
        f"LocalStorage helper directory {helper_dir} should be under {db_dir}."
    )
