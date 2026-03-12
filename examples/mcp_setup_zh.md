# 💊 CapsuleMemory MCP Server 配置指南

> [English](mcp_setup.md) | **中文**

## 安装
```bash
pip install "capsule-memory[mcp]"
```

## Claude Code 配置 (.claude/settings.json)
```json
{
  "mcpServers": {
    "capsule-memory": {
      "command": "capsule-memory-mcp",
      "args": ["--storage", "~/.capsules", "--storage-type", "local"],
      "env": {
        "CAPSULE_MOCK_EXTRACTOR": "false",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

## Claude Desktop 配置
格式与上方相同，配置文件位置：
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## 可用工具（10 个）
| 工具 | 说明 |
|------|------|
| `capsule_ingest` | 将对话轮次录入记忆会话 |
| `capsule_seal` | 将会话封存为持久胶囊 |
| `capsule_recall` | 召回相关记忆（返回完整结构） |
| `capsule_inject_context` | 召回并返回纯文本，可直接注入系统提示词 |
| `capsule_list` | 列出历史胶囊 |
| `capsule_export` | 导出胶囊到文件（json/msgpack/universal/prompt） |
| `capsule_import` | 从文件导入胶囊 |
| `capsule_pending_triggers` | 查看待处理的技能触发事件 |
| `capsule_confirm_trigger` | 确认或忽略技能触发 |
| `capsule_extract_skill` | 从描述手动创建技能胶囊 |
