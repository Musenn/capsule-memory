"""Tests for capsule_memory/cli.py — CLI commands via typer.testing.CliRunner."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from capsule_memory.cli import app as cli_app

runner = CliRunner()


def _seed_capsule(storage_path: str, user_id: str = "test_user") -> str:
    """Create a capsule in storage and return its ID."""
    from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
    from capsule_memory.storage.local import LocalStorage

    storage = LocalStorage(path=storage_path)
    config = CapsuleMemoryConfig(storage_path=storage_path)
    cm = CapsuleMemory(storage=storage, config=config, on_skill_trigger=lambda e: None)

    async def _create():
        async with cm.session(user_id) as session:
            await session.ingest("I use Python and FastAPI", "Great tech stack!")
            await session.ingest("Let's build a REST API", "Sure, let's use FastAPI")
        capsules = await cm.store.list(user_id=user_id)
        return capsules[0].capsule_id

    return asyncio.run(_create())


def _seed_skill_capsule(storage_path: str, user_id: str = "test_user") -> str:
    """Create a skill capsule in storage and return its ID."""
    from capsule_memory.storage.local import LocalStorage
    from capsule_memory.models.capsule import (
        Capsule, CapsuleType, CapsuleIdentity, CapsuleLifecycle,
        CapsuleMetadata, CapsuleStatus,
    )
    from datetime import datetime

    storage = LocalStorage(path=storage_path)
    capsule = Capsule(
        capsule_type=CapsuleType.SKILL,
        identity=CapsuleIdentity(
            user_id=user_id, session_id="manual_extract", origin_platform="test",
        ),
        lifecycle=CapsuleLifecycle(
            status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow(),
        ),
        metadata=CapsuleMetadata(
            title="Test Skill", tags=["test"], turn_count=0,
        ),
        payload={
            "skill_name": "code_formatter",
            "trigger_pattern": "format code",
            "description": "Formats code with black",
            "instructions": "Run black on the file",
        },
    )
    capsule.integrity.checksum = capsule.compute_checksum()
    asyncio.run(storage.save(capsule))
    return capsule.capsule_id


def _invoke(args: list[str], tmp_path: Path, user: str = "test_user") -> object:
    """Invoke CLI with --storage and --user pointing to isolated tmp_path."""
    return runner.invoke(
        cli_app,
        ["--storage", str(tmp_path), "--user", user] + args,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# version command
# ═══════════════════════════════════════════════════════════════════════════════

class TestVersionCommand:
    def test_version(self, tmp_path: Path) -> None:
        result = _invoke(["version"], tmp_path)
        assert result.exit_code == 0
        assert "capsule-memory" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# list command
# ═══════════════════════════════════════════════════════════════════════════════

class TestListCommand:
    def test_list_empty(self, tmp_path: Path) -> None:
        result = _invoke(["list"], tmp_path)
        assert result.exit_code == 0
        assert "No capsules found" in result.output

    def test_list_with_data(self, tmp_path: Path) -> None:
        _seed_capsule(str(tmp_path))
        result = _invoke(["list"], tmp_path)
        assert result.exit_code == 0
        assert "Capsules" in result.output

    def test_list_with_type_filter(self, tmp_path: Path) -> None:
        _seed_capsule(str(tmp_path))
        result = _invoke(["list", "--type", "memory"], tmp_path)
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════════════════════
# show command
# ═══════════════════════════════════════════════════════════════════════════════

class TestShowCommand:
    def test_show_capsule(self, tmp_path: Path) -> None:
        cid = _seed_capsule(str(tmp_path))
        result = _invoke(["show", cid], tmp_path)
        assert result.exit_code == 0
        assert "Capsule" in result.output

    def test_show_not_found(self, tmp_path: Path) -> None:
        result = _invoke(["show", "nonexistent_capsule_id"], tmp_path)
        assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# export command
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportCommand:
    def test_export_json(self, tmp_path: Path) -> None:
        cid = _seed_capsule(str(tmp_path))
        output = str(tmp_path / "export_test.json")
        result = _invoke(["export", cid, output, "--format", "json"], tmp_path)
        assert result.exit_code == 0
        assert Path(output).exists()
        assert "Exported to" in result.output

    def test_export_not_found(self, tmp_path: Path) -> None:
        output = str(tmp_path / "export_test.json")
        result = _invoke(["export", "nonexistent", output], tmp_path)
        assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# import command
# ═══════════════════════════════════════════════════════════════════════════════

class TestImportCommand:
    def test_import_json(self, tmp_path: Path) -> None:
        cid = _seed_capsule(str(tmp_path))

        # Export first
        export_path = str(tmp_path / "to_import.json")
        export_result = _invoke(
            ["export", cid, export_path, "--format", "json"], tmp_path
        )
        assert export_result.exit_code == 0
        assert Path(export_path).exists()

        # Import
        result = _invoke(["import", export_path], tmp_path)
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_import_nonexistent_file(self, tmp_path: Path) -> None:
        result = _invoke(["import", "/tmp/no_such_file_xyz.json"], tmp_path)
        assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# recall command
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecallCommand:
    def test_recall(self, tmp_path: Path) -> None:
        _seed_capsule(str(tmp_path))
        result = _invoke(["recall", "Python"], tmp_path)
        assert result.exit_code == 0
        assert "Recalled Context" in result.output

    def test_recall_no_data(self, tmp_path: Path) -> None:
        result = _invoke(["recall", "anything"], tmp_path)
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════════════════════
# skills command
# ═══════════════════════════════════════════════════════════════════════════════

class TestSkillsCommand:
    def test_skills_empty(self, tmp_path: Path) -> None:
        result = _invoke(["skills"], tmp_path)
        assert result.exit_code == 0
        assert "No skill capsules found" in result.output

    def test_skills_with_skill_capsule(self, tmp_path: Path) -> None:
        _seed_skill_capsule(str(tmp_path))
        result = _invoke(["skills"], tmp_path)
        assert result.exit_code == 0
        assert "Skills" in result.output
        assert "code_formatter" in result.output

    def test_skills_with_hybrid_capsule(self, tmp_path: Path) -> None:
        """Test skills listing with a hybrid capsule that has skills."""
        from capsule_memory.storage.local import LocalStorage
        from capsule_memory.models.capsule import (
            Capsule, CapsuleType, CapsuleIdentity, CapsuleLifecycle,
            CapsuleMetadata, CapsuleStatus,
        )
        from datetime import datetime

        storage = LocalStorage(path=str(tmp_path))
        capsule = Capsule(
            capsule_type=CapsuleType.HYBRID,
            identity=CapsuleIdentity(
                user_id="test_user", session_id="s1", origin_platform="test",
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.SEALED, sealed_at=datetime.utcnow(),
            ),
            metadata=CapsuleMetadata(title="Hybrid", tags=["test"]),
            payload={
                "memory": {"facts": [], "context_summary": "test"},
                "skills": [
                    {"skill_name": "hybrid_skill", "trigger_pattern": "do stuff"},
                ],
            },
        )
        capsule.integrity.checksum = capsule.compute_checksum()
        asyncio.run(storage.save(capsule))

        result = _invoke(["skills"], tmp_path)
        assert result.exit_code == 0
        assert "hybrid_skill" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# merge command
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeCommand:
    def test_merge_two_capsules(self, tmp_path: Path) -> None:
        cid1 = _seed_capsule(str(tmp_path), user_id="u1")
        cid2 = _seed_capsule(str(tmp_path), user_id="u2")
        result = _invoke(["merge", cid1, cid2, "--title", "Merged"], tmp_path)
        assert result.exit_code == 0
        assert "Merged" in result.output

    def test_merge_not_found(self, tmp_path: Path) -> None:
        result = _invoke(["merge", "id1", "id2"], tmp_path)
        assert result.exit_code == 1
