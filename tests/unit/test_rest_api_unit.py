"""Tests for capsule_memory/server/rest_api.py using httpx AsyncClient."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

from pathlib import Path

import pytest

from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
from capsule_memory.storage.local import LocalStorage

# Import rest_api module to manipulate its globals
import capsule_memory.server.rest_api as rest_api_module


@pytest.fixture
def _setup_app(tmp_path: Path):
    """Create a fresh app with isolated storage for each test."""
    storage = LocalStorage(path=tmp_path)
    config = CapsuleMemoryConfig(storage_path=str(tmp_path))
    cm = CapsuleMemory(storage=storage, config=config, on_skill_trigger=lambda e: None)

    # Inject _cm and clear sessions
    old_cm = rest_api_module._cm
    old_sessions = rest_api_module._active_sessions.copy()
    old_app = rest_api_module.app

    rest_api_module._cm = cm
    rest_api_module._active_sessions.clear()
    rest_api_module.app = None  # force rebuild

    yield

    rest_api_module._cm = old_cm
    rest_api_module._active_sessions.clear()
    rest_api_module._active_sessions.update(old_sessions)
    rest_api_module.app = old_app


@pytest.fixture
def app(_setup_app):
    """Get the FastAPI app."""
    return rest_api_module._ensure_app()


@pytest.fixture
async def client(app):
    """Create an httpx AsyncClient for the app."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    async def test_health(self, client) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Session endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionEndpoints:
    async def test_create_session(self, client) -> None:
        resp = await client.post(
            "/api/v1/sessions",
            params={"user_id": "u1", "session_id": "s1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "s1"
        assert data["user_id"] == "u1"

    async def test_create_session_auto_id(self, client) -> None:
        resp = await client.post("/api/v1/sessions", params={"user_id": "u2"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"].startswith("sess_")

    async def test_ingest_turn(self, client) -> None:
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        resp = await client.post(
            "/api/v1/sessions/s1/ingest",
            json={"user_message": "hello", "assistant_response": "hi"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_id"] == 1
        assert data["total_turns"] == 2  # user + assistant

    async def test_ingest_missing_fields(self, client) -> None:
        await client.post("/api/v1/sessions", params={"session_id": "s2"})
        resp = await client.post(
            "/api/v1/sessions/s2/ingest",
            json={"user_message": "hello"},
        )
        assert resp.status_code == 400

    async def test_get_snapshot(self, client) -> None:
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        await client.post(
            "/api/v1/sessions/s1/ingest",
            json={"user_message": "hi", "assistant_response": "hey"},
        )
        resp = await client.get("/api/v1/sessions/s1/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_count"] == 2
        assert data["is_active"] is True

    async def test_get_snapshot_not_found(self, client) -> None:
        resp = await client.get("/api/v1/sessions/nonexistent/snapshot")
        assert resp.status_code == 404

    async def test_seal_session(self, client) -> None:
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        await client.post(
            "/api/v1/sessions/s1/ingest",
            json={"user_message": "msg", "assistant_response": "resp"},
        )
        resp = await client.post(
            "/api/v1/sessions/s1/seal",
            json={"title": "Test Session", "tags": ["t1"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "capsule_id" in data
        assert data["title"] == "Test Session"

    async def test_seal_not_found(self, client) -> None:
        resp = await client.post(
            "/api/v1/sessions/nope/seal",
            json={},
        )
        assert resp.status_code == 404

    async def test_get_session_triggers(self, client) -> None:
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        resp = await client.get("/api/v1/sessions/s1/triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["triggers"] == []
        assert data["count"] == 0

    async def test_get_session_triggers_not_found(self, client) -> None:
        resp = await client.get("/api/v1/sessions/nope/triggers")
        assert resp.status_code == 404

    async def test_confirm_trigger_invalid_resolution(self, client) -> None:
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        resp = await client.post(
            "/api/v1/sessions/s1/triggers/evt_xxx/confirm",
            json={"resolution": "bad_value"},
        )
        assert resp.status_code == 400

    async def test_confirm_trigger_session_not_found(self, client) -> None:
        resp = await client.post(
            "/api/v1/sessions/nope/triggers/evt_xxx/confirm",
            json={"resolution": "ignore"},
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Capsule CRUD endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapsuleEndpoints:
    async def _create_capsule(self, client) -> str:
        """Helper: create a session, ingest, seal, return capsule_id."""
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        await client.post(
            "/api/v1/sessions/s1/ingest",
            json={"user_message": "I use Python", "assistant_response": "Great!"},
        )
        resp = await client.post(
            "/api/v1/sessions/s1/seal",
            json={"title": "Test", "tags": ["python"]},
        )
        return resp.json()["capsule_id"]

    async def test_list_capsules_empty(self, client) -> None:
        resp = await client.get("/api/v1/capsules")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_capsules_with_data(self, client) -> None:
        await self._create_capsule(client)
        resp = await client.get("/api/v1/capsules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "capsule_id" in data[0]

    async def test_get_capsule(self, client) -> None:
        cid = await self._create_capsule(client)
        resp = await client.get(f"/api/v1/capsules/{cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["capsule_id"] == cid

    async def test_get_capsule_not_found(self, client) -> None:
        resp = await client.get("/api/v1/capsules/nonexistent_id")
        assert resp.status_code == 404

    async def test_delete_capsule(self, client) -> None:
        cid = await self._create_capsule(client)
        resp = await client.delete(f"/api/v1/capsules/{cid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify it's gone
        resp2 = await client.get(f"/api/v1/capsules/{cid}")
        assert resp2.status_code == 404

    async def test_delete_capsule_not_found(self, client) -> None:
        resp = await client.delete("/api/v1/capsules/nonexistent_id")
        assert resp.status_code == 404

    async def test_get_prompt_snippet(self, client) -> None:
        cid = await self._create_capsule(client)
        resp = await client.get(f"/api/v1/capsules/{cid}/prompt-snippet")
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert "Memory Context" in data["text"]

    async def test_get_prompt_snippet_not_found(self, client) -> None:
        resp = await client.get("/api/v1/capsules/nonexistent/prompt-snippet")
        assert resp.status_code == 404

    async def test_export_capsule_json(self, client) -> None:
        cid = await self._create_capsule(client)
        resp = await client.get(f"/api/v1/capsules/{cid}/export", params={"format": "json"})
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"

    async def test_export_capsule_not_found(self, client) -> None:
        resp = await client.get("/api/v1/capsules/nonexistent/export")
        assert resp.status_code == 404

    async def test_pending_triggers_endpoint(self, client) -> None:
        resp = await client.get("/api/v1/capsules/pending-triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["triggers"] == []
        assert data["count"] == 0

    async def test_merge_capsules_too_few(self, client) -> None:
        resp = await client.post(
            "/api/v1/capsules/merge",
            json={"capsule_ids": ["one"]},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Recall endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecallEndpoint:
    async def test_recall(self, client) -> None:
        # Create some data first
        await client.post("/api/v1/sessions", params={"session_id": "s1"})
        await client.post(
            "/api/v1/sessions/s1/ingest",
            json={"user_message": "Python is great", "assistant_response": "Agreed!"},
        )
        await client.post("/api/v1/sessions/s1/seal", json={})

        resp = await client.get("/api/v1/recall", params={"q": "Python"})
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt_injection" in data
        assert "facts" in data
        assert "sources" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Auth middleware
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthMiddleware:
    async def test_auth_required_when_key_set(self, client) -> None:
        old = os.environ.get("CAPSULE_API_KEY")
        os.environ["CAPSULE_API_KEY"] = "test-secret-key"
        try:
            resp = await client.get("/api/v1/capsules")
            assert resp.status_code == 401

            resp2 = await client.get(
                "/api/v1/capsules",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert resp2.status_code == 200
        finally:
            if old:
                os.environ["CAPSULE_API_KEY"] = old
            else:
                os.environ.pop("CAPSULE_API_KEY", None)


# ═══════════════════════════════════════════════════════════════════════════════
# Import endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestImportEndpoint:
    async def _create_capsule(self, client) -> str:
        await client.post("/api/v1/sessions", params={"session_id": "si"})
        await client.post(
            "/api/v1/sessions/si/ingest",
            json={"user_message": "msg", "assistant_response": "resp"},
        )
        resp = await client.post("/api/v1/sessions/si/seal", json={})
        return resp.json()["capsule_id"]

    async def test_import_capsule(self, client) -> None:
        # First create and export a capsule
        cid = await self._create_capsule(client)
        export_resp = await client.get(
            f"/api/v1/capsules/{cid}/export", params={"format": "json"}
        )
        assert export_resp.status_code == 200
        file_content = export_resp.content

        # Import it
        resp = await client.post(
            "/api/v1/capsules/import",
            files={"file": ("test.json", file_content, "application/json")},
            data={"user_id": "import_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "capsule_id" in data

    async def test_import_invalid_file(self, client) -> None:
        resp = await client.post(
            "/api/v1/capsules/import",
            files={"file": ("bad.json", b"not valid json", "application/json")},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Merge endpoint with real data
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeEndpoint:
    async def _create_capsule(self, client, session_id: str) -> str:
        await client.post("/api/v1/sessions", params={"session_id": session_id})
        await client.post(
            f"/api/v1/sessions/{session_id}/ingest",
            json={"user_message": "msg", "assistant_response": "resp"},
        )
        resp = await client.post(f"/api/v1/sessions/{session_id}/seal", json={})
        return resp.json()["capsule_id"]

    async def test_merge_success(self, client) -> None:
        cid1 = await self._create_capsule(client, "merge_s1")
        cid2 = await self._create_capsule(client, "merge_s2")
        resp = await client.post(
            "/api/v1/capsules/merge",
            json={"capsule_ids": [cid1, cid2], "title": "Merged"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "capsule_id" in data
        assert data["title"] == "Merged"


# ═══════════════════════════════════════════════════════════════════════════════
# Confirm trigger success path
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfirmTriggerSuccess:
    async def test_confirm_trigger_event_not_found(self, client) -> None:
        """Confirm trigger with valid resolution but event not in session."""
        await client.post("/api/v1/sessions", params={"session_id": "ct1"})
        resp = await client.post(
            "/api/v1/sessions/ct1/triggers/evt_nonexistent/confirm",
            json={"resolution": "ignore"},
        )
        # Event not found in the session triggers → 404
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# List with filters
# ═══════════════════════════════════════════════════════════════════════════════

class TestListFilters:
    async def test_list_with_type_filter(self, client) -> None:
        resp = await client.get(
            "/api/v1/capsules", params={"type": "memory"}
        )
        assert resp.status_code == 200

    async def test_list_with_tags_filter(self, client) -> None:
        resp = await client.get(
            "/api/v1/capsules", params={"tags": "tag1,tag2"}
        )
        assert resp.status_code == 200

    async def test_list_with_pagination(self, client) -> None:
        resp = await client.get(
            "/api/v1/capsules", params={"limit": 5, "offset": 0}
        )
        assert resp.status_code == 200

    async def test_export_prompt_format(self, client) -> None:
        """Test export in prompt format."""
        await client.post("/api/v1/sessions", params={"session_id": "ef"})
        await client.post(
            "/api/v1/sessions/ef/ingest",
            json={"user_message": "msg", "assistant_response": "resp"},
        )
        seal_resp = await client.post("/api/v1/sessions/ef/seal", json={})
        cid = seal_resp.json()["capsule_id"]

        resp = await client.get(
            f"/api/v1/capsules/{cid}/export", params={"format": "prompt"}
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "text/plain; charset=utf-8"
