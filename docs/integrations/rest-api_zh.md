# REST API 集成

> [English](rest-api.md) | **中文**

## 启动服务

```bash
capsule-memory serve --port 8000
```

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/sessions | 创建会话 |
| POST | /api/v1/sessions/{id}/ingest | 录入轮次 |
| GET | /api/v1/sessions/{id}/snapshot | 会话快照 |
| POST | /api/v1/sessions/{id}/seal | 封存会话 |
| GET | /api/v1/capsules | 列出胶囊 |
| GET | /api/v1/capsules/{id} | 获取胶囊 |
| DELETE | /api/v1/capsules/{id} | 删除胶囊 |
| GET | /api/v1/capsules/{id}/export | 导出胶囊 |
| GET | /api/v1/capsules/{id}/prompt-snippet | 获取提示片段 |
| POST | /api/v1/capsules/import | 导入胶囊 |
| POST | /api/v1/capsules/merge | 合并胶囊 |
| GET | /api/v1/capsules/pending-triggers | Widget 轮询 |
| GET | /api/v1/recall | 召回记忆 |
| GET | /health | 健康检查 |

## 认证

设置 `CAPSULE_API_KEY` 环境变量启用 Bearer Token 认证：

```bash
CAPSULE_API_KEY=your-secret-key capsule-memory serve
```

所有请求须携带：`Authorization: Bearer your-secret-key`

## 交互式文档

访问 `http://localhost:8000/docs` 查看自动生成的 OpenAPI 文档。
