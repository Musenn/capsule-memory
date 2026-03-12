<div align="center">
<h1><picture><source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg"><img alt="CapsuleMemory" src="assets/logo-light.svg" height="72" valign="middle"></picture></h1>
</div>

> [English](index.md) | **中文**

**用户主权的 AI 记忆胶囊系统，支持技能提取。**

CapsuleMemory 从 AI 对话中捕获、提炼并封存记忆，生成可召回、可导出、可跨平台共享的便携式胶囊。

## 30 秒快速入门

```python
from capsule_memory import CapsuleMemory

cm = CapsuleMemory()

# 记录一段对话
async with cm.session("user_123") as session:
    await session.ingest("如何优化 Django 查询？",
                         "FK 用 select_related，M2M 用 prefetch_related。")

# 后续召回
result = await cm.recall("Django 优化", user_id="user_123")
print(result["prompt_injection"])
# 输出一段可直接注入任意 AI 系统提示词的文本
```

## 核心特性

- **会话追踪** — 录入对话轮次，自动检测可复用技能
- **记忆胶囊** — 将会话封存为便携、版本化的胶囊文件
- **技能提取** — 4 条规则引擎实时识别可复用的技术方案
- **通用导出** — 支持 JSON、MsgPack 或纯文本提示片段
- **跨平台** — 兼容 OpenAI、Claude、LangChain、Dify、Coze 及任意 AI
- **MCP Server** — 10 个工具，适配 Claude Code / Claude Desktop
- **REST API** — 16 个端点，支持任意 HTTP 客户端
- **CLI** — 完整命令行界面，支持 rich 输出

## 安装

```bash
pip install capsule-memory

# 可选后端
pip install "capsule-memory[sqlite]"    # 向量搜索
pip install "capsule-memory[server]"    # REST API
pip install "capsule-memory[mcp]"       # MCP Server
pip install "capsule-memory[all]"       # 全部安装
```

## 架构

```
用户对话 → SessionTracker → MemoryExtractor → CapsuleBuilder → 存储后端
                          ↓
                    SkillDetector → TriggerEvent → 用户确认
                          ↓
                    技能胶囊（可复用知识）
```
