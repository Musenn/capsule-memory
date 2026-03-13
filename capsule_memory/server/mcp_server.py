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
    config = CapsuleMemoryConfig.from_env()
    config.storage_path = storage_path
    config.storage_type = storage_type  # type: ignore[assignment]
    _cm = CapsuleMemory(
        config=config,
        on_skill_trigger=lambda evt: _pending_trigger_events.update({evt.event_id: evt}),
    )


def _get_or_create_session(user_id: str, session_id: str | None = None) -> Any:
    from capsule_memory.core.memory_compressor import MemoryCompressor
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
        from capsule_memory.core.memory_compressor import CompressorConfig
        compressor = (
            MemoryCompressor(
                model=cm._config.llm_model,
                config=CompressorConfig(
                    compress_threshold=cm._config.compress_threshold,
                    max_layer_tokens=cm._config.compress_layer_max,
                ),
            )
            if cm._config.llm_model else None
        )
        tracker = SessionTracker(
            config=config,
            storage=cm._storage,
            extractor=cm._extractor,
            skill_detector=cm._skill_detector,
            notifier=notifier,
            skill_refiner=cm._skill_refiner,
            compressor=compressor,
        )
        _active_sessions[user_id] = tracker
    return _active_sessions[user_id]


_SERVER_INSTRUCTIONS = """\
You have access to CapsuleMemory — a persistent memory system across conversations.

## Automatic behavior (follow without being asked):

1. **First message**: Call `capsule_ingest` with the user's message and your response. \
The result may include `recalled_context` with relevant history — use it to inform your replies.

2. **During conversation**: Call `capsule_ingest` after exchanges containing user preferences, \
technical decisions, project knowledge, or problem solutions. Skip trivial exchanges.

3. **End of conversation**: Call `capsule_seal` with a descriptive title, tags, and extracted \
`facts` + `summary`. Always provide facts/summary directly for highest quality memories.

## Do NOT memorize:
- When the user says "don't remember this" or "off the record"
- Temporary debugging with no lasting value
- Content the user is quoting from elsewhere
"""


