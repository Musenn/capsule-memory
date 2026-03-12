# 更新日志

> [English](changelog.md) | **中文**

CapsuleMemory 的所有重要变更均记录于此。

## [0.1.0] — 2026-03-11

### 新增

- **核心引擎**
  - `CapsuleMemory` 主入口，支持会话管理、召回、导出/导入
  - `SessionTracker` 支持轮次录入、快照、封存、召回
  - `CapsuleStore` 支持列表、获取、合并、对比、Fork 操作
  - 4 种胶囊类型：MEMORY、SKILL、HYBRID、CONTEXT
  - 4 种生命周期状态：DRAFT、SEALED、IMPORTED、ARCHIVED
  - 基于协议指纹的 HMAC-SHA256 校验和
  - AES-GCM 加密导出/导入

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
