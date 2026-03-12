# 💊 CapsuleMemory MCP Server Setup

> **English** | [中文](mcp_setup_zh.md)

## Installation
```bash
pip install "capsule-memory[mcp]"
```

## Claude Code Configuration (.claude/settings.json)
```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "args": ["--storage", "~/.capsules", "--storage-type", "local"],
      "env": {
        "CAPSULE_MOCK_EXTRACTOR": "false",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

## Claude Desktop Configuration
Same format as above, placed in:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Available Tools (10)
| Tool | Description |
|------|-------------|
| `capsule_ingest` | Ingest a conversation turn into the memory session |
| `capsule_seal` | Seal the session into a persistent capsule |
| `capsule_recall` | Recall relevant memories (returns full structure) |
| `capsule_inject_context` | Recall and return plain text for system prompt injection |
| `capsule_list` | List historical capsules |
| `capsule_export` | Export capsule to file (json/msgpack/universal/prompt) |
| `capsule_import` | Import capsule from file |
| `capsule_pending_triggers` | View pending skill trigger events |
| `capsule_confirm_trigger` | Confirm or dismiss a skill trigger |
| `capsule_extract_skill` | Manually create a skill capsule from description |
