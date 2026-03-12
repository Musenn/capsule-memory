"""Tests for capsule_memory/server/mcp_server.py — tool dispatch logic."""
from __future__ import annotations

import json
import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

from pathlib import Path

import pytest

from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
from capsule_memory.storage.local import LocalStorage

# Force-reload mcp_server so _MCP_AVAILABLE is re-evaluated
# (handles case where mcp is installed after first import)
import importlib
import capsule_memory.server.mcp_server as mcp_module
importlib.reload(mcp_module)


@pytest.fixture
def _setup_mcp(tmp_path: Path):
    """Initialize MCP module globals with isolated storage."""
    storage = LocalStorage(path=tmp_path)
    config = CapsuleMemoryConfig(storage_path=str(tmp_path))
    cm = CapsuleMemory(storage=storage, config=config, on_skill_trigger=lambda e: None)

    old_cm = mcp_module._cm
    old_sessions = mcp_module._active_sessions.copy()
    old_triggers = mcp_module._pending_trigger_events.copy()

    mcp_module._cm = cm
    mcp_module._active_sessions.clear()
    mcp_module._pending_trigger_events.clear()

    yield cm, tmp_path

    mcp_module._cm = old_cm
    mcp_module._active_sessions.clear()
    mcp_module._active_sessions.update(old_sessions)
    mcp_module._pending_trigger_events.clear()
    mcp_module._pending_trigger_events.update(old_triggers)


# ═══════════════════════════════════════════════════════════════════════════════
# init / get_cm (no mcp dependency needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInitialization:
    def test_get_cm_raises_when_not_initialized(self) -> None:
        old = mcp_module._cm
        mcp_module._cm = None
        try:
            with pytest.raises(RuntimeError, match="not initialized"):
                mcp_module.get_cm()
        finally:
            mcp_module._cm = old

    def test_init_capsule_memory(self, tmp_path: Path) -> None:
        old = mcp_module._cm
        try:
            mcp_module._cm = None
            mcp_module.init_capsule_memory(
                storage_path=str(tmp_path), storage_type="local"
            )
            assert mcp_module._cm is not None
        finally:
            mcp_module._cm = old


# ═══════════════════════════════════════════════════════════════════════════════
# _get_or_create_session (no mcp dependency needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetOrCreateSession:
    def test_creates_new_session(self, _setup_mcp) -> None:
        tracker = mcp_module._get_or_create_session("user1")
        assert tracker is not None
        assert "user1" in mcp_module._active_sessions

    def test_returns_existing_session(self, _setup_mcp) -> None:
        t1 = mcp_module._get_or_create_session("user1")
        t2 = mcp_module._get_or_create_session("user1")
        assert t1 is t2

    def test_custom_session_id(self, _setup_mcp) -> None:
        tracker = mcp_module._get_or_create_session("user1", session_id="custom_123")
        assert tracker.config.session_id == "custom_123"


# ═══════════════════════════════════════════════════════════════════════════════
# Tool dispatch (requires mcp package — skip entire class if not installed)
# ═══════════════════════════════════════════════════════════════════════════════

def _check_mcp_available():
    try:
        from mcp.server import Server  # noqa: F401
        from mcp.server.stdio import stdio_server  # noqa: F401
        from mcp import types  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _check_mcp_available(), reason="mcp package not installed")
