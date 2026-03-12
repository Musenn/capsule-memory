# Changelog

> **English** | [中文](changelog_zh.md)

All notable changes to CapsuleMemory are documented here.

## [0.1.0] — 2026-03-11

### Added

- **Core Engine**
  - `CapsuleMemory` main entry point with session management, recall, export/import
  - `SessionTracker` with turn ingestion, snapshot, seal, and recall
  - `CapsuleStore` with list, get, merge, diff, fork operations
  - 4 capsule types: MEMORY, SKILL, HYBRID, CONTEXT
  - 4 lifecycle states: DRAFT, SEALED, IMPORTED, ARCHIVED
  - HMAC-SHA256 checksums with protocol fingerprint verification
  - AES-GCM encryption for capsule export/import

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
