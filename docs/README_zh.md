<div align="center">

<h1><picture><source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg"><img alt="CapsuleMemory" src="assets/logo-light.svg" height="72" valign="middle"></picture></h1>

**用户主权的 AI 记忆胶囊系统**

在单次会话中实时追踪、提炼并封存记忆与技能，
通过便携式胶囊格式无缝嵌入任意 AI 框架。

[![CI](https://github.com/Musenn/capsule-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/Musenn/capsule-memory/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/Musenn/capsule-memory/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/capsule-memory)](https://pypi.org/project/capsule-memory/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

[English](https://github.com/Musenn/capsule-memory/blob/main/README.md) | **中文**

</div>

---

## 为什么选择 CapsuleMemory？

大多数 AI 记忆系统会自动持久化所有内容，用户对存储什么几乎没有控制权。CapsuleMemory 采用了不同的思路：

- **会话隔离**：默认不持久化任何内容。用户主动决定何时将会话封存为持久胶囊。
- **技能检测**：基于规则的引擎从对话中实时识别可复用的技能（代码模式、工作流、操作流程）。
- **便携式胶囊格式**：支持导出为 JSON / MessagePack / 通用格式，可导入任意系统，无供应商锁定。
- **框架无关**：提供 LangChain、LlamaIndex 的即插即用适配器，或通过 REST API / MCP Server 接入。

## 快速开始

### 安装

```bash
pip install capsule-memory
```

### 被动记忆（每次交互一行代码）

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()

# 一次调用处理会话生命周期、自动召回和录入
result = await cm.remember("我偏好用 black 格式化", "好的，使用 black。", user_id="alice")

# 首次调用会返回历史上下文（如果有的话）
if "recalled_context" in result:
    print(result["recalled_context"])

# 完成时封存以持久化
await cm.seal_session(user_id="alice", title="Python 工具偏好", tags=["python"])
```

### 主动模式（完全控制）

```python
async with cm.session("user_123") as session:
    await session.ingest(user_message, ai_response)
    # 退出上下文时自动封存，也可手动调用 session.seal()
```

### 跨会话记忆召回

```python
result = await cm.recall(query="部署步骤", user_id="user_123")
print(result["prompt_injection"])  # 可直接注入任意 LLM 的上下文
```

### MCP Server（Claude Code / Cursor / Windsurf 等）

零配置被动记忆 — 内置 instructions 自动告知宿主 LLM 如何管理记忆，无需 CLAUDE.md 或 .cursorrules。

```bash
pip install 'capsule-memory[mcp]'
capsule-memory-mcp
```

### REST API

```bash
pip install 'capsule-memory[server]'
capsule-memory serve --port 8000
# 打开 http://localhost:8000/docs 查看交互式 API 文档
```

### CLI

```bash
capsule-memory ingest "如何部署？" "使用 docker-compose" -s my_session
capsule-memory seal -s my_session -t "部署指南" --tag deployment
capsule-memory recall "部署"
```

## 架构概览

```
Session ─── ingest() ──→ 技能检测 ──→ seal() ──→ Capsule (MEMORY / SKILL / HYBRID)
                              │                              │
                              ▼                              ▼
                        SkillTriggerEvent              存储后端
                        (用户确认操作)           (Local / SQLite / Redis / Qdrant)
```

## 胶囊类型

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `MEMORY` | 提炼后的对话事实与上下文 | 通用会话历史 |
| `SKILL` | 可复用的技术方案或操作流程 | 代码模式、工作流 |
| `HYBRID` | 记忆 + 技能的组合 | 包含事实和技能的复杂会话 |
| `CONTEXT` | 纯文本上下文（外部导入） | 外部知识注入 |

## 胶囊生命周期

| 状态 | 说明 |
|------|------|
| **DRAFT** | 会话进行中，尚未封存 |
| **SEALED** | 已完成封存并持久化，已计算校验和 |
| **IMPORTED** | 从外部来源导入或从其他胶囊 Fork |
| **ARCHIVED** | 软删除，保留用于审计 |

## 存储后端

| 后端 | 搜索方式 | 适用场景 |
|------|----------|----------|
| LocalStorage | 关键词匹配 | 开发环境、单用户 |
| SQLiteStorage | 向量搜索 (384维) | 生产环境、本地部署 |
| RedisStorage | 关键词匹配 | 多服务、实时场景 |
| QdrantStorage | 向量搜索 (384维) | 生产环境、可水平扩展 |

```bash
# 安装可选扩展
pip install capsule-memory[llm]      # LLM 提取（litellm）
pip install capsule-memory[crypto]   # 加密导出/导入
pip install capsule-memory[sqlite]   # SQLite + sentence-transformers
pip install capsule-memory[redis]    # Redis
pip install capsule-memory[qdrant]   # Qdrant
pip install capsule-memory[all]      # 全部安装
```

## 技能检测规则

规则按优先级顺序执行，首次命中即短路：

| 优先级 | 规则 | 触发条件 |
|--------|------|----------|
| 1（最高） | UserAffirmation | 用户说"保存这个"、"记住这个"等 |
| 2 | RepeatPattern | 类似结构化内容重复出现 2 次以上 |
| 3 | StructuredOutput | 代码块、编号列表、技术关键词 |
| 4（最低） | LengthSignificance | 长回复（800+ 字符）且技术密度高 |

命中规则后生成 `SkillTriggerEvent`，用户可选择：
- **extract_skill** — 创建技能胶囊
- **merge_memory** — 合并到会话记忆
- **extract_hybrid** — 创建混合胶囊
- **ignore** — 忽略此事件
- **never** — 永远不再触发此规则

## 集成方式

| 集成 | 类型 | 文档 |
|------|------|------|
| 自动记忆 | 被动 + 主动双模式 | [指南](integrations/auto-memory_zh.md) |
| OpenAI | 原生 OpenAI SDK 适配器 | [指南](integrations/openai_zh.md) |
| REST API | 16 个端点，Bearer 认证 | [指南](integrations/rest-api_zh.md) |
| MCP Server | 10 个工具，内置 instructions | [指南](integrations/mcp_zh.md) |
| LangChain | 即插即用 `ConversationBufferMemory` | [指南](integrations/langchain_zh.md) |
| LlamaIndex | 即插即用 `ChatMemoryBuffer` | [指南](integrations/llamaindex_zh.md) |
| Web Widget | 可嵌入的 JS 面板 | [指南](integrations/widget_zh.md) |
| TypeScript SDK | `@capsule-memory/sdk` | [sdk-js/](https://github.com/Musenn/capsule-memory/tree/main/sdk-js) |

## 导出与导入

```python
# 导出为通用格式（任意平台可读）
await cm.export_capsule(capsule_id, "memory.json", format="universal")

# 导出为纯文本提示片段
await cm.export_capsule(capsule_id, "memory.txt", format="prompt")

# 从文件导入
imported = await cm.import_capsule("memory.json", user_id="new_user")
```

## CLI 命令

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

## 完整文档

文档站点：[https://Musenn.github.io/capsule-memory](https://Musenn.github.io/capsule-memory)

- [快速开始](quickstart_zh.md)
- [核心概念](concepts_zh.md)
- [API 参考](api-reference_zh.md)
- [更新日志](changelog_zh.md)

## 参与贡献

欢迎贡献代码！请先开一个 Issue 讨论你想要的改动。

1. Fork 本仓库
2. 创建特性分支（`git checkout -b feature/my-feature`）
3. 安装开发依赖：`pip install -e ".[dev,server]"`
4. 运行测试：`pytest tests/`
5. 运行代码检查：`ruff check capsule_memory/ tests/`
6. 提交 Pull Request

## 许可证

基于 [Apache License 2.0](https://github.com/Musenn/capsule-memory/blob/main/LICENSE) 开源。

详见 [NOTICE](https://github.com/Musenn/capsule-memory/blob/main/NOTICE) 了解归属要求。

---

<div align="center">

由 [Xuelin Xu (Musenn)](https://github.com/Musenn) 创建

Copyright 2025-2026 Xuelin Xu. Licensed under Apache-2.0.

</div>
