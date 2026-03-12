"""Integration tests for MCP Server tool simulation (T4.1)."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def mock_mode():
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    yield
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)


@pytest.fixture
def mcp_env(tmp_path):
    """Set up MCP server environment."""
    from capsule_memory.server import mcp_server

    mcp_server.init_capsule_memory(
        storage_path=str(tmp_path), storage_type="local"
    )
    mcp_server._active_sessions.clear()
    mcp_server._pending_trigger_events.clear()
    return mcp_server


async def test_capsule_ingest(mcp_env) -> None:
    """Simulate capsule_ingest tool call."""
    from capsule_memory.server.mcp_server import _get_or_create_session

    tracker = _get_or_create_session("test_user", "test_session")
    turn = await tracker.ingest("Hello", "Hi there!")
    assert turn.turn_id == 1
    assert len(tracker.state.turns) == 2


async def test_capsule_seal(mcp_env) -> None:
    """Simulate capsule_seal tool call."""
    from capsule_memory.server.mcp_server import (
        _get_or_create_session,
        get_cm,
    )

    tracker = _get_or_create_session("seal_user", "seal_session")
    await tracker.ingest("Test msg", "Test resp")

    capsule = await tracker.seal(title="MCP Test", tags=["mcp"])
    assert capsule.metadata.title == "MCP Test"
    assert capsule.metadata.turn_count == 2

    # Verify capsule persisted
    cm = get_cm()
    capsules = await cm._storage.list(user_id="seal_user")
    assert len(capsules) >= 1


async def test_capsule_recall(mcp_env) -> None:
    """Simulate capsule_recall tool call."""
    from capsule_memory.server.mcp_server import (
        _get_or_create_session,
        get_cm,
    )

    # First create and seal a session
    tracker = _get_or_create_session("recall_user", "recall_sess")
    await tracker.ingest("Python Django", "Great choices!")
    await tracker.seal()

    # Now recall
    cm = get_cm()
    result = await cm.recall("Python", user_id="recall_user")
    assert "prompt_injection" in result
    assert "facts" in result
    assert "sources" in result


async def test_capsule_list(mcp_env) -> None:
    """Simulate capsule_list tool call."""
    from capsule_memory.server.mcp_server import (
        _get_or_create_session,
        get_cm,
    )

    tracker = _get_or_create_session("list_user", "list_sess")
    await tracker.ingest("msg", "resp")
    await tracker.seal()

    cm = get_cm()
    capsules = await cm._storage.list(user_id="list_user")
    assert len(capsules) >= 1
    assert capsules[0].metadata.turn_count >= 2


async def test_capsule_export_import(mcp_env, tmp_path) -> None:
    """Simulate capsule_export and capsule_import tool calls."""
    from capsule_memory.server.mcp_server import (
        _get_or_create_session,
        get_cm,
    )

    tracker = _get_or_create_session("export_user", "export_sess")
    await tracker.ingest("Export test", "Response")
    capsule = await tracker.seal()

    cm = get_cm()

    # Export
    export_path = str(tmp_path / "mcp_export.json")
    result = await cm._storage.export_capsule(
        capsule.capsule_id, export_path, format="json"
    )
    assert result.exists()

    # Import
    imported = await cm._storage.import_capsule_file(
        export_path, user_id="import_user"
    )
    assert imported.identity.user_id == "import_user"


async def test_capsule_inject_context(mcp_env) -> None:
    """Simulate capsule_inject_context tool call."""
    from capsule_memory.server.mcp_server import (
        _get_or_create_session,
        get_cm,
    )

    tracker = _get_or_create_session("ctx_user", "ctx_sess")
    await tracker.ingest("Context test", "Response data")
    await tracker.seal()

    cm = get_cm()
    result = await cm.recall("Context", user_id="ctx_user")
    assert isinstance(result["prompt_injection"], str)


async def test_capsule_extract_skill(mcp_env) -> None:
    """Simulate capsule_extract_skill tool call."""
    from capsule_memory.core.builder import CapsuleBuilder
    from capsule_memory.core.session import SessionConfig
    from capsule_memory.models.skill import SkillPayload
    from capsule_memory.server.mcp_server import get_cm

    cm = get_cm()
    skill_payload = SkillPayload(
        skill_name="Test Skill",
        trigger_pattern="when testing",
        description="A test skill for MCP",
        instructions="Do the test thing",
    )
    config = SessionConfig(user_id="skill_user", session_id="manual_extract")
    capsule = CapsuleBuilder.build_skill(config, skill_payload, tags=["test"])
    await cm._storage.save(capsule)

    # Verify the skill capsule
    retrieved = await cm._storage.get(capsule.capsule_id)
    assert retrieved is not None
    assert retrieved.capsule_type.value == "skill"
