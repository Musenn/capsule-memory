# Automatic Memory Mode

> **English** | [中文](auto-memory_zh.md)

## Overview

CapsuleMemory supports two modes of operation:

| Mode | How it works | Best for |
|------|-------------|----------|
| **Passive** | Memory is managed automatically, zero config | MCP clients, Python SDK with `remember()` |
| **Active** | You explicitly call ingest/seal/recall | Scripts, automation, full control |

Most users want **passive mode** — memory that just works without thinking about it.

## MCP Clients (Zero Config)

When you connect CapsuleMemory as an MCP server, passive memory works **out of the box** with no additional configuration:

1. **Built-in instructions** — The server automatically tells the host LLM how to manage memory. No CLAUDE.md, no `.cursorrules`, no manual setup needed. Just install and connect.

2. **Auto-recall on first turn** — When `capsule_ingest` is called for the first time in a session, relevant historical context is automatically recalled and returned:

   ```json
   {
     "turn_id": 1,
     "session_id": "sess_abc123",
     "total_turns": 2,
     "recalled_context": "=== Historical Memory Context ===\n...",
     "recalled_facts_count": 5
   }
   ```

3. **Auto-seal on shutdown** — When the MCP server exits, all active sessions are automatically sealed. No data loss.

4. **MCP Prompt `memory-context`** — Clients that support MCP prompts can request context injection at conversation start.

This applies to Claude Code, Claude Desktop, Cursor, Windsurf, Continue, Cline, and any other MCP-compatible client.

## Python SDK (One Line)

For developers integrating via `pip install capsule-memory`:

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()

# One call per exchange — handles everything automatically
result = await cm.remember(
    user_message="I prefer black for formatting",
    assistant_response="Noted, using black with line length 88.",
    user_id="alice",
)

# First call returns historical context if available
if "recalled_context" in result:
    print(result["recalled_context"])

# ... more exchanges ...
result = await cm.remember(
    user_message="What about imports?",
    assistant_response="Use isort with black profile.",
    user_id="alice",
)

# When done, seal to persist
capsule = await cm.seal_session(
    user_id="alice",
    title="Python Tooling Preferences",
    tags=["python", "tooling"],
)
```

`remember()` handles session lifecycle, auto-recall, and ingestion in one call. No need to understand sessions, trackers, or extractors.

### What `remember()` does internally:

1. Creates a session on first call for a user_id
2. Recalls relevant history from past capsules (first turn only)
3. Ingests the turn into the active session
4. Returns the result with optional recalled context

### Framework integration example

```python
# FastAPI / any web framework
@app.post("/chat")
async def chat(message: str, user_id: str):
    response = await llm.complete(message)

    # One line adds persistent memory
    memory = await cm.remember(message, response, user_id=user_id)

    # Use recalled context to enhance future responses
    if "recalled_context" in memory:
        # Prepend to next system prompt
        context_store[user_id] = memory["recalled_context"]

    return {"response": response}
```

## REST API

The REST API provides the same passive features:

- `POST /api/v1/sessions/{id}/ingest` — Auto-recalls on first turn, returns `recalled_context`
- `POST /api/v1/sessions/{id}/seal` — Accepts `facts` and `summary` for host LLM extraction
- Server auto-seals all sessions on shutdown

## CLI

The CLI supports the complete active workflow:

```bash
capsule-memory ingest "How to deploy?" "Use docker-compose up -d" -s my_session
capsule-memory ingest "What about SSL?" "Use certbot with nginx" -s my_session
capsule-memory seal -s my_session -t "Deployment Guide" --tag deployment,docker
capsule-memory recall "deployment SSL"
```

## Active Mode

Active mode gives you full control over each step:

```python
cm = CapsuleMemory()

# Manual recall
context = await cm.recall("Python formatting", user_id="alice")

# Manual session management
async with cm.session("alice") as tracker:
    await tracker.ingest("question", "answer")
    capsule = await tracker.seal(title="My Session", tags=["tag"])
```

## Customizing MCP Behavior

The MCP server's built-in instructions cover most use cases. If you need to customize the behavior (e.g., change what gets memorized), you can override them in your client's system prompt configuration (CLAUDE.md, .cursorrules, etc.). The built-in instructions serve as a sensible default — not a requirement.
