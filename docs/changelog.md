# Changelog

> **English** | [中文](changelog_zh.md)

All notable changes to CapsuleMemory are documented here.

## [0.1.1] — 2026-03-13

### Added

- **Passive Memory Mode** (zero-config automatic memory management)
  - MCP Server: built-in `instructions` parameter — host LLM auto-manages memory without CLAUDE.md or .cursorrules
  - MCP Prompts: `memory-context` prompt for context injection at conversation start
  - Auto-recall on first ingest: new sessions automatically recall relevant history
  - Auto-seal on shutdown: MCP and REST servers seal all active sessions on exit (no data loss)
  - Python SDK: `remember()` one-call API handles session lifecycle, recall, and ingestion
  - Python SDK: `seal_session()` companion method for `remember()`

- **Host LLM Extraction** (three-tier extraction strategy)
  - MCP `capsule_seal`: accepts `facts` and `summary` from the host LLM directly
  - REST API `POST /seal`: accepts `facts` and `summary` in request body
  - Extraction mode indicator in seal response: `host_llm` / `server_llm` / `rule_based`

- **CLI Enhancements**
  - `capsule-memory ingest` command for session-based turn ingestion
  - `capsule-memory seal` command to seal sessions from CLI

- **REST API Extensibility**
  - `create_app()` public API: returns a configured FastAPI instance for mounting/extending
  - `GET /sessions/{id}/triggers` endpoint (was undocumented)
  - `POST /sessions/{id}/triggers/{eid}/confirm` endpoint (was undocumented)

- **Multi-client MCP Documentation**
  - Configuration examples for Cursor, Windsurf, Continue, Cline, and generic MCP clients
  - `CAPSULE_LLM_MODEL` guidance per client type

- **Auto-memory Documentation** (`docs/integrations/auto-memory.md`)
  - Comprehensive guide covering passive vs active modes across all surfaces

### Changed

- `litellm` moved from hard dependency to optional (`pip install capsule-memory[llm]`)
  - Core package now installs without LLM dependencies (~100MB lighter)
  - Rule-based extraction works out of the box; LLM features require `[llm]` extra
- Version strings in MCP server and REST API now use `__version__` (no more hardcoded values)
- REST API uses FastAPI `lifespan` context manager instead of deprecated `on_event("shutdown")`
- `_managed_sessions` in `CapsuleMemory` moved from class-level to instance-level (prevents cross-instance leaks)
- Adaptive memory compressor (`MemoryCompressor`) with layered L1/L2/cascade strategy

### Fixed

- Import crash when `litellm` is not installed (lazy imports in extractor, compressor, refiner)
- `MemoryExtractor` constructor now takes `ExtractorConfig` object (not raw kwargs)

## [0.1.0] — 2026-03-11

### Added

- **Core Engine**
  - `CapsuleMemory` main entry point with session management, recall, export/import
  - `SessionTracker` with turn ingestion, snapshot, seal, and recall
  - `CapsuleStore` with list, get, merge, diff, fork operations
  - 4 capsule types: MEMORY, SKILL, HYBRID, CONTEXT
  - 4 lifecycle states: DRAFT, SEALED, IMPORTED, ARCHIVED
  - HMAC-SHA256 checksums with protocol fingerprint verification
  - Fernet symmetric encryption with PBKDF2 key derivation for capsule export/import

- **Skill Detection**
  - 4 priority-ordered rules: UserAffirmation, RepeatPattern, StructuredOutput, LengthSignificance
  - `SkillTriggerEvent` with actions: extract_skill, merge_memory, extract_hybrid, ignore, never
  - Optional LLM-based scoring via `CAPSULE_SKILL_LLM_SCORE=true`

- **Storage Backends**
  - `LocalStorage` — file-based with keyword search
  - `SQLiteStorage` — sqlite-vec with 384-dim vector search
  - `RedisStorage` — redis.asyncio with PubSub trigger channel
  - `QdrantStorage` — vector search with per-user collections

- **Integrations**
  - REST API server (FastAPI, 16 endpoints, optional Bearer auth)
  - MCP Server (10 tools for Claude Code)
  - CLI (typer + rich, 9 commands)
  - LangChain adapter (`CapsuleMemoryLangChainMemory`)
  - LlamaIndex adapter (`CapsuleMemoryLlamaIndexMemory`)
  - Web Widget (embeddable capsule panel)
  - TypeScript SDK (`@capsule-memory/sdk`)

- **Export Formats**
  - JSON, MessagePack, Universal (cross-platform), Prompt (text snippet)

- **Documentation**
  - Quickstart guide, core concepts, API reference
  - Integration guides for REST API, OpenAI, LangChain
  - Example scripts for LangChain, OpenAI, multi-agent, and more
