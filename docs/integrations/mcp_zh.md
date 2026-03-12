# MCP Server 集成

> [English](mcp.md) | **中文**

## 概述

CapsuleMemory 提供了一个 Model Context Protocol (MCP) 服务，包含 10 个工具，适用于 Claude Code 和其他兼容 MCP 的客户端。

## 启动 MCP Server

```bash
capsule-memory mcp --storage local --user default_user
```

或通过 Python：

```python
from capsule_memory.server.mcp_server import create_mcp_server

server = create_mcp_server(storage_type="local", user_id="default_user")
server.run()
```

## 可用工具

| 工具 | 说明 |
|------|------|
| `capsule_ingest` | 将一组 user+assistant 轮次录入活跃会话 |
| `capsule_seal` | 将当前会话封存为持久胶囊 |
| `capsule_recall` | 通过语义查询召回相关记忆 |
| `capsule_list` | 列出当前用户的所有胶囊 |
| `capsule_get` | 获取指定胶囊的完整详情 |
| `capsule_export` | 将胶囊导出到文件 |
| `capsule_import` | 从文件导入胶囊 |
| `capsule_inject_context` | 从纯文本创建 CONTEXT 胶囊 |
| `capsule_extract_skill` | 从描述和步骤中提取技能胶囊 |
| `capsule_merge` | 将多个胶囊合并为一个 |

## Claude Code 配置

添加到 `.claude/settings.json`：

```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory",
      "args": ["mcp", "--storage", "local", "--user", "my_user"]
    }
  }
}
```

## 工具调用示例

### 录入轮次

```json
{
  "tool": "capsule_ingest",
  "arguments": {
    "user_message": "Python 中如何排序列表？",
    "assistant_response": "用 sorted() 返回新列表，或用 .sort() 就地排序。"
  }
}
```

### 召回记忆

```json
{
  "tool": "capsule_recall",
  "arguments": {
    "query": "Python 排序",
    "top_k": 5
  }
}
```

### 封存会话

```json
{
  "tool": "capsule_seal",
  "arguments": {
    "title": "Python 基础会话",
    "tags": ["python", "basics"]
  }
}
```
