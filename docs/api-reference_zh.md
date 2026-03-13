# API 参考

> [English](api-reference.md) | **中文**

## CapsuleMemory

系统主入口。

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory(
    storage=None,           # BaseStorage 实例（根据配置自动创建）
    config=None,            # CapsuleMemoryConfig（自动从环境变量加载）
    skill_detection=True,   # 启用技能检测
    on_skill_trigger=None,  # 技能触发事件回调
)
```

### cm.session()

创建会话上下文管理器。

```python
async with cm.session(
    user_id="user_123",
    session_id=None,           # 为 None 时自动生成
    agent_id=None,             # 可选的 Agent 标识
    origin_platform="unknown", # 来源平台名称
    auto_seal_on_exit=True,    # 退出上下文时自动封存
) as session:
    await session.ingest(user_msg, ai_response)
```

### cm.recall()

跨封存胶囊召回相关记忆。

```python
result = await cm.recall(
    query="搜索词",
    user_id="user_123",
    top_k=5,
)
# 返回: {"facts": [...], "skills": [...], "summary": "...",
#         "prompt_injection": "...", "sources": [...]}
```

### cm.export_capsule()

将胶囊导出为文件。

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

从文件导入胶囊。

```python
capsule = await cm.import_capsule(
    file_path="input.json",
    user_id="target_user",
    passphrase="",
)
```

### cm.store

访问 CapsuleStore 进行高级操作。

```python
# 列出胶囊
capsules = await cm.store.list(user_id="user_123", capsule_type=CapsuleType.MEMORY)

# 获取单个胶囊
capsule = await cm.store.get(capsule_id)

# 合并胶囊
merged = await cm.store.merge([id1, id2], title="合并后的胶囊")

# 对比胶囊差异
diff = await cm.store.diff(id_a, id_b)

# Fork 胶囊到其他用户
forked = await cm.store.fork(capsule_id, new_user_id="agent_b")
```

## SessionTracker

### session.ingest()

录入一组对话轮次。

```python
turn = await session.ingest(
    user_message="你好",
    assistant_response="你好！有什么可以帮你的？",
    tokens=0,  # 可选 token 计数
)
# 返回: ConversationTurn（用户轮次）
```

### session.seal()

将会话封存为持久胶囊。

```python
capsule = await session.seal(
    title="会话标题",
    tags=["tag1", "tag2"],
)
```

### session.snapshot()

获取当前会话状态快照。

```python
snap = await session.snapshot()
# 返回: {"session_id", "user_id", "turn_count", "is_active", ...}
```

### session.recall()

在会话上下文中召回记忆。

```python
result = await session.recall(query="主题", top_k=5)
```

## CapsuleMemoryConfig

```python
from capsule_memory import CapsuleMemoryConfig

config = CapsuleMemoryConfig(
    storage_type="local",          # local | sqlite | redis | qdrant
    storage_path="~/.capsules",
    storage_url="",                # redis/qdrant 连接地址
    skill_detection=True,
    enable_llm_scorer=False,
    llm_model="gpt-4o-mini",      # 或任何 litellm 支持的模型
    default_notifier="cli",        # cli | none
    encrypt_by_default=False,
    compress_threshold=8000,       # L1 压缩触发的缓冲区 token 阈值
    compress_layer_max=6000,       # 级联压缩触发的每层最大 token 数
)

# 或从环境变量加载
config = CapsuleMemoryConfig.from_env()
```
