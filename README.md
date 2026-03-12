<div align="center">

<h1><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg"><source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-light.svg"><img alt="CapsuleMemory" src="docs/assets/logo-light.svg" height="72" valign="middle"></picture></h1>

**User-sovereign AI memory capsule system**

Track, distill, and seal memories and skills in real-time within a single session,
seamlessly embedding them into any AI framework via a portable capsule format.

[![CI](https://github.com/Musenn/capsule-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/Musenn/capsule-memory/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/capsule-memory)](https://pypi.org/project/capsule-memory/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

**English** | [中文](docs/README_zh.md)

</div>

---

## Why CapsuleMemory?

Most AI memory systems persist everything automatically, giving users little control over what gets stored. CapsuleMemory takes a different approach:

- **Session Isolation**: Nothing persists by default. Users actively choose when to seal a session into a durable capsule.
- **Skill Detection**: A rule-based engine identifies reusable skills (code patterns, workflows, procedures) from conversations in real-time.
- **Portable Capsule Format**: Export to JSON / MessagePack / Universal format. Import into any system, no vendor lock-in.
- **Framework-agnostic**: Drop-in adapters for LangChain, LlamaIndex, or use via REST API / MCP Server.

## Quick Start

```bash
pip install capsule-memory
```

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()
async with cm.session("user_123") as session:
    await session.ingest(user_message, ai_response)
    # Session auto-seals on exit, or call session.seal() explicitly
```

### Recall memories across sessions

```python
result = await cm.recall(query="deployment steps", user_id="user_123")
print(result["prompt_injection"])  # Ready to inject into any LLM
```

### REST API

```bash
pip install capsule-memory[server]
capsule-memory serve --port 8000
# Visit http://localhost:8000/docs for interactive API docs
```

### MCP Server (Claude Code)

```bash
capsule-memory mcp --storage local --user my_user
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
# Install optional backends
pip install capsule-memory[sqlite]   # SQLite + sentence-transformers
pip install capsule-memory[redis]    # Redis
pip install capsule-memory[qdrant]   # Qdrant
pip install capsule-memory[all]      # Everything
```

## Integrations

| Integration | Type | Docs |
|------------|------|------|
| REST API | 16 endpoints, Bearer auth | [Guide](docs/integrations/rest-api.md) |
| MCP Server | 10 tools for Claude Code | [Guide](docs/integrations/mcp.md) |
| LangChain | Drop-in `ConversationBufferMemory` | [Guide](docs/integrations/langchain.md) |
| LlamaIndex | Drop-in `ChatMemoryBuffer` | [Guide](docs/integrations/llamaindex.md) |
| Web Widget | Embeddable JS panel | [Guide](docs/integrations/widget.md) |
| TypeScript SDK | `@capsule-memory/sdk` | [sdk-js/](sdk-js/) |

## Documentation

Full documentation: [https://Musenn.github.io/capsule-memory](https://Musenn.github.io/capsule-memory)

- [Quick Start](docs/quickstart.md)
- [Core Concepts](docs/concepts.md)
- [API Reference](docs/api-reference.md)
- [Changelog](docs/changelog.md)

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/my-feature`)
3. Install dev dependencies: `pip install -e ".[dev,server]"`
4. Run tests: `pytest tests/`
5. Run linter: `ruff check capsule_memory/ tests/`
6. Submit a pull request

## License

Licensed under [Apache License 2.0](LICENSE).

See [NOTICE](NOTICE) for attribution requirements.

---

<div align="center">

Created by [Xuelin Xu (Musenn)](https://github.com/Musenn)

Copyright 2025-2026 Xuelin Xu. Licensed under Apache-2.0.

</div>
