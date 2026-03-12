<div align="center">
<h1><picture><source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg"><img alt="CapsuleMemory" src="assets/logo-light.svg" height="72" valign="middle"></picture></h1>
</div>

> **English** | [中文](index_zh.md)

**User-sovereign AI memory capsule system with skill extraction.**

CapsuleMemory captures, distills, and seals AI conversation memories into portable capsules that can be recalled, exported, and shared across any AI platform.

## 30-Second Quick Start

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()

# Record a conversation
async with cm.session("user_123") as session:
    await session.ingest("How to optimize Django queries?",
                         "Use select_related for FK, prefetch_related for M2M.")

# Recall later
result = await cm.recall("Django optimization", user_id="user_123")
print(result["prompt_injection"])
# Outputs a text block you can inject into any AI's system prompt
```

## Key Features

- **Session Tracking** — Ingest conversation turns, auto-detect reusable skills
- **Memory Capsules** — Seal sessions into portable, versioned capsule files
- **Skill Extraction** — 4 rule-based detectors identify reusable technical solutions
- **Universal Export** — Export to JSON, MsgPack, or plain-text prompt snippets
- **Cross-Platform** — Works with OpenAI, Claude, LangChain, Dify, Coze, and any AI
- **MCP Server** — 10 tools for Claude Code / Claude Desktop integration
- **REST API** — 16 endpoints for any HTTP client
- **CLI** — Full command-line interface with rich output

## Installation

```bash
pip install capsule-memory

# With optional backends
pip install "capsule-memory[sqlite]"    # Vector search
pip install "capsule-memory[server]"    # REST API
pip install "capsule-memory[mcp]"       # MCP Server
pip install "capsule-memory[all]"       # Everything
```

## Architecture

```
User Conversation → Session Tracker → Memory Extractor → Capsule Builder → Storage
                                    ↓
                              Skill Detector → Trigger Event → User Confirmation
                                    ↓
                              Skill Capsule (reusable knowledge)
```
