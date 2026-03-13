# 更新日志

> [English](changelog.md) | **中文**

CapsuleMemory 的所有重要变更均记录于此。

## [0.1.1] — 2026-03-13

### 新增

- **被动记忆模式**（零配置自动记忆管理）
  - MCP Server：内置 `instructions` 参数 — 宿主 LLM 无需 CLAUDE.md 或 .cursorrules 即可自动管理记忆
  - MCP Prompts：`memory-context` 提示词，支持对话开始时上下文注入
  - 首次录入自动召回：新会话首轮自动召回相关历史记忆
  - 关闭时自动封存：MCP 和 REST 服务器退出时自动封存所有活跃会话（零数据丢失）
  - Python SDK：`remember()` 一行代码 API，处理会话生命周期、召回和录入
  - Python SDK：`seal_session()` 配合 `remember()` 的封存方法

- **宿主 LLM 提取**（三层提取策略）
  - MCP `capsule_seal`：接受宿主 LLM 直接提供的 `facts` 和 `summary`
  - REST API `POST /seal`：请求体接受 `facts` 和 `summary`
  - 封存响应中包含提取模式标识：`host_llm` / `server_llm` / `rule_based`

- **CLI 增强**
  - `capsule-memory ingest` 命令：基于会话的轮次录入
  - `capsule-memory seal` 命令：从 CLI 封存会话

- **REST API 可扩展性**
  - `create_app()` 公开 API：返回已配置的 FastAPI 实例，支持挂载/扩展
  - `GET /sessions/{id}/triggers` 端点（此前未文档化）
  - `POST /sessions/{id}/triggers/{eid}/confirm` 端点（此前未文档化）

- **多客户端 MCP 文档**
  - Cursor、Windsurf、Continue、Cline 及通用 MCP 客户端配置示例
  - 按客户端类型的 `CAPSULE_LLM_MODEL` 使用指南

- **自动记忆文档** (`docs/integrations/auto-memory.md`)
  - 覆盖所有表面的被动与主动模式完整指南

### 变更

- `litellm` 从硬依赖移至可选依赖（`pip install capsule-memory[llm]`）
  - 核心包安装不再需要 LLM 依赖（减轻约 100MB）
  - 规则提取开箱即用；LLM 功能需安装 `[llm]` 扩展
- MCP 服务器和 REST API 中的版本号改用 `__version__`（不再硬编码）
- REST API 改用 FastAPI `lifespan` 上下文管理器替代已弃用的 `on_event("shutdown")`
- `CapsuleMemory` 中 `_managed_sessions` 从类级别移至实例级别（防止跨实例泄漏）
- 自适应分层记忆压缩器（`MemoryCompressor`），支持 L1/L2/级联策略

### 修复

- 未安装 `litellm` 时导入崩溃（extractor、compressor、refiner 改用延迟导入）
- `MemoryExtractor` 构造函数现在接受 `ExtractorConfig` 对象（而非裸参数）

## [0.1.0] — 2026-03-11

### 新增

- **核心引擎**
  - `CapsuleMemory` 主入口，支持会话管理、召回、导出/导入
  - `SessionTracker` 支持轮次录入、快照、封存、召回
  - `CapsuleStore` 支持列表、获取、合并、对比、Fork 操作
  - 4 种胶囊类型：MEMORY、SKILL、HYBRID、CONTEXT
  - 4 种生命周期状态：DRAFT、SEALED、IMPORTED、ARCHIVED
  - 基于协议指纹的 HMAC-SHA256 校验和
  - Fernet 对称加密（PBKDF2 密钥派生）导出/导入

- **技能检测**
  - 4 条优先级排序规则：UserAffirmation、RepeatPattern、StructuredOutput、LengthSignificance
  - `SkillTriggerEvent` 支持操作：extract_skill、merge_memory、extract_hybrid、ignore、never
  - 可选 LLM 评分（通过 `CAPSULE_SKILL_LLM_SCORE=true` 启用）

- **存储后端**
  - `LocalStorage` — 基于文件，关键词搜索
  - `SQLiteStorage` — sqlite-vec，384 维向量搜索
  - `RedisStorage` — redis.asyncio，支持 PubSub 触发通道
  - `QdrantStorage` — 向量搜索，按用户分集合

- **集成**
  - REST API 服务（FastAPI，16 个端点，可选 Bearer 认证）
  - MCP Server（10 个工具，适配 Claude Code）
  - CLI（typer + rich，9 条命令）
  - LangChain 适配器（`CapsuleMemoryLangChainMemory`）
  - LlamaIndex 适配器（`CapsuleMemoryLlamaIndexMemory`）
  - Web Widget（可嵌入的胶囊面板）
  - TypeScript SDK（`@capsule-memory/sdk`）

- **导出格式**
  - JSON、MessagePack、Universal（跨平台）、Prompt（文本片段）

- **文档**
  - 快速开始指南、核心概念、API 参考
  - REST API、OpenAI、LangChain 集成指南
  - LangChain、OpenAI、多 Agent 等示例脚本
