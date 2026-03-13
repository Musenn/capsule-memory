# 自动记忆模式

> [English](auto-memory.md) | **中文**

## 概述

CapsuleMemory 支持两种工作模式：

| 模式 | 工作方式 | 适用场景 |
|------|---------|---------|
| **被动模式** | 记忆自动管理，零配置 | MCP 客户端、Python SDK `remember()` |
| **主动模式** | 显式调用 ingest/seal/recall | 脚本、自动化、需要完全控制 |

大多数用户想要的是**被动模式** —— 无需操心的记忆管理。

## MCP 客户端（零配置）

将 CapsuleMemory 作为 MCP 服务器连接后，被动记忆**开箱即用**，无需任何额外配置：

1. **内置 instructions** —— 服务器自动告诉宿主 LLM 如何管理记忆。不需要 CLAUDE.md，不需要 `.cursorrules`，不需要任何手动设置。安装即用。

2. **首次录入自动召回** —— 当 `capsule_ingest` 在新会话中首次被调用时，自动召回相关历史上下文：

   ```json
   {
     "turn_id": 1,
     "session_id": "sess_abc123",
     "total_turns": 2,
     "recalled_context": "=== Historical Memory Context ===\n...",
     "recalled_facts_count": 5
   }
   ```

3. **关闭时自动封存** —— MCP 服务器退出时，所有活跃会话自动封存。不会丢失数据。

4. **MCP Prompt `memory-context`** —— 支持 MCP Prompts 的客户端可以在对话开始时请求上下文注入。

适用于 Claude Code、Claude Desktop、Cursor、Windsurf、Continue、Cline 及任何 MCP 兼容客户端。

## Python SDK（一行代码）

通过 `pip install capsule-memory` 集成的开发者：

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()

# 每次交互一行调用 —— 自动处理一切
result = await cm.remember(
    user_message="我喜欢用 black 格式化代码",
    assistant_response="好的，使用 black，行宽 88。",
    user_id="alice",
)

# 首次调用会返回历史上下文（如果有的话）
if "recalled_context" in result:
    print(result["recalled_context"])

# ... 更多交互 ...
result = await cm.remember(
    user_message="导入排序呢？",
    assistant_response="使用 isort，配合 black profile。",
    user_id="alice",
)

# 完成时封存以持久化
capsule = await cm.seal_session(
    user_id="alice",
    title="Python 工具偏好",
    tags=["python", "tooling"],
)
```

`remember()` 在一次调用中处理会话生命周期、自动召回和录入。不需要理解 session、tracker 或 extractor 等概念。

### `remember()` 内部做了什么：

1. 首次调用时为该 user_id 创建会话
2. 从历史胶囊中召回相关记忆（仅第一轮）
3. 将当前轮次录入活跃会话
4. 返回结果（含可选的召回上下文）

### 框架集成示例

```python
# FastAPI 或任何 Web 框架
@app.post("/chat")
async def chat(message: str, user_id: str):
    response = await llm.complete(message)

    # 一行代码添加持久记忆
    memory = await cm.remember(message, response, user_id=user_id)

    # 利用召回上下文增强后续回复
    if "recalled_context" in memory:
        context_store[user_id] = memory["recalled_context"]

    return {"response": response}
```

## REST API

REST API 提供同样的被动特性：

- `POST /api/v1/sessions/{id}/ingest` —— 首次录入时自动召回，返回 `recalled_context`
- `POST /api/v1/sessions/{id}/seal` —— 接受 `facts` 和 `summary` 用于宿主 LLM 提取
- 服务器关闭时自动封存所有会话

## CLI

CLI 支持完整的主动工作流：

```bash
capsule-memory ingest "如何部署？" "使用 docker-compose up -d" -s my_session
capsule-memory ingest "SSL 怎么办？" "使用 certbot 配合 nginx" -s my_session
capsule-memory seal -s my_session -t "部署指南" --tag deployment,docker
capsule-memory recall "部署 SSL"
```

## 主动模式

主动模式给你对每个步骤的完全控制：

```python
cm = CapsuleMemory()

# 手动召回
context = await cm.recall("Python 格式化", user_id="alice")

# 手动会话管理
async with cm.session("alice") as tracker:
    await tracker.ingest("问题", "回答")
    capsule = await tracker.seal(title="我的会话", tags=["标签"])
```

## 自定义 MCP 行为

MCP 服务器的内置 instructions 覆盖了大多数场景。如果需要自定义行为（如改变记忆策略），可以在客户端的系统提示词配置中覆盖（CLAUDE.md、.cursorrules 等）。内置 instructions 是合理的默认值，不是必须遵守的规则。
