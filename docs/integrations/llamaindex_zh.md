# LlamaIndex 集成

> [English](llamaindex.md) | **中文**

## CapsuleMemoryLlamaIndexMemory

`ChatMemoryBuffer` 的即插即用替代，将对话历史持久化到 CapsuleMemory 胶囊。

无需硬依赖 `llama_index` — 通过鸭子类型实现 memory 接口（`put`、`get`、`get_all`、`reset`）。

```python
from capsule_memory import CapsuleMemory
from capsule_memory.adapters.llamaindex import CapsuleMemoryLlamaIndexMemory

cm = CapsuleMemory()
memory = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="user_123")

# 配合 LlamaIndex ReActAgent 使用
from llama_index.core.agent import ReActAgent
agent = ReActAgent.from_tools(tools, memory=memory)
agent.chat("如何在 Kubernetes 上部署？")

# 完成后封存
memory.seal(title="K8s 会话", tags=["llamaindex", "devops"])
```

## 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cm` | `CapsuleMemory` | 必填 | CapsuleMemory 实例 |
| `user_id` | `str` | 必填 | 用户标识，用于会话管理 |
| `session_id` | `str \| None` | `None` | 自定义会话 ID（省略则自动生成） |
| `token_limit` | `int` | `3000` | `get()` 返回的最大 token 数（约 4 字符/token） |
| `auto_recall` | `bool` | `True` | 是否自动从封存胶囊中召回上下文 |

## 接口方法

### `put(message)`

向缓冲区添加消息。接受任何具有 `role` 和 `content` 属性的对象（包括 LlamaIndex 的 `ChatMessage`）。自动配对 user + assistant 消息并录入会话。

### `get(input=None)`

获取截断到 `token_limit` 的聊天历史。当 `auto_recall=True` 且提供了 `input` 时，会在返回的历史前插入一条包含封存胶囊召回上下文的系统消息。

### `get_all()`

返回所有消息，不做截断。

### `reset()`

清空缓冲区并创建新会话。不会删除已封存的胶囊。

### `seal(title="", tags=None)`

将当前会话封存为持久胶囊。

## 自动召回

当 `auto_recall=True`（默认）时，调用 `get(input="某个查询")` 会自动搜索已封存胶囊中的相关上下文，并作为系统消息注入返回历史的开头。这使 LLM 无需手动配置即可获取跨会话知识。

## 示例：多会话工作流

```python
cm = CapsuleMemory()

# 会话 1：了解用户偏好
memory = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="alice")
memory.put(SimpleChatMessage(role="user", content="我偏好 Python 和 FastAPI"))
memory.put(SimpleChatMessage(role="assistant", content="已记录！"))
memory.seal(title="偏好设置", tags=["prefs"])

# 会话 2：自动召回之前的上下文
memory2 = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="alice")
history = memory2.get(input="推荐一个框架")
# history[0] 是一条包含召回偏好信息的系统消息
```

完整可运行示例参见 `examples/integrate_llamaindex.py`。