def _build_server() -> "Server":
    server = Server("capsule-memory", instructions=_SERVER_INSTRUCTIONS)

    # ─── MCP Prompts (passive memory injection) ───────────────────────────

    @server.list_prompts()  # type: ignore[untyped-decorator, no-untyped-call, unused-ignore]
    async def list_prompts() -> list[types.Prompt]:
        return [
            types.Prompt(
                name="memory-context",
                description=(
                    "Recall relevant memories for a topic and return them as "
                    "context. Use this at conversation start to inject historical "
                    "context automatically."
                ),
                arguments=[
                    types.PromptArgument(
                        name="topic",
                        description="Topic or question to recall context for",
                        required=True,
                    ),
                    types.PromptArgument(
                        name="user_id",
                        description="User ID (default: 'default')",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()  # type: ignore[untyped-decorator, no-untyped-call, unused-ignore]
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
        if name != "memory-context":
            raise ValueError(f"Unknown prompt: {name}")
        args = arguments or {}
        topic = args.get("topic", "")
        user_id = args.get("user_id", "default")
        cm = get_cm()
        result = await cm.recall(topic, user_id=user_id, top_k=3)
        context_text = result.get("prompt_injection", "")
        if not context_text or not result.get("facts"):
            context_text = "(No relevant memories found for this topic.)"
        return types.GetPromptResult(
            description=f"Memory context for: {topic}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            "The following is historical context from previous "
                            "conversations. Use it to provide more personalized "
                            "and informed responses:\n\n" + context_text
                        ),
                    ),
                ),
            ],
        )

    # ─── Tools ────────────────────────────────────────────────────────────

    @server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call, unused-ignore]
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
                description=(
                    "Seal the current session into a persistent memory capsule. "
                    "You can provide extracted facts and summary directly — this "
                    "produces higher quality memories than server-side extraction "
                    "and requires no LLM configuration. Extract key facts from the "
                    "conversation and pass them in the 'facts' and 'summary' fields."
                ),
                inputSchema={"type": "object", "properties": {
                    "user_id": {"type": "string", "default": "default"},
                    "title": {"type": "string", "description": "Capsule title"},
                    "tags": {"type": "array", "items": {"type": "string"},
                             "description": "Tag list"},
                    "summary": {"type": "string",
                                "description": "A concise summary of the conversation "
                                "(100-300 words). Focus on key decisions, topics, and context."},
                    "facts": {"type": "array",
                              "description": "Extracted facts worth remembering long-term.",
                              "items": {"type": "object", "properties": {
                                  "key": {"type": "string",
                                          "description": "Fact key in category.name format, "
                                          "e.g. 'technical_preference.python_formatter'"},
                                  "value": {"type": "string",
                                            "description": "The specific fact value"},
                                  "category": {"type": "string",
                                               "enum": ["technical_preference", "project_info",
                                                        "user_preference", "decision",
                                                        "constraint", "other"]},
                              }, "required": ["key", "value"]}},
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

    @server.call_tool()  # type: ignore[untyped-decorator, no-untyped-call, unused-ignore]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        from capsule_memory.exceptions import CapsuleNotFoundError
        cm = get_cm()
        user_id = arguments.get("user_id", "default")

        try:
            if name == "capsule_ingest":
                tracker = _get_or_create_session(user_id, arguments.get("session_id"))
                is_new_session = len(tracker.state.turns) == 0
                turn = await tracker.ingest(
                    arguments["user_message"], arguments["assistant_response"]
                )
                result: dict[str, Any] = {
                    "turn_id": turn.turn_id,
                    "session_id": tracker.config.session_id,
                    "total_turns": len(tracker.state.turns),
                    "pending_triggers": len(tracker.state.pending_triggers),
                }

                # Auto-recall on first turn of a new session
                if is_new_session:
                    try:
                        recall_result = await cm.recall(
                            arguments["user_message"], user_id=user_id, top_k=3
                        )
                        recalled_facts = recall_result.get("facts", [])
                        if recalled_facts:
                            result["recalled_context"] = recall_result.get(
                                "prompt_injection", ""
                            )
                            result["recalled_facts_count"] = len(recalled_facts)
                    except Exception as recall_err:
                        logger.debug("Auto-recall on first ingest failed: %s", recall_err)

                return [types.TextContent(type="text", text=json.dumps(result))]

            elif name == "capsule_seal":
                if user_id not in _active_sessions:
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": f"No active session for user {user_id}. Call capsule_ingest first.",
                    }))]
                tracker = _active_sessions[user_id]

                # Build pre-extracted payload if host LLM provided facts/summary
                pre_extracted = None
                client_facts = arguments.get("facts")
                client_summary = arguments.get("summary")
                if client_facts or client_summary:
                    from capsule_memory.models.memory import MemoryFact, MemoryPayload
                    facts = []
                    for i, f in enumerate(client_facts or []):
                        facts.append(MemoryFact(
                            key=f.get("key", f"fact.{i}"),
                            value=f.get("value", ""),
                            confidence=float(f.get("confidence", 0.9)),
                            category=f.get("category", "other"),
                            source_turn=i,
                        ))
                    pre_extracted = MemoryPayload(
                        facts=facts,
                        context_summary=client_summary or "",
                    )

                capsule = await tracker.seal(
                    title=arguments.get("title", ""),
                    tags=arguments.get("tags", []),
                    pre_extracted=pre_extracted,
                )
                del _active_sessions[user_id]
                result = {
                    "capsule_id": capsule.capsule_id,
                    "title": capsule.metadata.title,
                    "turn_count": capsule.metadata.turn_count,
                    "type": capsule.capsule_type.value,
                    "extraction": "host_llm" if pre_extracted else (
                        "server_llm" if cm._config.llm_model else "rule_based"
                    ),
                }
                if not pre_extracted and not cm._config.llm_model:
                    result["hint"] = (
                        "Tip: pass 'facts' and 'summary' in capsule_seal to use "
                        "your own extraction — no server LLM config needed."
                    )
                return [types.TextContent(type="text", text=json.dumps(result))]

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


async def _auto_seal_active_sessions() -> None:
    """Auto-seal all active sessions on shutdown to prevent data loss."""
    if not _active_sessions:
        return
    logger.info("Auto-sealing %d active session(s) on shutdown...", len(_active_sessions))
    for user_id, tracker in list(_active_sessions.items()):
        if tracker.state.is_active and len(tracker.state.turns) > 0:
            try:
                capsule = await tracker.seal(title="(auto-sealed on shutdown)")
                logger.info(
                    "Auto-sealed session for user=%s → capsule=%s (%d turns)",
                    user_id, capsule.capsule_id[:12], capsule.metadata.turn_count,
                )
            except Exception as e:
                logger.warning("Auto-seal failed for user=%s: %s", user_id, e)
    _active_sessions.clear()


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

    if not get_cm()._config.llm_model:
        logger.warning(
            "CAPSULE_LLM_MODEL is not set. Memory extraction will use "
            "rule-based fallback (lower quality). To enable LLM-powered "
            "extraction, set CAPSULE_LLM_MODEL in your .mcp.json env "
            "(e.g. \"gpt-4o-mini\") along with the corresponding API key."
        )

    server = _build_server()

    async def _run() -> None:
        from mcp.server.models import InitializationOptions
        from mcp.server.lowlevel.server import NotificationOptions
        try:
            async with stdio_server() as (read_stream, write_stream):
                from capsule_memory import __version__
                init_options = InitializationOptions(
                    server_name="capsule-memory",
                    server_version=__version__,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                )
                await server.run(read_stream, write_stream, init_options)
        finally:
            await _auto_seal_active_sessions()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
