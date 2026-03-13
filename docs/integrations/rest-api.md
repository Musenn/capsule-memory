# REST API Integration

> **English** | [中文](rest-api_zh.md)

## Start the Server

```bash
capsule-memory serve --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/sessions | Create session |
| POST | /api/v1/sessions/{id}/ingest | Ingest turn |
| GET | /api/v1/sessions/{id}/snapshot | Session snapshot |
| POST | /api/v1/sessions/{id}/seal | Seal session |
| GET | /api/v1/sessions/{id}/triggers | Pending triggers |
| POST | /api/v1/sessions/{id}/triggers/{eid}/confirm | Confirm trigger |
| GET | /api/v1/capsules | List capsules |
| GET | /api/v1/capsules/{id} | Get capsule |
| DELETE | /api/v1/capsules/{id} | Delete capsule |
| GET | /api/v1/capsules/{id}/export | Export capsule |
| GET | /api/v1/capsules/{id}/prompt-snippet | Get prompt snippet |
| POST | /api/v1/capsules/import | Import capsule |
| POST | /api/v1/capsules/merge | Merge capsules |
| GET | /api/v1/capsules/pending-triggers | Widget polling |
| GET | /api/v1/recall | Recall memories |
| GET | /health | Health check |

## Authentication

Set `CAPSULE_API_KEY` environment variable to enable Bearer token auth:

```bash
CAPSULE_API_KEY=your-secret-key capsule-memory serve
```

All requests must include: `Authorization: Bearer your-secret-key`

## Key Parameters

### Recall

```
GET /api/v1/recall?query=search+term&user_id=default&top_k=3
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Search query text |
| `user_id` | No | User ID (default: `default`) |
| `top_k` | No | Max results 1-10 (default: 3) |

### Ingest

```
POST /api/v1/sessions/{session_id}/ingest
Content-Type: application/json

{"user_message": "...", "assistant_response": "..."}
```

### Seal (basic)

```
POST /api/v1/sessions/{session_id}/seal
Content-Type: application/json

{"title": "Session Title", "tags": ["tag1"]}
```

### Seal with Host LLM Extraction (recommended)

Pass pre-extracted `facts` and `summary` directly — no `CAPSULE_LLM_MODEL` needed:

```
POST /api/v1/sessions/{session_id}/seal
Content-Type: application/json

{
  "title": "Python Code Style",
  "tags": ["python"],
  "summary": "User prefers black for formatting.",
  "facts": [
    {"key": "preference.formatter", "value": "black", "category": "technical_preference"}
  ]
}
```

Response includes an `extraction` field: `host_llm`, `server_llm`, or `rule_based`.

## Interactive Docs

Visit `http://localhost:8000/docs` for auto-generated OpenAPI documentation.
