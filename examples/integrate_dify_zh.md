# 💊 CapsuleMemory + Dify 集成指南

> [English](integrate_dify.md) | **中文**

## 概述

通过 HTTP 请求节点将 CapsuleMemory 集成到 Dify 工作流和 Chatflow 中。
无需安装 SDK — Dify 直接调用 CapsuleMemory REST API。

## 前置条件

1. CapsuleMemory REST 服务已运行：
   ```bash
   capsule-memory serve --port 8000
   ```
2. Dify 实例可访问（云版或自部署）

---

## 场景一：Dify 工作流集成

### 第一步：添加记忆召回的 HTTP 请求节点

在 Dify 工作流编辑器中，在 LLM 节点之前添加一个 **HTTP 请求** 节点。

**HTTP 请求配置：**
```json
{
  "method": "GET",
  "url": "http://your-server:8000/api/v1/recall",
  "params": {
    "q": "{{#input.query#}}",
    "user_id": "{{#input.user_id#}}",
    "top_k": "3"
  },
  "headers": {
    "Authorization": "Bearer {{#env.CAPSULE_API_KEY#}}"
  },
  "timeout": 10
}
```

### 第二步：变量映射

将 HTTP 响应映射到 LLM 节点的系统提示词：

| 源变量 | 目标 | 说明 |
|--------|------|------|
| `http_response.body.prompt_injection` | LLM 系统提示词（追加） | 记忆上下文块 |
| `http_response.body.facts` | 可选上下文变量 | 结构化事实列表 |
| `http_response.body.sources` | 调试输出 | 来源胶囊 ID |

在 LLM 节点的系统提示词中追加：
```
{{#http_node.body.prompt_injection#}}
```

### 第三步：添加记忆录入的 HTTP 请求节点（可选）

在 LLM 节点之后，添加另一个 HTTP 请求节点保存交互记录：

**创建会话（首次调用）：**
```json
{
  "method": "POST",
  "url": "http://your-server:8000/api/v1/sessions",
  "params": {
    "user_id": "{{#input.user_id#}}"
  }
}
```

**录入轮次：**
```json
{
  "method": "POST",
  "url": "http://your-server:8000/api/v1/sessions/{{#session_node.body.session_id#}}/ingest",
  "body": {
    "user_message": "{{#input.query#}}",
    "assistant_response": "{{#llm_node.text#}}",
    "user_id": "{{#input.user_id#}}"
  }
}
```

---

## 场景二：Dify Chatflow 集成

### 第一步：配置会话变量

在 Chatflow 设置中，添加会话变量 `capsule_session_id`（类型：string）。

### 第二步：前处理钩子

在前处理流程中添加 HTTP 请求节点：

```json
{
  "method": "GET",
  "url": "http://your-server:8000/api/v1/recall",
  "params": {
    "q": "{{#sys.query#}}",
    "user_id": "{{#sys.user_id#}}",
    "top_k": "3"
  }
}
```

### 第三步：系统提示词模板

在 LLM 节点中使用以下系统提示词模板：

```
你是一个有用的助手。如果相关，请参考以下记忆上下文：

{{#pre_process.body.prompt_injection#}}

基于此上下文和你的知识回答用户的问题。
```

### 第四步：后处理钩子（保存记忆）

在后处理流程中添加 HTTP 请求节点录入轮次：

```json
{
  "method": "POST",
  "url": "http://your-server:8000/api/v1/sessions/{{#conversation.capsule_session_id#}}/ingest",
  "body": {
    "user_message": "{{#sys.query#}}",
    "assistant_response": "{{#llm.text#}}",
    "user_id": "{{#sys.user_id#}}"
  }
}
```

---

## 使用建议

- **会话管理**：每个 Dify 对话创建一个 CapsuleMemory 会话。将 `session_id` 存储在 Dify 的会话变量中。
- **封存**：当对话结束或达到轮次阈值时，添加"封存" HTTP 请求。
- **性能**：使用 LocalStorage 时 recall API 通常在 100ms 内响应。生产环境建议使用 SQLiteStorage 以启用向量搜索。
- **安全**：在服务端设置 `CAPSULE_API_KEY`，并在 Dify 的 HTTP 请求头中传递。
