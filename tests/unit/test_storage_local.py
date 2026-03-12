from __future__ import annotations
import json
import pytest
from pathlib import Path
from datetime import datetime
from capsule_memory.models.capsule import (
    Capsule, CapsuleType, CapsuleStatus, CapsuleIdentity, CapsuleLifecycle, CapsuleMetadata,
)
from capsule_memory.storage.local import LocalStorage


def make_capsule(user_id: str = "u1", title: str = "Test") -> Capsule:
    return Capsule(
        capsule_type=CapsuleType.MEMORY,
        identity=CapsuleIdentity(user_id=user_id, session_id="s1"),
        lifecycle=CapsuleLifecycle(status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow()),
        metadata=CapsuleMetadata(title=title, tags=["test"]),
        payload={"facts": [], "context_summary": "test", "entities": {}, "timeline": [], "raw_turns": []},
    )


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(path=tmp_path)


async def test_save_and_get(storage: LocalStorage) -> None:
    c = make_capsule()
    await storage.save(c)
    retrieved = await storage.get(c.capsule_id)
    assert retrieved is not None
    assert retrieved.capsule_id == c.capsule_id


async def test_get_nonexistent_returns_none(storage: LocalStorage) -> None:
    assert await storage.get("nonexistent_id") is None


async def test_delete(storage: LocalStorage) -> None:
    c = make_capsule()
    await storage.save(c)
    assert await storage.delete(c.capsule_id) is True
    assert await storage.get(c.capsule_id) is None


async def test_list_filter_by_type(storage: LocalStorage) -> None:
    c1 = make_capsule()
    c1.capsule_type = CapsuleType.MEMORY
    c2 = make_capsule()
    c2.capsule_type = CapsuleType.SKILL
    c2.payload = {"skill_name": "test", "trigger_pattern": "test", "description": "",
                  "instructions": "", "trigger_keywords": [], "examples": [],
                  "applicable_contexts": [], "source_session": "", "reuse_count": 0,
                  "effectiveness_rating": None}
    await storage.save(c1)
    await storage.save(c2)
    memory_list = await storage.list(capsule_type=CapsuleType.MEMORY)
    assert all(c.capsule_type == CapsuleType.MEMORY for c in memory_list)


async def test_list_filter_by_tags(storage: LocalStorage) -> None:
    c1 = make_capsule()
    c1.metadata.tags = ["python", "django"]
    c2 = make_capsule()
    c2.metadata.tags = ["java"]
    await storage.save(c1)
    await storage.save(c2)
    results = await storage.list(tags=["python"])
    ids = [c.capsule_id for c in results]
    assert c1.capsule_id in ids
    assert c2.capsule_id not in ids


async def test_count(storage: LocalStorage) -> None:
    await storage.save(make_capsule())
    await storage.save(make_capsule())
    assert await storage.count() == 2


async def test_export_json(storage: LocalStorage, tmp_path: Path) -> None:
    c = make_capsule()
    await storage.save(c)
    out = tmp_path / "export.json"
    await storage.export_capsule(c.capsule_id, str(out), format="json")
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["capsule_id"] == c.capsule_id


async def test_export_universal(storage: LocalStorage, tmp_path: Path) -> None:
    c = make_capsule()
    await storage.save(c)
    out = tmp_path / "export_universal.json"
    await storage.export_capsule(c.capsule_id, str(out), format="universal")
    data = json.loads(out.read_text())
    assert data["schema"] == "universal-memory/1.0"
    assert "prompt_injection" in data


async def test_export_prompt(storage: LocalStorage, tmp_path: Path) -> None:
    c = make_capsule()
    await storage.save(c)
    out = tmp_path / "snippet.txt"
    await storage.export_capsule(c.capsule_id, str(out), format="prompt")
    text = out.read_text()
    assert "=== Memory Context ===" in text


async def test_import_json_file(storage: LocalStorage, tmp_path: Path) -> None:
    c = make_capsule(user_id="original_user")
    await storage.save(c)
    exported = tmp_path / "cap.json"
    await storage.export_capsule(c.capsule_id, str(exported), format="json")
    imported = await storage.import_capsule_file(str(exported), user_id="new_user")
    assert imported.identity.user_id == "new_user"
    assert imported.lifecycle.status == CapsuleStatus.IMPORTED


async def test_import_universal_file(storage: LocalStorage, tmp_path: Path) -> None:
    c = make_capsule()
    c.lifecycle.sealed_at = datetime.utcnow()
    await storage.save(c)
    exported = tmp_path / "universal.json"
    await storage.export_capsule(c.capsule_id, str(exported), format="universal")
    imported = await storage.import_capsule_file(str(exported), user_id="new_user")
    assert imported.lifecycle.status == CapsuleStatus.IMPORTED
