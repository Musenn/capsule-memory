# MCP Server Integration

> **English** | [中文](mcp_zh.md)

## Overview

CapsuleMemory provides a Model Context Protocol (MCP) server with 10 tools, designed for use with Claude Code and other MCP-compatible clients.

## Start the MCP Server

```bash
capsule-memory mcp --storage local --user default_user
```

Or via Python:

```python
from capsule_memory.server.mcp_server import create_mcp_server

server = create_mcp_server(storage_type="local", user_id="default_user")
server.run()
```

## Available Tools

| Tool | Description |
|------|-------------|
| `capsule_ingest` | Ingest a user+assistant turn pair into the active session |
| `capsule_seal` | Seal the current session into a persistent capsule |
| `capsule_recall` | Recall relevant memories by semantic query |
| `capsule_list` | List all capsules for the current user |
| `capsule_get` | Get full details of a specific capsule |
| `capsule_export` | Export a capsule to file |
| `capsule_import` | Import a capsule from file |
| `capsule_inject_context` | Create a CONTEXT capsule from plain text |
| `capsule_extract_skill` | Extract a skill capsule from description + steps |
| `capsule_merge` | Merge multiple capsules into one |

## Claude Code Configuration

Add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory",
      "args": ["mcp", "--storage", "local", "--user", "my_user"]
    }
  }
}
```

## Tool Examples

### Ingest a Turn

```json
{
  "tool": "capsule_ingest",
  "arguments": {
    "user_message": "How do I sort a list in Python?",
    "assistant_response": "Use sorted() for a new list or .sort() for in-place."
  }
}
```

### Recall Memories

```json
{
  "tool": "capsule_recall",
  "arguments": {
    "query": "Python sorting",
    "top_k": 5
  }
}
```

### Seal Session

```json
{
  "tool": "capsule_seal",
  "arguments": {
    "title": "Python Basics Session",
    "tags": ["python", "basics"]
  }
}
```
