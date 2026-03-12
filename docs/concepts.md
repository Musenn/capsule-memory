# Core Concepts

> **English** | [中文](concepts_zh.md)

## Capsule Types

| Type | Description | Use Case |
|------|------------|----------|
| `MEMORY` | Distilled conversation facts and context | General conversation history |
| `SKILL` | Reusable technical solution or procedure | Code patterns, workflows |
| `HYBRID` | Memory + Skills combined | Rich sessions with both facts and skills |
| `CONTEXT` | Plain text context (imported) | External context injection |

## Session Lifecycle

```
1. Create Session  →  cm.session("user_id")
2. Ingest Turns    →  session.ingest(user_msg, ai_response)
3. Skill Detection →  Background: checks 4 rules per turn
4. Seal            →  session.seal() or auto-seal on exit
5. Storage         →  Capsule persisted to storage backend
```

## Capsule Status

- **DRAFT** — Session in progress, not yet sealed
- **SEALED** — Finalized and persisted, checksum computed
- **IMPORTED** — Imported from external source or forked
- **ARCHIVED** — Soft-deleted, retained for audit

## Skill Detection Rules

Rules are evaluated in priority order (short-circuit on first match):

| Priority | Rule | Trigger |
|----------|------|---------|
| 1 (highest) | UserAffirmation | User says "save this", "remember this", etc. |
| 2 | RepeatPattern | Similar structured content repeated 2+ times |
| 3 | StructuredOutput | Code blocks, numbered lists, technical keywords |
| 4 (lowest) | LengthSignificance | Long response (800+ chars) with technical density |

When a rule matches, a `SkillTriggerEvent` is created. The user can:
- **extract_skill** — Create a skill capsule
- **merge_memory** — Merge into session memory
- **extract_hybrid** — Create a hybrid capsule
- **ignore** — Dismiss this event
- **never** — Never trigger this rule again

## Storage Backends

| Backend | Search | Best For |
|---------|--------|----------|
| LocalStorage | Keyword | Development, single-user |
| SQLiteStorage | Vector (384-dim) | Production, local deployment |
| RedisStorage | Keyword | Multi-service, real-time |
| QdrantStorage | Vector (384-dim) | Production, scalable |

## Protocol Attribution

Every capsule carries attribution metadata:
- `schema_version`: `capsule-schema/1.0+35c1b411`
- `capsule_id`: Prefix includes protocol fingerprint
- `checksum`: HMAC-SHA256 with protocol key material
- `metadata.capsule_created_by`: `capsule-memory`
- `metadata.capsule_project_url`: GitHub repository URL
