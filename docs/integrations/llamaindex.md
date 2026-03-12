# LlamaIndex Integration

> **English** | [中文](llamaindex_zh.md)

## CapsuleMemoryLlamaIndexMemory

Drop-in replacement for `ChatMemoryBuffer` that persists conversation history to CapsuleMemory capsules.

No hard dependency on `llama_index` — works via duck-typing the memory interface (`put`, `get`, `get_all`, `reset`).

```python
from capsule_memory import CapsuleMemory
from capsule_memory.adapters.llamaindex import CapsuleMemoryLlamaIndexMemory

cm = CapsuleMemory()
memory = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="user_123")

# Use with LlamaIndex ReActAgent
from llama_index.core.agent import ReActAgent
agent = ReActAgent.from_tools(tools, memory=memory)
agent.chat("How do I deploy on Kubernetes?")

# Seal when done
memory.seal(title="K8s Session", tags=["llamaindex", "devops"])
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cm` | `CapsuleMemory` | required | CapsuleMemory instance |
| `user_id` | `str` | required | User identifier for session management |
| `session_id` | `str \| None` | `None` | Custom session ID (auto-generated if omitted) |
| `token_limit` | `int` | `3000` | Max tokens returned by `get()` (approx. 4 chars/token) |
| `auto_recall` | `bool` | `True` | Prepend recalled context from sealed capsules |

## Interface Methods

### `put(message)`

Add a message to the buffer. Accepts any object with `role` and `content` attributes (including LlamaIndex `ChatMessage`). Automatically pairs user + assistant messages and ingests them into the session.

### `get(input=None)`

Retrieve chat history truncated to `token_limit`. When `auto_recall=True` and `input` is provided, a system message with recalled context from sealed capsules is prepended.

### `get_all()`

Return all messages without truncation.

### `reset()`

Clear the buffer and create a fresh session. Does not delete sealed capsules.

### `seal(title="", tags=None)`

Seal the current session into a persistent capsule.

## Auto-Recall

When `auto_recall=True` (default), calling `get(input="some query")` automatically searches sealed capsules for relevant context and injects it as a system message at the beginning of the returned history. This gives the LLM access to cross-session knowledge without manual configuration.

## Example: Multi-Session Workflow

```python
cm = CapsuleMemory()

# Session 1: Learn about the user
memory = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="alice")
memory.put(SimpleChatMessage(role="user", content="I prefer Python and FastAPI"))
memory.put(SimpleChatMessage(role="assistant", content="Noted!"))
memory.seal(title="Preferences", tags=["prefs"])

# Session 2: Auto-recall previous context
memory2 = CapsuleMemoryLlamaIndexMemory(cm=cm, user_id="alice")
history = memory2.get(input="recommend a framework")
# history[0] is a system message with recalled preferences
```

See `examples/integrate_llamaindex.py` for a complete runnable example.
