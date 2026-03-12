"""
CapsuleMemory REST API Server — FastAPI-based API with 16 endpoints.

Requires: pip install 'capsule-memory[server]'

Endpoints:
    - POST   /api/v1/sessions                     → Create session
    - POST   /api/v1/sessions/{id}/ingest          → Ingest turn
    - GET    /api/v1/sessions/{id}/snapshot         → Session snapshot
    - POST   /api/v1/sessions/{id}/seal             → Seal session
    - GET    /api/v1/sessions/{id}/triggers         → Pending triggers
    - POST   /api/v1/sessions/{id}/triggers/{eid}/confirm → Confirm trigger
    - GET    /api/v1/capsules                       → List capsules
    - GET    /api/v1/capsules/{id}                  → Get capsule
    - DELETE /api/v1/capsules/{id}                  → Delete capsule
    - GET    /api/v1/capsules/{id}/export            → Export capsule
    - GET    /api/v1/capsules/{id}/prompt-snippet     → Prompt snippet
    - POST   /api/v1/capsules/import                → Import capsule
    - POST   /api/v1/capsules/merge                 → Merge capsules
    - GET    /api/v1/capsules/pending-triggers       → Widget polling (Patch #4)
    - GET    /api/v1/recall                         → Recall memories
    - GET    /health                                → Health check
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    _SERVER_AVAILABLE = True
except ImportError:
    _SERVER_AVAILABLE = False

# ─── In-process session state ─────────────────────────────────────────────────
_active_sessions: dict[str, Any] = {}  # key=session_id → SessionTracker
_cm: Any = None  # CapsuleMemory instance


def _get_cm() -> Any:
    """Get the initialized CapsuleMemory instance."""
    if _cm is None:
        raise RuntimeError("CapsuleMemory not initialized. Call init_capsule_memory() first.")
    return _cm


def init_capsule_memory(
    storage_path: str = "~/.capsules",
    storage_type: str = "local",
) -> None:
    """Initialize the global CapsuleMemory instance for the REST server."""
    global _cm
    from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig

    config = CapsuleMemoryConfig.from_env()
    config.storage_path = storage_path
    config.storage_type = storage_type  # type: ignore[assignment]
    _cm = CapsuleMemory(
        config=config,
        on_skill_trigger=lambda evt: logger.info(
            "Skill trigger: %s (confidence=%.2f)",
            evt.skill_draft.suggested_name,
            evt.skill_draft.confidence,
        ),
    )


def _build_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="CapsuleMemory API",
        description="User-sovereign AI memory capsule system with skill extraction",
        version="0.1.0",
    )

    # CORS configuration — default blocks all cross-origin requests;
    # set CAPSULE_CORS_ORIGINS to a comma-separated whitelist in production.
    _cors_raw = os.getenv("CAPSULE_CORS_ORIGINS", "")
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Auth middleware ───────────────────────────────────────────────────

    async def verify_token(authorization: str | None = Header(default=None)) -> None:
        """API key verification. Requires CAPSULE_API_KEY to be set."""
        import hmac as _hmac
        api_key = os.getenv("CAPSULE_API_KEY", "")
        if not api_key:
            logger.warning("CAPSULE_API_KEY not set — all endpoints are unprotected")
            return
        token = (authorization.removeprefix("Bearer ").strip()) if authorization else ""
        if not _hmac.compare_digest(token, api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # ─── Helper: get or create session tracker ─────────────────────────────

    def _get_or_create_session(
        session_id: str, user_id: str = "default"
    ) -> Any:
        """Get an existing session or create a new one."""
        from capsule_memory.core.session import SessionConfig, SessionTracker
        from capsule_memory.notifier.callback import CallbackNotifier

        if session_id in _active_sessions:
            return _active_sessions[session_id]

        cm = _get_cm()
        config = SessionConfig(
            user_id=user_id,
            session_id=session_id,
            auto_seal_on_exit=False,
        )
        notifier = CallbackNotifier(
            lambda evt: logger.info("Trigger event: %s", evt.event_id)
        )
        tracker = SessionTracker(
            config=config,
            storage=cm._storage,
            extractor=cm._extractor,
            skill_detector=cm._skill_detector,
            notifier=notifier,
        )
        _active_sessions[session_id] = tracker
        return tracker

    # ─── Session endpoints ─────────────────────────────────────────────────

    @app.post(
        "/api/v1/sessions",
        summary="Create a new session",
        dependencies=[Depends(verify_token)],
    )
    async def create_session(
        user_id: str = "default",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new conversation session.

        Args:
            user_id: User identifier.
            session_id: Optional custom session ID.

        Returns:
            Dict with session_id and user_id.
        """
        resolved_id = session_id or f"sess_{uuid4().hex[:12]}"
        _get_or_create_session(resolved_id, user_id)
        return {"session_id": resolved_id, "user_id": user_id}

    @app.post(
        "/api/v1/sessions/{session_id}/ingest",
        summary="Ingest a conversation turn",
        dependencies=[Depends(verify_token)],
    )
    async def ingest_turn(
        session_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Ingest a user-assistant conversation turn into an active session.

        Args:
            session_id: The session to ingest into.
            body: Must contain user_message, assistant_response. Optional: user_id.

        Returns:
            Dict with turn_id, session_id, total_turns, pending_triggers.
        """
        user_id = body.get("user_id", "default")
        user_message = body.get("user_message")
        assistant_response = body.get("assistant_response")

        if not user_message or not assistant_response:
            raise HTTPException(
                status_code=400,
                detail="user_message and assistant_response are required",
            )

        tracker = _get_or_create_session(session_id, user_id)
        turn = await tracker.ingest(user_message, assistant_response)

        return {
            "turn_id": turn.turn_id,
            "session_id": session_id,
            "total_turns": len(tracker.state.turns),
            "pending_triggers": len(tracker.state.pending_triggers),
        }

    @app.get(
        "/api/v1/sessions/{session_id}/snapshot",
        summary="Get session snapshot",
        dependencies=[Depends(verify_token)],
    )
    async def get_snapshot(
        session_id: str,
        user_id: str = Query(default="default"),
    ) -> dict[str, Any]:
        """
        Get a snapshot of the current session state.

        Args:
            session_id: The session identifier.
            user_id: User identifier (for session lookup).

        Returns:
            Session state snapshot.
        """
        if session_id not in _active_sessions:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        tracker = _active_sessions[session_id]
        snapshot_result: dict[str, Any] = await tracker.snapshot()
        return snapshot_result

    @app.post(
        "/api/v1/sessions/{session_id}/seal",
        summary="Seal a session into a capsule",
        dependencies=[Depends(verify_token)],
    )
    async def seal_session(
        session_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Seal a session, creating a persistent capsule.

        Args:
            session_id: The session to seal.
            body: Optional fields: user_id, title, tags.

        Returns:
            Dict with capsule_id, title, turn_count, type.
        """
        if session_id not in _active_sessions:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        tracker = _active_sessions[session_id]
        capsule = await tracker.seal(
            title=body.get("title", ""),
            tags=body.get("tags", []),
        )
        del _active_sessions[session_id]

        return {
            "capsule_id": capsule.capsule_id,
            "title": capsule.metadata.title,
            "turn_count": capsule.metadata.turn_count,
            "type": capsule.capsule_type.value,
        }

    @app.get(
        "/api/v1/sessions/{session_id}/triggers",
        summary="Get pending skill triggers for a session",
        dependencies=[Depends(verify_token)],
    )
    async def get_session_triggers(
        session_id: str,
        user_id: str = Query(default="default"),
    ) -> dict[str, Any]:
        """
        Get pending skill trigger events for a session.

        Args:
            session_id: The session identifier.
            user_id: User identifier.

        Returns:
            Dict with pending trigger events list.
        """
        if session_id not in _active_sessions:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        tracker = _active_sessions[session_id]
        events = [
            {
                "event_id": e.event_id,
                "suggested_name": e.skill_draft.suggested_name,
                "confidence": e.skill_draft.confidence,
                "trigger_rule": e.trigger_rule.value,
            }
            for e in tracker.state.pending_triggers
            if not e.resolved
        ]
        return {"triggers": events, "count": len(events)}

    @app.post(
        "/api/v1/sessions/{session_id}/triggers/{event_id}/confirm",
        summary="Confirm or dismiss a skill trigger",
        dependencies=[Depends(verify_token)],
    )
    async def confirm_trigger(
        session_id: str,
        event_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Confirm or dismiss a skill trigger event.

        Args:
            session_id: The session identifier.
            event_id: The trigger event ID.
            body: Must contain resolution. Optional: user_id.

        Returns:
            Dict with resolved status and event_id.
        """
        if session_id not in _active_sessions:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        resolution = body.get("resolution")
        if resolution not in (
            "extract_skill",
            "merge_memory",
            "extract_hybrid",
            "ignore",
            "never",
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resolution: {resolution}. "
                f"Must be one of: extract_skill, merge_memory, extract_hybrid, ignore, never",
            )

        tracker = _active_sessions[session_id]
        try:
            await tracker.confirm_skill_trigger(event_id, resolution)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        return {"resolved": True, "event_id": event_id}

    # ─── Capsule CRUD endpoints ────────────────────────────────────────────

    @app.get(
        "/api/v1/capsules",
        summary="List capsules",
        dependencies=[Depends(verify_token)],
    )
    async def list_capsules(
        user_id: str = Query(default=None),
        type: str | None = Query(default=None),
        tags: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        """
        List capsules with optional filtering.

        Args:
            user_id: Filter by user ID.
            type: Filter by capsule type (memory, skill, hybrid, context).
            tags: Comma-separated tag list.
            limit: Max results per page.
            offset: Pagination offset.

        Returns:
            List of capsule summary dicts.
        """
        from capsule_memory.models.capsule import CapsuleType as CT

        cm = _get_cm()
        capsule_type = CT(type) if type else None
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        capsules = await cm.store.list(
            user_id=user_id,
            capsule_type=capsule_type,
            tags=tag_list,
            limit=limit,
            offset=offset,
        )

        return [
            {
                "capsule_id": c.capsule_id,
                "type": c.capsule_type.value,
                "title": c.metadata.title,
                "tags": c.metadata.tags,
                "sealed_at": (
                    c.lifecycle.sealed_at.isoformat() if c.lifecycle.sealed_at else None
                ),
                "turn_count": c.metadata.turn_count,
                "status": c.lifecycle.status.value,
            }
            for c in capsules
        ]

    @app.get(
        "/api/v1/capsules/pending-triggers",
        summary="Get pending trigger events for Widget polling (Patch #4)",
        dependencies=[Depends(verify_token)],
    )
    async def get_pending_triggers(user_id: str = Query(default="default")) -> dict[str, Any]:
        """
        Widget polling endpoint. Returns all unresolved skill trigger events
        across active sessions.

        This endpoint reads from the in-process _active_sessions dict.
        Server restart clears all pending events (expected behavior).

        Args:
            user_id: User ID for filtering (currently returns all sessions'
                     events; Widget-side filtering by user_id recommended).

        Returns:
            Dict with triggers list and count.
        """
        pending: list[dict[str, Any]] = []
        for session_id, tracker in list(_active_sessions.items()):
            for event in tracker.state.pending_triggers:
                if not event.resolved:
                    try:
                        pending.append(
                            {
                                "event_id": event.event_id,
                                "session_id": session_id,
                                "trigger_rule": event.trigger_rule.value,
                                "skill_draft": {
                                    "suggested_name": event.skill_draft.suggested_name,
                                    "confidence": event.skill_draft.confidence,
                                    "preview": event.skill_draft.preview,
                                    "trigger_rule": event.skill_draft.trigger_rule.value,
                                },
                            }
                        )
                    except AttributeError:
                        continue  # Skip malformed events

        return {"triggers": pending, "count": len(pending)}

    @app.get(
        "/api/v1/capsules/{capsule_id}",
        summary="Get capsule details",
        dependencies=[Depends(verify_token)],
    )
    async def get_capsule(capsule_id: str) -> dict[str, Any]:
        """
        Get full capsule details by ID.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            Full capsule data as dict.

        Raises:
            HTTPException 404: If capsule not found.
        """
        from capsule_memory.exceptions import CapsuleNotFoundError

        cm = _get_cm()
        try:
            capsule = await cm.store.get(capsule_id)
        except CapsuleNotFoundError:
            raise HTTPException(status_code=404, detail=f"Capsule {capsule_id} not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Storage error: {e}")

        result: dict[str, Any] = json.loads(capsule.to_json())
        return result

    @app.delete(
        "/api/v1/capsules/{capsule_id}",
        summary="Delete a capsule",
        dependencies=[Depends(verify_token)],
    )
    async def delete_capsule(capsule_id: str) -> dict[str, Any]:
        """
        Delete a capsule by ID.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            Dict with deleted status and capsule_id.
        """
        cm = _get_cm()
        deleted = await cm.store.delete(capsule_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Capsule {capsule_id} not found")
        return {"deleted": True, "capsule_id": capsule_id}

    @app.get(
        "/api/v1/capsules/{capsule_id}/export",
        summary="Export capsule as file download",
        dependencies=[Depends(verify_token)],
    )
    async def export_capsule(
        capsule_id: str,
        format: str = Query(default="json"),
        encrypt: bool = Query(default=False),
        passphrase: str = Query(default=""),
    ) -> StreamingResponse:
        """
        Export a capsule as a file download (StreamingResponse).

        Args:
            capsule_id: The capsule's unique identifier.
            format: Export format (json, msgpack, universal, prompt).
            encrypt: Whether to encrypt.
            passphrase: Encryption passphrase.

        Returns:
            StreamingResponse with file attachment.
        """
        cm = _get_cm()
        ext_map = {"json": ".json", "msgpack": ".capsule", "universal": ".json", "prompt": ".txt"}
        ext = ext_map.get(format, ".json")
        media_map = {
            "json": "application/json",
            "msgpack": "application/octet-stream",
            "universal": "application/json",
            "prompt": "text/plain",
        }
        media_type = media_map.get(format, "application/octet-stream")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, f"{capsule_id}{ext}")
            try:
                await cm.export_capsule(
                    capsule_id, output_path, format=format,
                    encrypt=encrypt, passphrase=passphrase,
                )
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            content = Path(output_path).read_bytes()

        filename = f"{capsule_id}{ext}"
        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.get(
        "/api/v1/capsules/{capsule_id}/prompt-snippet",
        summary="Get capsule as a prompt snippet",
        dependencies=[Depends(verify_token)],
    )
    async def get_prompt_snippet(capsule_id: str) -> dict[str, Any]:
        """
        Get a capsule's content as a plain-text prompt snippet.

        Args:
            capsule_id: The capsule's unique identifier.

        Returns:
            Dict with text field containing the prompt snippet.
        """
        from capsule_memory.exceptions import CapsuleNotFoundError

        cm = _get_cm()
        try:
            capsule = await cm.store.get(capsule_id)
        except CapsuleNotFoundError:
            raise HTTPException(status_code=404, detail=f"Capsule {capsule_id} not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Storage error: {e}")

        return {"text": capsule.to_prompt_snippet()}

    @app.post(
        "/api/v1/capsules/import",
        summary="Import a capsule from file upload",
        dependencies=[Depends(verify_token)],
    )
    async def import_capsule(
        file: UploadFile = File(...),
        user_id: str = Form(default="default"),
        passphrase: str = Form(default=""),
    ) -> dict[str, Any]:
        """
        Import a capsule from an uploaded file.

        Supports .json, .capsule (msgpack), and .txt formats.
        Auto-detects format from file extension and content.

        Args:
            file: The uploaded file.
            user_id: Target user ID for the imported capsule.
            passphrase: Decryption passphrase (if encrypted).

        Returns:
            Dict with capsule_id, type, and title.
        """
        cm = _get_cm()
        suffix = Path(file.filename or "upload.json").suffix or ".json"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        try:
            capsule = await cm.import_capsule(tmp_path, user_id, passphrase)
            return {
                "capsule_id": capsule.capsule_id,
                "type": capsule.capsule_type.value,
                "title": capsule.metadata.title,
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @app.post(
        "/api/v1/capsules/merge",
        summary="Merge multiple capsules",
        dependencies=[Depends(verify_token)],
    )
    async def merge_capsules(body: dict[str, Any]) -> dict[str, Any]:
        """
        Merge multiple capsules into a new one.

        Args:
            body: Must contain capsule_ids. Optional: title, tags, user_id.

        Returns:
            Dict with merged capsule details.
        """
        cm = _get_cm()
        capsule_ids = body.get("capsule_ids", [])
        if len(capsule_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 capsule_ids are required for merge",
            )

        try:
            merged = await cm.store.merge(
                capsule_ids=capsule_ids,
                title=body.get("title", ""),
                tags=body.get("tags"),
                user_id=body.get("user_id"),
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "capsule_id": merged.capsule_id,
            "type": merged.capsule_type.value,
            "title": merged.metadata.title,
            "turn_count": merged.metadata.turn_count,
        }

    # ─── Recall endpoint ───────────────────────────────────────────────────

    @app.get(
        "/api/v1/recall",
        summary="Recall relevant memories",
        dependencies=[Depends(verify_token)],
    )
    async def recall_memories(
        q: str = Query(..., description="Search query"),
        user_id: str = Query(default="default"),
        top_k: int = Query(default=3, ge=1, le=10),
    ) -> dict[str, Any]:
        """
        Recall relevant memories matching the query.

        Args:
            q: Search query text.
            user_id: User identifier.
            top_k: Maximum number of capsules to recall.

        Returns:
            Full recall structure with facts, skills, summary, prompt_injection, sources.
        """
        cm = _get_cm()
        recall_result: dict[str, Any] = await cm.recall(q, user_id=user_id, top_k=top_k)
        return recall_result

    # ─── Health check ──────────────────────────────────────────────────────

    @app.get("/health", summary="Health check")
    async def health_check() -> dict[str, Any]:
        """
        Health check endpoint.

        Returns:
            Dict with status and version.
        """
        return {"status": "ok", "version": "0.1.0"}

    return app


# Module-level app instance (lazy-built on first import)
app: Any = None


def _ensure_app() -> Any:
    """Ensure the FastAPI app is built."""
    global app
    if app is None:
        if not _SERVER_AVAILABLE:
            raise RuntimeError(
                "REST API Server requires capsule-memory[server] extras: "
                "pip install 'capsule-memory[server]'"
            )
        app = _build_app()
    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    storage_path: str = "~/.capsules",
    storage_type: str = "local",
) -> None:
    """
    REST API Server entry point.

    Args:
        host: Bind host address.
        port: Bind port number.
        storage_path: Path to capsule storage directory.
        storage_type: Storage backend type (local, sqlite, redis, qdrant).

    Raises:
        RuntimeError: If capsule-memory[server] extras are not installed.
    """
    if not _SERVER_AVAILABLE:
        logger.error(
            "REST API Server requires capsule-memory[server] extras: "
            "pip install 'capsule-memory[server]'"
        )
        return

    import uvicorn

    init_capsule_memory(storage_path=storage_path, storage_type=storage_type)
    application = _ensure_app()
    uvicorn.run(application, host=host, port=port)
