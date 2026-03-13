"""Integration tests for the REST API Server (T2.2), includes Patch #4 verification."""
from __future__ import annotations

import os

import pytest

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"


@pytest.fixture(autouse=True)
def mock_extractor_mode():
    os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"
    yield
    os.environ.pop("CAPSULE_MOCK_EXTRACTOR", None)


@pytest.fixture
def client(tmp_path):
    """Create a test client with a temporary storage directory."""
    from capsule_memory.server import rest_api

    rest_api.init_capsule_memory(storage_path=str(tmp_path), storage_type="local")
    app = rest_api._build_app()
    rest_api.app = app
    # Clear sessions between tests
    rest_api._active_sessions.clear()
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        # Wrap TestClient in a way that tests can use it
        yield tc


def test_health_check(client) -> None:
    """Health endpoint returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    from capsule_memory import __version__
    assert data["version"] == __version__


def test_create_session(client) -> None:
    """Creating a session returns session_id."""
    resp = client.post("/api/v1/sessions", params={"user_id": "test_user"})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["user_id"] == "test_user"


def test_ingest_and_snapshot(client) -> None:
    """Ingest turns and get a snapshot."""
    # Create session
    resp = client.post(
        "/api/v1/sessions",
        params={"user_id": "test_user", "session_id": "test_sess_1"},
    )
    assert resp.status_code == 200

    # Ingest a turn
    resp = client.post(
        "/api/v1/sessions/test_sess_1/ingest",
        json={
            "user_message": "Hello",
            "assistant_response": "Hi there!",
            "user_id": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["turn_id"] == 1
    assert data["total_turns"] == 2  # user + assistant

    # Get snapshot
    resp = client.get(
        "/api/v1/sessions/test_sess_1/snapshot",
        params={"user_id": "test_user"},
    )
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["turn_count"] == 2
    assert snap["is_active"] is True


def test_seal_session(client) -> None:
    """Seal a session and verify capsule is created."""
    # Create and ingest
    client.post(
        "/api/v1/sessions",
        params={"user_id": "test_user", "session_id": "seal_test"},
    )
    client.post(
        "/api/v1/sessions/seal_test/ingest",
        json={
            "user_message": "Hello",
            "assistant_response": "Hi!",
            "user_id": "test_user",
        },
    )

    # Seal
    resp = client.post(
        "/api/v1/sessions/seal_test/seal",
        json={"user_id": "test_user", "title": "Test Seal", "tags": ["test"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "capsule_id" in data
    assert data["title"] == "Test Seal"

    # Verify capsule exists in storage
    resp = client.get("/api/v1/capsules", params={"user_id": "test_user"})
    assert resp.status_code == 200
    capsules = resp.json()
    assert len(capsules) >= 1


def test_list_capsules(client) -> None:
    """List capsules after creating some."""
    # Create and seal a session
    client.post(
        "/api/v1/sessions",
        params={"user_id": "list_user", "session_id": "list_test"},
    )
    client.post(
        "/api/v1/sessions/list_test/ingest",
        json={
            "user_message": "Test",
            "assistant_response": "Response",
            "user_id": "list_user",
        },
    )
    client.post(
        "/api/v1/sessions/list_test/seal",
        json={"user_id": "list_user", "title": "List Test"},
    )

    resp = client.get("/api/v1/capsules", params={"user_id": "list_user"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "capsule_id" in data[0]
    assert "type" in data[0]


def test_get_capsule_detail(client) -> None:
    """Get full capsule details."""
    # Create and seal
    client.post(
        "/api/v1/sessions",
        params={"user_id": "detail_user", "session_id": "detail_test"},
    )
    client.post(
        "/api/v1/sessions/detail_test/ingest",
        json={
            "user_message": "Detail test",
            "assistant_response": "Response",
            "user_id": "detail_user",
        },
    )
    seal_resp = client.post(
        "/api/v1/sessions/detail_test/seal",
        json={"user_id": "detail_user", "title": "Detail Test"},
    )
    capsule_id = seal_resp.json()["capsule_id"]

    resp = client.get(f"/api/v1/capsules/{capsule_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capsule_id"] == capsule_id


def test_delete_capsule(client) -> None:
    """Delete a capsule."""
    # Create and seal
    client.post(
        "/api/v1/sessions",
        params={"user_id": "del_user", "session_id": "del_test"},
    )
    client.post(
        "/api/v1/sessions/del_test/ingest",
        json={
            "user_message": "Delete test",
            "assistant_response": "Response",
            "user_id": "del_user",
        },
    )
    seal_resp = client.post(
        "/api/v1/sessions/del_test/seal",
        json={"user_id": "del_user"},
    )
    capsule_id = seal_resp.json()["capsule_id"]

    resp = client.delete(f"/api/v1/capsules/{capsule_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify deletion
    resp = client.get(f"/api/v1/capsules/{capsule_id}")
    assert resp.status_code == 404


def test_export_capsule(client) -> None:
    """Export a capsule as JSON download."""
    # Create and seal
    client.post(
        "/api/v1/sessions",
        params={"user_id": "export_user", "session_id": "export_test"},
    )
    client.post(
        "/api/v1/sessions/export_test/ingest",
        json={
            "user_message": "Export test",
            "assistant_response": "Response",
            "user_id": "export_user",
        },
    )
    seal_resp = client.post(
        "/api/v1/sessions/export_test/seal",
        json={"user_id": "export_user"},
    )
    capsule_id = seal_resp.json()["capsule_id"]

    resp = client.get(
        f"/api/v1/capsules/{capsule_id}/export",
        params={"format": "json"},
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_prompt_snippet(client) -> None:
    """Get capsule as prompt snippet."""
    # Create and seal
    client.post(
        "/api/v1/sessions",
        params={"user_id": "snippet_user", "session_id": "snippet_test"},
    )
    client.post(
        "/api/v1/sessions/snippet_test/ingest",
        json={
            "user_message": "Snippet test",
            "assistant_response": "Response",
            "user_id": "snippet_user",
        },
    )
    seal_resp = client.post(
        "/api/v1/sessions/snippet_test/seal",
        json={"user_id": "snippet_user"},
    )
    capsule_id = seal_resp.json()["capsule_id"]

    resp = client.get(f"/api/v1/capsules/{capsule_id}/prompt-snippet")
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert len(data["text"]) > 0


def test_import_capsule(client, tmp_path) -> None:
    """Import a capsule from file upload."""
    import json

    # Create a universal format file
    universal = {
        "schema": "universal-memory/1.0",
        "capsule_id": "test_import",
        "title": "Imported Test",
        "summary": "Test summary",
        "facts": [{"key": "lang", "value": "Python"}],
        "skills": [],
        "tags": ["imported"],
        "prompt_injection": "test",
        "created_at": "2025-01-01T00:00:00",
        "origin": "test",
    }
    import_file = tmp_path / "import_test.json"
    import_file.write_text(json.dumps(universal), encoding="utf-8")

    with open(import_file, "rb") as f:
        resp = client.post(
            "/api/v1/capsules/import",
            files={"file": ("import_test.json", f, "application/json")},
            data={"user_id": "import_user"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "capsule_id" in data


def test_merge_capsules(client) -> None:
    """Merge two capsules."""
    # Create and seal two sessions
    for i in range(2):
        sid = f"merge_test_{i}"
        client.post(
            "/api/v1/sessions",
            params={"user_id": "merge_user", "session_id": sid},
        )
        client.post(
            f"/api/v1/sessions/{sid}/ingest",
            json={
                "user_message": f"Merge test {i}",
                "assistant_response": f"Response {i}",
                "user_id": "merge_user",
            },
        )
        client.post(
            f"/api/v1/sessions/{sid}/seal",
            json={"user_id": "merge_user", "title": f"Merge Test {i}"},
        )

    # Get capsule IDs
    resp = client.get("/api/v1/capsules", params={"user_id": "merge_user"})
    capsule_ids = [c["capsule_id"] for c in resp.json()]
    assert len(capsule_ids) >= 2

    # Merge
    resp = client.post(
        "/api/v1/capsules/merge",
        json={
            "capsule_ids": capsule_ids[:2],
            "title": "Merged Result",
            "user_id": "merge_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "capsule_id" in data
    assert data["title"] == "Merged Result"


def test_recall(client) -> None:
    """Recall memories."""
    # Create and seal
    client.post(
        "/api/v1/sessions",
        params={"user_id": "recall_user", "session_id": "recall_test"},
    )
    client.post(
        "/api/v1/sessions/recall_test/ingest",
        json={
            "user_message": "Python Django optimization",
            "assistant_response": "Use select_related and prefetch_related",
            "user_id": "recall_user",
        },
    )
    client.post(
        "/api/v1/sessions/recall_test/seal",
        json={"user_id": "recall_user", "title": "Django Optimization"},
    )

    resp = client.get(
        "/api/v1/recall",
        params={"q": "Django", "user_id": "recall_user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "prompt_injection" in data
    assert "facts" in data
    assert "sources" in data


def test_ingest_missing_fields(client) -> None:
    """Ingest with missing fields returns 400."""
    client.post(
        "/api/v1/sessions",
        params={"user_id": "test_user", "session_id": "err_test"},
    )
    resp = client.post(
        "/api/v1/sessions/err_test/ingest",
        json={"user_message": "Hello"},  # missing assistant_response
    )
    assert resp.status_code == 400


def test_snapshot_nonexistent_session(client) -> None:
    """Snapshot on a nonexistent session returns 404."""
    resp = client.get(
        "/api/v1/sessions/nonexistent/snapshot",
        params={"user_id": "test_user"},
    )
    assert resp.status_code == 404


def test_pending_triggers_returns_empty_without_active_sessions(client) -> None:
    """
    Patch #4 verification: pending-triggers endpoint returns empty list
    when no active sessions exist. This ensures Widget polling doesn't fail.
    """
    resp = client.get(
        "/api/v1/capsules/pending-triggers",
        params={"user_id": "test_user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "triggers" in data
    assert data["triggers"] == []
    assert data["count"] == 0


def test_delete_nonexistent_capsule(client) -> None:
    """Deleting a nonexistent capsule returns 404."""
    resp = client.delete("/api/v1/capsules/nonexistent_id")
    assert resp.status_code == 404


def test_merge_with_less_than_two(client) -> None:
    """Merge with less than 2 capsules returns 400."""
    resp = client.post(
        "/api/v1/capsules/merge",
        json={"capsule_ids": ["one_id"]},
    )
    assert resp.status_code == 400
