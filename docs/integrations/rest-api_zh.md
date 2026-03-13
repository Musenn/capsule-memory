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
| GET | /api/v1/sessions/{id}/triggers | 待确认触发 |
| POST | /api/v1/sessions/{id}/triggers/{eid}/confirm | 确认触发 |
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

## 关键参数

### 召回

```
GET /api/v1/recall?query=搜索词&user_id=default&top_k=3
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | 搜索关键词 |
| `user_id` | 否 | 用户 ID（默认：`default`） |
| `top_k` | 否 | 最大结果数 1-10（默认：3） |

### 录入

```
POST /api/v1/sessions/{session_id}/ingest
Content-Type: application/json

{"user_message": "...", "assistant_response": "..."}
```

### 封存（基础）

```
POST /api/v1/sessions/{session_id}/seal
Content-Type: application/json

{"title": "会话标题", "tags": ["tag1"]}
```

### 宿主 LLM 提取封存（推荐）

直接传入预提取的 `facts` 和 `summary`，无需配置 `CAPSULE_LLM_MODEL`：

```
POST /api/v1/sessions/{session_id}/seal
Content-Type: application/json

{
  "title": "Python 代码风格",
  "tags": ["python"],
  "summary": "用户偏好使用 black 格式化代码。",
  "facts": [
    {"key": "preference.formatter", "value": "black", "category": "technical_preference"}
  ]
}
```

响应中包含 `extraction` 字段：`host_llm`、`server_llm` 或 `rule_based`。

## 交互式文档

访问 `http://localhost:8000/docs` 查看自动生成的 OpenAPI 文档。