class TestToolDispatch:
    """Test the call_tool dispatcher by building the server and calling it."""

    @pytest.fixture
    def server(self, _setup_mcp):
        return mcp_module._build_server()

    async def _call_tool(self, server, name: str, arguments: dict) -> list:
        """Invoke the call_tool handler registered on the server."""
        from mcp.types import CallToolRequest, CallToolRequestParams

        handler = server.request_handlers.get(CallToolRequest)
        if handler is None:
            pytest.skip("Cannot access MCP server call_tool handler")

        request = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=name, arguments=arguments),
        )
        result = await handler(request)
        # ServerResult wraps the actual result; access root or model fields
        if hasattr(result, "content"):
            return result.content
        # mcp >= 1.x returns ServerResult with root attribute
        inner = getattr(result, "root", result)
        if hasattr(inner, "content"):
            return inner.content
        # Try model_dump
        dumped = result.model_dump() if hasattr(result, "model_dump") else {}
        return dumped.get("content", dumped.get("root", {}).get("content", []))

    async def test_capsule_ingest(self, server) -> None:
        results = await self._call_tool(server, "capsule_ingest", {
            "user_message": "hello",
            "assistant_response": "world",
            "user_id": "test_user",
        })
        assert len(results) >= 1
        data = json.loads(results[0].text)
        assert "turn_id" in data
        assert data["total_turns"] == 2

    async def test_capsule_seal(self, server) -> None:
        await self._call_tool(server, "capsule_ingest", {
            "user_message": "msg",
            "assistant_response": "resp",
            "user_id": "test_user",
        })
        results = await self._call_tool(server, "capsule_seal", {
            "user_id": "test_user",
            "title": "Test Capsule",
            "tags": ["test"],
        })
        data = json.loads(results[0].text)
        assert "capsule_id" in data
        assert data["title"] == "Test Capsule"

    async def test_capsule_seal_no_session(self, server) -> None:
        results = await self._call_tool(server, "capsule_seal", {
            "user_id": "no_such_user",
        })
        data = json.loads(results[0].text)
        assert "error" in data

    async def test_capsule_recall(self, server) -> None:
        await self._call_tool(server, "capsule_ingest", {
            "user_message": "I use Python", "assistant_response": "Nice!",
            "user_id": "u1",
        })
        await self._call_tool(server, "capsule_seal", {"user_id": "u1"})

        results = await self._call_tool(server, "capsule_recall", {
            "query": "Python", "user_id": "u1",
        })
        data = json.loads(results[0].text)
        assert "prompt_injection" in data

    async def test_capsule_inject_context(self, server) -> None:
        await self._call_tool(server, "capsule_ingest", {
            "user_message": "msg", "assistant_response": "resp",
            "user_id": "u1",
        })
        await self._call_tool(server, "capsule_seal", {"user_id": "u1"})

        results = await self._call_tool(server, "capsule_inject_context", {
            "query": "test", "user_id": "u1",
        })
        assert isinstance(results[0].text, str)

    async def test_capsule_list(self, server) -> None:
        results = await self._call_tool(server, "capsule_list", {
            "user_id": "test_user",
        })
        data = json.loads(results[0].text)
        assert isinstance(data, list)

    async def test_capsule_pending_triggers(self, server) -> None:
        results = await self._call_tool(server, "capsule_pending_triggers", {
            "user_id": "test_user",
        })
        data = json.loads(results[0].text)
        assert "pending" in data

    async def test_capsule_confirm_trigger_no_session(self, server) -> None:
        results = await self._call_tool(server, "capsule_confirm_trigger", {
            "event_id": "evt_xxx",
            "resolution": "ignore",
            "user_id": "no_user",
        })
        data = json.loads(results[0].text)
        assert "error" in data

    async def test_capsule_extract_skill(self, server) -> None:
        results = await self._call_tool(server, "capsule_extract_skill", {
            "skill_description": "A skill that formats code with black",
            "skill_name": "code_formatter",
            "tags": ["code"],
            "user_id": "u1",
        })
        data = json.loads(results[0].text)
        assert "skill_capsule_id" in data
        assert data["skill_name"] == "code_formatter"

    async def test_unknown_tool(self, server) -> None:
        results = await self._call_tool(server, "nonexistent_tool", {})
        data = json.loads(results[0].text)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    async def test_capsule_export(self, server, _setup_mcp) -> None:
        _, tmp_path = _setup_mcp
        # Create a capsule first
        await self._call_tool(server, "capsule_ingest", {
            "user_message": "export test msg", "assistant_response": "ok",
            "user_id": "export_user",
        })
        seal_result = await self._call_tool(server, "capsule_seal", {
            "user_id": "export_user", "title": "Export Test",
        })
        capsule_id = json.loads(seal_result[0].text)["capsule_id"]

        output_path = str(tmp_path / "exports" / "test_export.json")
        results = await self._call_tool(server, "capsule_export", {
            "capsule_id": capsule_id,
            "format": "json",
            "output_path": output_path,
        })
        data = json.loads(results[0].text)
        assert "path" in data
        assert data["format"] == "json"

    async def test_capsule_import(self, server, _setup_mcp) -> None:
        _, tmp_path = _setup_mcp
        # Create and export first
        await self._call_tool(server, "capsule_ingest", {
            "user_message": "import test", "assistant_response": "ok",
            "user_id": "import_user",
        })
        seal_result = await self._call_tool(server, "capsule_seal", {
            "user_id": "import_user",
        })
        capsule_id = json.loads(seal_result[0].text)["capsule_id"]

        export_path = str(tmp_path / "exports" / "import_test.json")
        await self._call_tool(server, "capsule_export", {
            "capsule_id": capsule_id,
            "format": "json",
            "output_path": export_path,
        })

        results = await self._call_tool(server, "capsule_import", {
            "file_path": export_path,
            "user_id": "new_user",
        })
        data = json.loads(results[0].text)
        assert "capsule_id" in data

    async def test_capsule_recall_exclude_skills(self, server) -> None:
        await self._call_tool(server, "capsule_ingest", {
            "user_message": "hello", "assistant_response": "world",
            "user_id": "recall_user",
        })
        await self._call_tool(server, "capsule_seal", {"user_id": "recall_user"})
        results = await self._call_tool(server, "capsule_recall", {
            "query": "hello", "user_id": "recall_user",
            "include_skills": False,
        })
        data = json.loads(results[0].text)
        assert data["skills"] == []

    async def test_list_tools(self, _setup_mcp) -> None:
        """Test the list_tools handler."""
        from mcp.types import ListToolsRequest

        server = mcp_module._build_server()
        handler = server.request_handlers.get(ListToolsRequest)
        if handler is None:
            pytest.skip("Cannot access list_tools handler")

        request = ListToolsRequest(method="tools/list")
        result = await handler(request)
        inner = getattr(result, "root", result)
        tools = getattr(inner, "tools", [])
        tool_names = [t.name for t in tools]
        assert "capsule_ingest" in tool_names
        assert "capsule_seal" in tool_names
        assert "capsule_recall" in tool_names
        assert len(tools) == 10
