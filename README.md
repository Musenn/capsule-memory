<div align="center">

<h1><picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Musenn/capsule-memory/main/docs/assets/logo-dark.svg"><source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/Musenn/capsule-memory/main/docs/assets/logo-light.svg"><img alt="CapsuleMemory" src="https://raw.githubusercontent.com/Musenn/capsule-memory/main/docs/assets/logo-light.svg" height="72" valign="middle"></picture></h1>

**User-sovereign AI memory capsule system**

Track, distill, and seal memories and skills in real-time within a single session,
seamlessly embedding them into any AI framework via a portable capsule format.

[![CI](https://github.com/Musenn/capsule-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/Musenn/capsule-memory/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/Musenn/capsule-memory/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/capsule-memory)](https://pypi.org/project/capsule-memory/)
[![npm](https://img.shields.io/npm/v/@capsule-memory/sdk)](https://www.npmjs.com/package/@capsule-memory/sdk)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

**English** | [中文](https://github.com/Musenn/capsule-memory/blob/main/docs/README_zh.md)

</div>

---

## Why CapsuleMemory?

Most AI memory systems persist everything automatically, giving users little control over what gets stored. CapsuleMemory takes a different approach:

- **Session Isolation**: Nothing persists by default. Users actively choose when to seal a session into a durable capsule.
- **Skill Detection**: A rule-based engine identifies reusable skills (code patterns, workflows, procedures) from conversations in real-time.
- **Portable Capsule Format**: Export to JSON / MessagePack / Universal format. Import into any system, no vendor lock-in.
- **Framework-agnostic**: Drop-in adapters for LangChain, LlamaIndex, or use via REST API / MCP Server.

## Installation

**Python (PyPI)**

```bash
pip install capsule-memory
```

**TypeScript / JavaScript (npm)**

```bash
npm install @capsule-memory/sdk
```

Pre-built packages are also available on the [GitHub Releases](https://github.com/Musenn/capsule-memory/releases) page as direct downloads (`.whl`, `.tar.gz`, `.tgz`).

## Quick Start

### Passive Memory (one line per exchange)

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()

# One call handles session lifecycle, auto-recall, and ingestion
result = await cm.remember("I prefer black for formatting", "Noted, using black.", user_id="alice")

# First call returns historical context if available
if "recalled_context" in result:
    print(result["recalled_context"])

# When done, seal to persist
await cm.seal_session(user_id="alice", title="Python Tooling", tags=["python"])
```

### Active Mode (full control)

```python
async with cm.session("user_123") as session:
    await session.ingest(user_message, ai_response)
    # Session auto-seals on exit, or call session.seal() explicitly
```

### Recall memories across sessions

```python
result = await cm.recall(query="deployment steps", user_id="user_123")
print(result["prompt_injection"])  # Ready to inject into any LLM
```

### MCP Server (Claude Code / Cursor / Windsurf / etc.)

Zero-config passive memory — built-in instructions tell the host LLM how to manage memory automatically. No CLAUDE.md or .cursorrules needed.

```bash
pip install 'capsule-memory[mcp]'
capsule-memory-mcp
```

### REST API

```bash
pip install 'capsule-memory[server]'
capsule-memory serve --port 8000
# Visit http://localhost:8000/docs for interactive API docs
```

### CLI

```bash
capsule-memory ingest "How to deploy?" "Use docker-compose" -s my_session
capsule-memory seal -s my_session -t "Deployment Guide" --tag deployment
capsule-memory recall "deployment"
```

## Architecture

```
Session ─── ingest() ──→ Skill Detection ──→ seal() ──→ Capsule (MEMORY / SKILL / HYBRID)
                              │                              │
                              ▼                              ▼
                        SkillTriggerEvent              Storage Backend
                        (user confirms)           (Local / SQLite / Redis / Qdrant)
```

## Storage Backends

| Backend | Search | Best For |
|---------|--------|----------|
| LocalStorage | Keyword | Development, single-user |
| SQLiteStorage | Vector (384-dim) | Production, local deployment |
| RedisStorage | Keyword | Multi-service, real-time |
| QdrantStorage | Vector (384-dim) | Production, scalable |

```bash
# Install optional extras
pip install capsule-memory[llm]      # LLM-powered extraction (litellm)
pip install capsule-memory[crypto]   # Encrypted capsule export/import
pip install capsule-memory[sqlite]   # SQLite + sentence-transformers
pip install capsule-memory[redis]    # Redis
pip install capsule-memory[qdrant]   # Qdrant
pip install capsule-memory[all]      # Everything
```

## Integrations

| Integration | Type | Docs |
|------------|------|------|
| Auto Memory | Passive + Active modes | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/auto-memory.md) |
| OpenAI | Native OpenAI SDK adapter | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/openai.md) |
| REST API | 16 endpoints, Bearer auth | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/rest-api.md) |
| MCP Server | 10 tools, built-in instructions | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/mcp.md) |
| LangChain | Drop-in `ConversationBufferMemory` | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/langchain.md) |
| LlamaIndex | Drop-in `ChatMemoryBuffer` | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/llamaindex.md) |
| Web Widget | Embeddable JS panel | [Guide](https://github.com/Musenn/capsule-memory/blob/main/docs/integrations/widget.md) |
| TypeScript SDK | `@capsule-memory/sdk` | [sdk-js/](https://github.com/Musenn/capsule-memory/tree/main/sdk-js) |

## Documentation

Full documentation: [https://Musenn.github.io/capsule-memory](https://Musenn.github.io/capsule-memory)

- [Quick Start](https://github.com/Musenn/capsule-memory/blob/main/docs/quickstart.md)
- [Core Concepts](https://github.com/Musenn/capsule-memory/blob/main/docs/concepts.md)
- [API Reference](https://github.com/Musenn/capsule-memory/blob/main/docs/api-reference.md)
- [Changelog](https://github.com/Musenn/capsule-memory/blob/main/docs/changelog.md)

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/my-feature`)
3. Install dev dependencies: `pip install -e ".[dev,server]"`
4. Run tests: `pytest tests/`
5. Run linter: `ruff check capsule_memory/ tests/`
6. Submit a pull request

## License

Licensed under [Apache License 2.0](https://github.com/Musenn/capsule-memory/blob/main/LICENSE).

See [NOTICE](https://github.com/Musenn/capsule-memory/blob/main/NOTICE) for attribution requirements.

---

<div align="center">

Created by [Xuelin Xu (Musenn)](https://github.com/Musenn)

Copyright 2025-2026 Xuelin Xu. Licensed under Apache-2.0.

</div>
