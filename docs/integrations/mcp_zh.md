# MCP Server 集成

> [English](mcp.md) | **中文**

## 概述

CapsuleMemory 提供了一个 Model Context Protocol (MCP) 服务，包含 10 个工具，适用于 Claude Code、Claude Desktop 和其他兼容 MCP 的客户端。

服务器通过 stdio 传输协议通信。宿主应用（Claude Code / Claude Desktop）自动管理服务器进程的生命周期。

## 安装

```bash
pip install 'capsule-memory[mcp]'
```

## 启动 MCP Server

推荐让 MCP 客户端自动管理服务器。如需手动运行调试：

```bash
# 通过专用入口点
capsule-memory-mcp --storage ~/.capsules --storage-type local

# 或通过 CLI 子命令
capsule-memory mcp --storage ~/.capsules
```

### 环境变量

MCP 服务器从环境变量读取配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CAPSULE_LLM_MODEL` | (空) | 可选。用于服务端提取的 litellm 模型字符串（如 `gpt-4o-mini`）。若宿主 LLM 通过 `capsule_seal` 直接提供 facts/summary，则无需配置。 |
| `CAPSULE_STORAGE_PATH` | `~/.capsules` | 存储目录路径 |
| `CAPSULE_STORAGE_TYPE` | `local` | 存储后端：`local`、`sqlite`、`redis`、`qdrant` |
| `CAPSULE_COMPRESS_THRESHOLD` | `8000` | 触发 L1 压缩的缓冲区 token 阈值 |
| `CAPSULE_COMPRESS_LAYER_MAX` | `6000` | 触发级联压缩的每层最大 token |
| `CAPSULE_SKILL_LLM_SCORE` | `false` | 启用 LLM 评分以过滤低质量 skill 触发 |
| `OPENAI_API_KEY` | — | OpenAI 兼容提供商的 API Key |

## Claude Code 配置

在项目根目录创建 `.mcp.json` 文件（项目级别），或使用 CLI 命令。

> **注意：** `capsule-memory-mcp` 必须在系统 PATH 中可访问。如果安装在 conda/venv 环境中，请使用方式 B（conda）或方式 C（完整路径），而非方式 A。

### 方式 A：直接命令（需要 `capsule-memory-mcp` 在 PATH 中）

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### 方式 B：使用 conda 环境（conda 用户推荐）

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "conda",
      "args": ["run", "-n", "capsule-memory", "--no-banner", "capsule-memory-mcp"],
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### 方式 C：使用完整路径

直接指定 Python 环境中入口点的完整路径：

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "/path/to/your/env/bin/capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### 方式 D：CLI 命令

```bash
claude mcp add capsule-memory -- capsule-memory-mcp
```

### 验证服务器是否正常

创建 `.mcp.json` 后，重启 Claude Code。运行 `/mcp` 应能看到 `capsule-memory` 已列出。如果连接失败，请检查：

1. `capsule-memory-mcp` 是否可访问？在终端运行 `capsule-memory-mcp --help` 测试。
2. 环境变量是否正确设置？
3. 查看 stderr 输出获取错误详情。

## Claude Desktop 配置

添加到 `claude_desktop_config.json`（Settings → Developer → Edit Config）：

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

## 其他 MCP 客户端（Cursor、Windsurf、Continue、Cline 等）

CapsuleMemory 兼容**所有 MCP 客户端**，不仅限于 Claude。服务器使用标准 MCP stdio 协议通信，无 Claude 特定行为。

### Cursor

在 Cursor 的 MCP 设置中添加（Settings → MCP Servers → Add）：

```json
{
  "capsule-memory": {
    "command": "capsule-memory-mcp",
    "env": {
      "CAPSULE_LLM_MODEL": "gpt-4o-mini",
      "OPENAI_API_KEY": "sk-..."
    }
  }
}
```

### Windsurf / Continue / Cline

这些客户端通常使用项目根目录的 `.mcp.json` 或类似配置文件，格式与 Claude Code 相同：

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "env": {
        "CAPSULE_LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

请查阅各客户端文档了解具体的配置文件位置和格式。

### 通用 MCP 客户端

任何支持 MCP stdio 传输协议的客户端都可以使用 CapsuleMemory：

1. 启动 `capsule-memory-mcp` 作为子进程
2. 通过 stdin/stdout 使用 NDJSON 通信（每行一条 JSON-RPC 消息）
3. 通过环境变量传递配置

### 关于 `CAPSULE_LLM_MODEL` 的说明

- **如果你的 MCP 宿主本身是 LLM**（Claude、GPT-4、Gemini 等）：可以完全不配置 `CAPSULE_LLM_MODEL`。让宿主 LLM 直接提取 facts 和 summary，通过 `capsule_seal` 传入即可。这是推荐的零配置方案。
- **如果你的 MCP 宿主不是 LLM**（脚本、自动化工具等）：需要设置 `CAPSULE_LLM_MODEL`，让服务器自行提取记忆。

## 可用工具

| 工具 | 说明 |
|------|------|
| `capsule_ingest` | 将一组 user+assistant 轮次录入活跃会话 |
| `capsule_seal` | 将当前会话封存为持久胶囊 |
| `capsule_recall` | 通过语义查询召回相关记忆（返回结构化 JSON） |
| `capsule_inject_context` | 召回记忆并返回纯文本，用于注入 system prompt |
| `capsule_list` | 列出胶囊，支持类型/标签过滤 |
| `capsule_export` | 将胶囊导出为文件（json/msgpack/universal/prompt） |
| `capsule_import` | 从文件导入胶囊 |
| `capsule_pending_triggers` | 查看待确认的技能触发事件 |
| `capsule_confirm_trigger` | 确认或忽略技能触发事件 |
| `capsule_extract_skill` | 从自然语言描述手动创建技能胶囊 |

## 工具调用示例

### 录入轮次

```json
{
  "tool": "capsule_ingest",
  "arguments": {
    "user_message": "Python 中如何排序列表？",
    "assistant_response": "用 sorted() 返回新列表，或用 .sort() 就地排序。",
    "user_id": "default"
  }
}
```

### 召回记忆

```json
{
  "tool": "capsule_recall",
  "arguments": {
    "query": "Python 排序",
    "user_id": "default",
    "top_k": 5
  }
}
```

### 封存会话（基础）

```json
{
  "tool": "capsule_seal",
  "arguments": {
    "title": "Python 基础会话",
    "tags": ["python", "basics"],
    "user_id": "default"
  }
}
```

### 宿主 LLM 提取封存（零配置，推荐）

在 Claude Code 等 LLM 客户端中使用时，宿主 LLM 可以直接提取 facts 和 summary，无需配置 `CAPSULE_LLM_MODEL`：

```json
{
  "tool": "capsule_seal",
  "arguments": {
    "title": "Python 代码风格",
    "tags": ["python", "tooling"],
    "summary": "用户偏好使用 black 格式化代码，使用 isort 配合 black profile 排序导入。",
    "facts": [
      {
        "key": "technical_preference.formatter",
        "value": "black，默认行宽 88",
        "category": "technical_preference"
      },
      {
        "key": "technical_preference.import_sorter",
        "value": "isort --profile black",
        "category": "technical_preference"
      }
    ],
    "user_id": "default"
  }
}
```

这种方式产出更高质量的记忆，因为宿主 LLM 拥有完整的对话上下文。

### 确认技能触发

```json
{
  "tool": "capsule_confirm_trigger",
  "arguments": {
    "event_id": "evt_abc123",
    "resolution": "extract_skill",
    "user_id": "default"
  }
}
```

resolution 可选值：`extract_skill`、`merge_memory`、`extract_hybrid`、`ignore`、`never`。
