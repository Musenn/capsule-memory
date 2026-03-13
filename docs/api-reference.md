# API Reference

> **English** | [中文](api-reference_zh.md)

## CapsuleMemory

Main entry point for the CapsuleMemory system.

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory(
    storage=None,           # BaseStorage instance (auto-created from config)
    config=None,            # CapsuleMemoryConfig (auto-loaded from env)
    skill_detection=True,   # Enable skill detection
    on_skill_trigger=None,  # Callback for skill trigger events
)
```

### cm.session()

Create a session context manager.

```python
async with cm.session(
    user_id="user_123",
    session_id=None,           # Auto-generated if None
    agent_id=None,             # Optional agent identifier
    origin_platform="unknown", # Platform name
    auto_seal_on_exit=True,    # Auto-seal when exiting context
) as session:
    await session.ingest(user_msg, ai_response)
```

### cm.recall()

Recall relevant memories across sealed capsules.

```python
result = await cm.recall(
    query="search term",
    user_id="user_123",
    top_k=5,
)
# Returns: {"facts": [...], "skills": [...], "summary": "...",
#           "prompt_injection": "...", "sources": [...]}
```

### cm.export_capsule()

Export a capsule to file.

```python
path = await cm.export_capsule(
    capsule_id="cap_...",
    output_path="output.json",
    format="universal",  # json | msgpack | universal | prompt
    encrypt=False,
    passphrase="",
)
```

### cm.import_capsule()

Import a capsule from file.

```python
capsule = await cm.import_capsule(
    file_path="input.json",
    user_id="target_user",
    passphrase="",
)
```

### cm.store

Access the CapsuleStore for advanced operations.

```python
# List capsules
capsules = await cm.store.list(user_id="user_123", capsule_type=CapsuleType.MEMORY)

# Get single capsule
capsule = await cm.store.get(capsule_id)

# Merge capsules
merged = await cm.store.merge([id1, id2], title="Merged")

# Diff capsules
diff = await cm.store.diff(id_a, id_b)

# Fork capsule to new user
forked = await cm.store.fork(capsule_id, new_user_id="agent_b")
```

## SessionTracker

### session.ingest()

Ingest a conversation turn pair.

```python
turn = await session.ingest(
    user_message="Hello",
    assistant_response="Hi there!",
    tokens=0,  # Optional token count
)
# Returns: ConversationTurn (the user turn)
```

### session.seal()

Seal the session into a persistent capsule.

```python
capsule = await session.seal(
    title="Session Title",
    tags=["tag1", "tag2"],
)
```

### session.snapshot()

Get current session state.

```python
snap = await session.snapshot()
# Returns: {"session_id", "user_id", "turn_count", "is_active", ...}
```

### session.recall()

Recall memories within session context.

```python
result = await session.recall(query="topic", top_k=5)
```

## CapsuleMemoryConfig

```python
from capsule_memory import CapsuleMemoryConfig

config = CapsuleMemoryConfig(
    storage_type="local",          # local | sqlite | redis | qdrant
    storage_path="~/.capsules",
    storage_url="",                # For redis/qdrant
    skill_detection=True,
    enable_llm_scorer=False,
    llm_model="gpt-4o-mini",      # or any litellm-supported model
    default_notifier="cli",        # cli | none
    encrypt_by_default=False,
    compress_threshold=8000,       # Buffer token threshold before L1 compression
    compress_layer_max=6000,       # Max tokens per layer before cascade compression
)

# Or from environment variables
config = CapsuleMemoryConfig.from_env()
```
