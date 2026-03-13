# MCP Server Integration

> **English** | [中文](mcp_zh.md)

## Overview

CapsuleMemory provides a Model Context Protocol (MCP) server with 10 tools, designed for use with Claude Code, Claude Desktop, and other MCP-compatible clients.

The server communicates over stdio transport. The host application (Claude Code / Claude Desktop) manages the server process lifecycle automatically.

## Installation

```bash
pip install 'capsule-memory[mcp]'
```

## Start the MCP Server

The recommended way is to let the MCP client manage the server. If you need to run it manually for debugging:

```bash
# Via the dedicated entry point
capsule-memory-mcp --storage ~/.capsules --storage-type local

# Or via the CLI subcommand
capsule-memory mcp --storage ~/.capsules
```

### Environment Variables

The MCP server reads configuration from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPSULE_LLM_MODEL` | (empty) | Optional. litellm model string for server-side extraction (e.g. `gpt-4o-mini`). Not needed if the host LLM provides facts/summary via `capsule_seal`. |
| `CAPSULE_STORAGE_PATH` | `~/.capsules` | Storage directory path |
| `CAPSULE_STORAGE_TYPE` | `local` | Storage backend: `local`, `sqlite`, `redis`, `qdrant` |
| `CAPSULE_COMPRESS_THRESHOLD` | `8000` | Buffer token threshold before L1 compression triggers |
| `CAPSULE_COMPRESS_LAYER_MAX` | `6000` | Max tokens per compression layer before cascade |
| `CAPSULE_SKILL_LLM_SCORE` | `false` | Enable LLM scoring for skill trigger quality |
| `OPENAI_API_KEY` | — | API key for OpenAI-compatible providers |

## Claude Code Configuration

Create a `.mcp.json` file in your project root (project-level), or use the CLI command.

> **Important:** `capsule-memory-mcp` must be on your PATH. If installed in a conda/venv environment, use Option B (conda) or Option C (full path) instead of Option A.

### Option A: Direct command (requires `capsule-memory-mcp` on PATH)

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### Option B: With conda environment (recommended for conda users)

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "conda",
      "args": ["run", "-n", "capsule-memory", "--no-banner", "capsule-memory-mcp"],
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### Option C: Full path to executable

Use the full path to the entry point in your Python environment:

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "/path/to/your/env/bin/capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### Option D: CLI command

```bash
claude mcp add capsule-memory -- capsule-memory-mcp
```

### Verify the server works

After creating `.mcp.json`, restart Claude Code. You should see `capsule-memory` listed when you run `/mcp`. If the server fails to connect, check:

1. Is `capsule-memory-mcp` accessible? Run `capsule-memory-mcp --help` in your terminal.
2. Are the environment variables set correctly?
3. Check stderr output for error details.

## Claude Desktop Configuration

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

## Other MCP Clients (Cursor, Windsurf, Continue, Cline, etc.)

CapsuleMemory works with **any MCP-compatible client**, not just Claude. The server speaks standard MCP over stdio — no Claude-specific behavior.

### Cursor

Add to Cursor's MCP settings (Settings → MCP Servers → Add):

```json
{
  "capsule-memory": {
    "command": "capsule-memory-mcp",
    "env": {
      "CAPSULE_LLM_MODEL": "gpt-4o-mini",
      "OPENAI_API_KEY": "sk-..."
    }
  }
}
```

### Windsurf / Continue / Cline

These clients typically use a `.mcp.json` or similar config file in the project root. The format is the same as Claude Code:

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

Check each client's documentation for the exact config file location and format.

### Generic MCP Client

Any client that supports MCP stdio transport can use CapsuleMemory. Requirements:

1. Spawn `capsule-memory-mcp` as a subprocess
2. Communicate via stdin/stdout using NDJSON (one JSON-RPC message per line)
3. Pass environment variables for configuration

### Notes on `CAPSULE_LLM_MODEL`

- **If your MCP host is an LLM** (Claude, GPT-4, Gemini, etc.): you can skip `CAPSULE_LLM_MODEL` entirely. Instead, have the host LLM extract facts and summary, then pass them to `capsule_seal` directly. This is the recommended zero-config approach.
- **If your MCP host is not an LLM** (a script, automation tool, etc.): set `CAPSULE_LLM_MODEL` so the server can extract memories on its own.

## Available Tools

| Tool | Description |
|------|-------------|
| `capsule_ingest` | Ingest a user+assistant turn pair into the active session |
| `capsule_seal` | Seal the current session into a persistent capsule |
| `capsule_recall` | Recall relevant memories by semantic query (structured JSON) |
| `capsule_inject_context` | Recall memory and return plain text for system prompt injection |
| `capsule_list` | List capsules with optional type/tag filtering |
| `capsule_export` | Export a capsule to file (json/msgpack/universal/prompt) |
| `capsule_import` | Import a capsule from file |
| `capsule_pending_triggers` | View pending skill trigger events awaiting confirmation |
| `capsule_confirm_trigger` | Confirm or dismiss a skill trigger event |
| `capsule_extract_skill` | Manually create a skill capsule from a natural language description |

## Tool Examples

### Ingest a Turn

```json
{
  "tool": "capsule_ingest",
  "arguments": {
    "user_message": "How do I sort a list in Python?",
    "assistant_response": "Use sorted() for a new list or .sort() for in-place.",
    "user_id": "default"
  }
}
```

### Recall Memories

```json
{
  "tool": "capsule_recall",
  "arguments": {
    "query": "Python sorting",
    "user_id": "default",
    "top_k": 5
  }
}
```

### Seal Session (basic)

```json
{
  "tool": "capsule_seal",
  "arguments": {
    "title": "Python Basics Session",
    "tags": ["python", "basics"],
    "user_id": "default"
  }
}
```

### Seal with Host LLM Extraction (zero-config, recommended)

When used from Claude Code or other LLM-powered clients, the host LLM can extract facts and summary directly — no `CAPSULE_LLM_MODEL` configuration needed:

```json
{
  "tool": "capsule_seal",
  "arguments": {
    "title": "Python Code Style",
    "tags": ["python", "tooling"],
    "summary": "User prefers black for formatting and isort with black profile for imports.",
    "facts": [
      {
        "key": "technical_preference.formatter",
        "value": "black with default line length 88",
        "category": "technical_preference"
      },
      {
        "key": "technical_preference.import_sorter",
        "value": "isort --profile black",
        "category": "technical_preference"
      }
    ],
    "user_id": "default"
  }
}
```

This produces higher quality memories because the host LLM has full conversation context.

### Confirm a Skill Trigger

```json
{
  "tool": "capsule_confirm_trigger",
  "arguments": {
    "event_id": "evt_abc123",
    "resolution": "extract_skill",
    "user_id": "default"
  }
}
```

Resolution options: `extract_skill`, `merge_memory`, `extract_hybrid`, `ignore`, `never`.
