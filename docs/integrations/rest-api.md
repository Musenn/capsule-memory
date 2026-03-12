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

## Interactive Docs

Visit `http://localhost:8000/docs` for auto-generated OpenAPI documentation.
