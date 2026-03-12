# 快速开始

> [English](quickstart.md) | **中文**

## 安装

```bash
pip install capsule-memory
```

## 基本用法

```python
import asyncio
from capsule_memory import CapsuleMemory

async def main():
    cm = CapsuleMemory()

    # 创建会话并录入对话轮次
    async with cm.session("user_123") as session:
        await session.ingest(
            "我在用 Python 写一个爬虫",
            "推荐使用 httpx 做异步请求，selectolax 解析 HTML。"
        )
        await session.ingest(
            "如何处理限流？",
            "用 asyncio.Semaphore 控制并发数量，"
            "加上 tenacity 实现指数退避重试。"
        )
    # 退出上下文时自动封存

    # 列出已封存的胶囊
    capsules = await cm.store.list(user_id="user_123")
    print(f"胶囊数量: {len(capsules)}")

    # 召回记忆
    result = await cm.recall("爬虫最佳实践", user_id="user_123")
    print(result["prompt_injection"])

asyncio.run(main())
```

## Mock 模式（无需 API Key）

设置 `CAPSULE_MOCK_EXTRACTOR=true` 使用模拟数据提取（不调用 LLM）：

```bash
CAPSULE_MOCK_EXTRACTOR=true python your_script.py
```

## 导出与导入

```python
# 导出为通用格式（任意平台可读）
await cm.export_capsule(capsule_id, "memory.json", format="universal")

# 导出为纯文本提示片段
await cm.export_capsule(capsule_id, "memory.txt", format="prompt")

# 从文件导入
imported = await cm.import_capsule("memory.json", user_id="new_user")
```

## CLI 用法

```bash
# 列出胶囊
capsule-memory list --user user_123

# 查看胶囊详情
capsule-memory show <capsule_id>

# 导出胶囊
capsule-memory export <capsule_id> output.json --format universal

# 召回记忆
capsule-memory recall "web scraping" --user user_123

# 启动 REST API 服务
capsule-memory serve --port 8000

# 启动 MCP 服务
capsule-memory mcp
```
