"""
CapsuleMemory MCP Server — provides 10 tools for Claude Code / Claude Desktop integration.

Requires: pip install 'capsule-memory[mcp]'

Session state: maintained in-process via _active_sessions dict (key=user_id).
Server restart clears active sessions; sealed capsules persist in storage.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_active_sessions: dict[str, Any] = {}
_cm: Any = None
_pending_trigger_events: dict[str, Any] = {}


def get_cm() -> Any:
    if _cm is None:
        raise RuntimeError("CapsuleMemory not initialized. Call init_capsule_memory() first.")
    return _cm


try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


def init_capsule_memory(storage_path: str = "~/.capsules", storage_type: str = "local") -> None:
    global _cm
    from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig
    config = CapsuleMemoryConfig(storage_path=storage_path, storage_type=storage_type)  # type: ignore[arg-type]
    _cm = CapsuleMemory(
        config=config,
        on_skill_trigger=lambda evt: _pending_trigger_events.update({evt.event_id: evt}),
    )


def _get_or_create_session(user_id: str, session_id: str | None = None) -> Any:
    from capsule_memory.core.session import SessionConfig, SessionTracker
    from capsule_memory.notifier.callback import CallbackNotifier

    if user_id not in _active_sessions or not _active_sessions[user_id].state.is_active:
        cm = get_cm()
        from uuid import uuid4
        config = SessionConfig(
            user_id=user_id,
            session_id=session_id or f"sess_{uuid4().hex[:12]}",
            auto_seal_on_exit=False,
        )
        notifier = CallbackNotifier(
            lambda evt: _pending_trigger_events.update({evt.event_id: evt})
        )
        tracker = SessionTracker(
            config=config,
            storage=cm._storage,
            extractor=cm._extractor,
            skill_detector=cm._skill_detector,
            notifier=notifier,
        )
        _active_sessions[user_id] = tracker
    return _active_sessions[user_id]


def _build_server() -> "Server":
    server = Server("capsule-memory")

    @server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="capsule_ingest",
                description="Ingest a conversation turn into the current memory session.",
                inputSchema={"type": "object", "required": ["user_message", "assistant_response"],
                             "properties": {
                                 "user_message": {"type": "string", "description": "User message"},
                                 "assistant_response": {"type": "string", "description": "AI response"},
                                 "user_id": {"type": "string", "default": "default", "description": "User ID"},
                                 "session_id": {"type": "string", "description": "Session ID (optional)"},
                             }},
            ),
            types.Tool(
                name="capsule_seal",
                description="Seal the current session into a capsule for persistent storage.",
                inputSchema={"type": "object", "properties": {
                    "user_id": {"type": "string", "default": "default"},
                    "title": {"type": "string", "description": "Capsule title (optional)"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tag list (optional)"},
                }},
            ),
            types.Tool(
                name="capsule_recall",
                description="Recall relevant memories from history, returning context injectable into system prompts.",
                inputSchema={"type": "object", "required": ["query"],
                             "properties": {
                                 "query": {"type": "string", "description": "Topic or question"},
                                 "user_id": {"type": "string", "default": "default"},
                                 "top_k": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
                                 "include_skills": {"type": "boolean", "default": True},
                             }},
            ),
            types.Tool(
                name="capsule_inject_context",
                description="Recall memory and return plain text block for direct system prompt injection.",
                inputSchema={"type": "object", "required": ["query"],
                             "properties": {
                                 "query": {"type": "string"},
                                 "user_id": {"type": "string", "default": "default"},
                             }},
            ),
            types.Tool(
                name="capsule_list",
                description="List user's historical capsules.",
                inputSchema={"type": "object", "properties": {
                    "user_id": {"type": "string", "default": "default"},
                    "capsule_type": {"type": "string", "enum": ["memory", "skill", "hybrid", "context"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                }},
            ),
            types.Tool(
                name="capsule_export",
                description="Export a capsule to a specified format.",
                inputSchema={"type": "object", "required": ["capsule_id"],
                             "properties": {
                                 "capsule_id": {"type": "string"},
                                 "format": {"type": "string", "enum": ["json", "msgpack", "universal", "prompt"],
                                            "default": "universal"},
                                 "output_path": {"type": "string",
                                                 "description": "Output file path (optional)"},
                                 "encrypt": {"type": "boolean", "default": False},
                                 "passphrase": {"type": "string", "default": ""},
                             }},
            ),
            types.Tool(
                name="capsule_import",
                description="Import a capsule from file (.json, .capsule, universal format).",
                inputSchema={"type": "object", "required": ["file_path"],
                             "properties": {
                                 "file_path": {"type": "string"},
                                 "user_id": {"type": "string", "default": "default"},
                                 "passphrase": {"type": "string", "default": ""},
                             }},
            ),
            types.Tool(
                name="capsule_pending_triggers",
                description="View pending skill trigger events awaiting user confirmation.",
                inputSchema={"type": "object", "properties": {
                    "user_id": {"type": "string", "default": "default"},
                }},
            ),
            types.Tool(
                name="capsule_confirm_trigger",
                description="Confirm or dismiss a skill trigger event.",
                inputSchema={"type": "object", "required": ["event_id", "resolution"],
                             "properties": {
                                 "event_id": {"type": "string"},
                                 "resolution": {"type": "string",
                                                "enum": ["extract_skill", "merge_memory",
                                                         "extract_hybrid", "ignore", "never"]},
                                 "user_id": {"type": "string", "default": "default"},
                             }},
            ),
            types.Tool(
                name="capsule_extract_skill",
                description="Create a skill capsule from a natural language description (manual extraction).",
                inputSchema={"type": "object", "required": ["skill_description"],
                             "properties": {
                                 "skill_description": {"type": "string",
                                                       "description": "Skill description including purpose, trigger, and method"},
                                 "skill_name": {"type": "string", "description": "Skill name (optional)"},
                                 "tags": {"type": "array", "items": {"type": "string"}},
                                 "user_id": {"type": "string", "default": "default"},
                             }},
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        from capsule_memory.exceptions import CapsuleNotFoundError
        cm = get_cm()
        user_id = arguments.get("user_id", "default")

        try:
            if name == "capsule_ingest":
                tracker = _get_or_create_session(user_id, arguments.get("session_id"))
                turn = await tracker.ingest(
                    arguments["user_message"], arguments["assistant_response"]
                )
                return [types.TextContent(type="text", text=json.dumps({
                    "turn_id": turn.turn_id,
                    "session_id": tracker.config.session_id,
                    "total_turns": len(tracker.state.turns),
                    "pending_triggers": len(tracker.state.pending_triggers),
                }))]

            elif name == "capsule_seal":
                if user_id not in _active_sessions:
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": f"No active session for user {user_id}. Call capsule_ingest first.",
                    }))]
                tracker = _active_sessions[user_id]
                capsule = await tracker.seal(
                    title=arguments.get("title", ""),
                    tags=arguments.get("tags", []),
                )
                del _active_sessions[user_id]
                return [types.TextContent(type="text", text=json.dumps({
                    "capsule_id": capsule.capsule_id,
                    "title": capsule.metadata.title,
                    "turn_count": capsule.metadata.turn_count,
                    "type": capsule.capsule_type.value,
                }))]

            elif name == "capsule_recall":
                result = await cm.recall(
                    arguments["query"], user_id, arguments.get("top_k", 3)
                )
                if not arguments.get("include_skills", True):
                    result["skills"] = []
                return [types.TextContent(
                    type="text", text=json.dumps(result, ensure_ascii=False)
                )]

            elif name == "capsule_inject_context":
                result = await cm.recall(arguments["query"], user_id, top_k=3)
                return [types.TextContent(type="text", text=result["prompt_injection"])]

            elif name == "capsule_list":
                from capsule_memory.models.capsule import CapsuleType as CT
                ct = CT(arguments["capsule_type"]) if arguments.get("capsule_type") else None
                capsules = await cm.store.list(
                    user_id=user_id, capsule_type=ct,
                    tags=arguments.get("tags"),
                    limit=arguments.get("limit", 20),
                )
                return [types.TextContent(type="text", text=json.dumps([{
                    "capsule_id": c.capsule_id,
                    "type": c.capsule_type.value,
                    "title": c.metadata.title,
                    "tags": c.metadata.tags,
                    "sealed_at": (
                        c.lifecycle.sealed_at.isoformat() if c.lifecycle.sealed_at else None
                    ),
                    "turn_count": c.metadata.turn_count,
                } for c in capsules], ensure_ascii=False))]

            elif name == "capsule_export":
                capsule_id = arguments["capsule_id"]
                fmt = arguments.get("format", "universal")
                output_path = arguments.get("output_path") or str(
                    Path(cm._config.storage_path).expanduser() / "exports" / f"{capsule_id}.{fmt}"
                )
                out = await cm.export_capsule(
                    capsule_id, output_path,
                    format=fmt,
                    encrypt=arguments.get("encrypt", False),
                    passphrase=arguments.get("passphrase", ""),
                )
                return [types.TextContent(type="text", text=json.dumps({
                    "path": str(out),
                    "format": fmt,
                    "size_bytes": out.stat().st_size,
                }))]

            elif name == "capsule_import":
                capsule = await cm.import_capsule(
                    arguments["file_path"], user_id, arguments.get("passphrase", "")
                )
                return [types.TextContent(type="text", text=json.dumps({
                    "capsule_id": capsule.capsule_id,
                    "type": capsule.capsule_type.value,
                    "title": capsule.metadata.title,
                }))]

            elif name == "capsule_pending_triggers":
                events = []
                if user_id in _active_sessions:
                    events = [
                        {
                            "event_id": e.event_id,
                            "suggested_name": e.skill_draft.suggested_name,
                            "confidence": e.skill_draft.confidence,
                            "trigger_rule": e.trigger_rule.value,
                        }
                        for e in _active_sessions[user_id].state.pending_triggers
                        if not e.resolved
                    ]
                return [types.TextContent(
                    type="text", text=json.dumps({"pending": events})
                )]

            elif name == "capsule_confirm_trigger":
                event_id = arguments["event_id"]
                if user_id not in _active_sessions:
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": "No active session",
                    }))]
                await _active_sessions[user_id].confirm_skill_trigger(
                    event_id, arguments["resolution"]
                )
                return [types.TextContent(type="text", text=json.dumps({
                    "resolved": True, "event_id": event_id,
                }))]

            elif name == "capsule_extract_skill":
                from capsule_memory.models.skill import SkillPayload
                from capsule_memory.core.builder import CapsuleBuilder
                from capsule_memory.core.session import SessionConfig
                skill_name = arguments.get("skill_name") or re.sub(
                    r"\s+", " ", arguments["skill_description"][:50]
                ).strip()
                skill_payload = SkillPayload(
                    skill_name=skill_name,
                    trigger_pattern=arguments["skill_description"],
                    description=arguments["skill_description"],
                    instructions=arguments["skill_description"],
                )
                config = SessionConfig(user_id=user_id, session_id="manual_extract")
                capsule = CapsuleBuilder.build_skill(
                    config, skill_payload, tags=arguments.get("tags", [])
                )
                await cm.store.save(capsule)
                return [types.TextContent(type="text", text=json.dumps({
                    "skill_capsule_id": capsule.capsule_id,
                    "skill_name": skill_name,
                }))]

            else:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Unknown tool: {name}",
                }))]

        except CapsuleNotFoundError as e:
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]
        except Exception as e:
            logger.exception("Tool %s failed: %s", name, e)
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


def main() -> None:
    """MCP Server entry point."""
    if not _MCP_AVAILABLE:
        logger.error("MCP Server requires capsule-memory[mcp] extras: pip install 'capsule-memory[mcp]'")
        return

    parser = argparse.ArgumentParser(description="CapsuleMemory MCP Server")
    parser.add_argument("--storage", default=os.getenv("CAPSULE_STORAGE_PATH", "~/.capsules"))
    parser.add_argument("--storage-type", default=os.getenv("CAPSULE_STORAGE_TYPE", "local"))
    parser.add_argument("--log-level", default=os.getenv("CAPSULE_LOG_LEVEL", "INFO"))
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    init_capsule_memory(storage_path=args.storage, storage_type=args.storage_type)

    server = _build_server()
    asyncio.run(stdio_server(server))  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
