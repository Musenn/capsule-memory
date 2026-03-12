# 零代码记忆迁移指南

> [English](zero_code_migration.md) | **中文**

## 概述

无需编写任何代码，即可在不同 AI 平台之间迁移对话记忆。
使用 CapsuleMemory Widget 的导出功能和纯文本提示片段完成迁移。

---

## 第一步：从 CapsuleMemory Widget 导出

1. 打开嵌入了 CapsuleMemory Widget 的页面
2. 点击**胶囊图标**打开胶囊列表面板
3. 找到你想迁移的胶囊
4. 点击胶囊卡片上的**导出**按钮
5. 在下拉菜单中选择 **"Prompt"** 格式

6. 下载的 `.txt` 文件包含如下纯文本提示片段：

```
=== Memory Context ===
[Source: quickstart | Time: 2025-03-10 14:30]
[Topic: Django 查询优化]

Background: 关于优化 Django ORM 查询的讨论...

Key Facts:
  - user.lang: Python
  - framework: Django
  - optimization: M2M 用 prefetch_related，FK 用 select_related

Available Skills:
  [Django N+1 修复] 使用 prefetch_related 消除 N+1 查询
    Trigger: 当用户反馈数据库查询慢时
    Instructions: 在 queryset 上添加 prefetch_related('related_model')...

=== Memory Context End ===
```

---

## 第二步：粘贴到 ChatGPT

1. 打开 **ChatGPT** (chat.openai.com)
2. 点击你的对话或新建一个
3. 进入 **"自定义指令"** 或 **"系统提示词"**（API Playground 中）
4. 将导出的提示片段粘贴到系统指令字段
5. ChatGPT 现在拥有了该对话的历史上下文

---

## 第三步：粘贴到 Claude

1. 打开 **Claude** (claude.ai)
2. 新建一个对话
3. 在第一条消息中粘贴提示片段，并添加前缀：

```
请使用以下来自之前对话的上下文：

[在此粘贴导出的提示片段]

现在，基于此上下文继续：[你的新问题]
```

---

## 第四步：粘贴到任意 AI 平台

提示片段格式为通用纯文本，适用于：

- **ChatGPT** → 自定义指令或第一条消息
- **Claude** → 项目知识或第一条消息
- **Gemini** → 第一条消息上下文
- **本地 LLM**（Ollama、LM Studio） → 系统提示词字段
- **Dify / Coze / FastGPT** → 系统提示词变量
- **API 调用** → system message 内容

---

## 备选方案：Universal JSON 导出

如需在 CapsuleMemory 实例之间程序化迁移：

1. 导出时选择 **"Universal"** 格式而非 "Prompt"
2. `.json` 文件遵循 `universal-memory/1.0` 架构
3. 在目标平台导入：
   ```bash
   capsule-memory import exported_file.json --user new_user
   ```

或通过 REST API：
```bash
curl -X POST http://target-server:8000/api/v1/capsules/import \
  -F "file=@exported_file.json" \
  -F "user_id=new_user"
```

---

## 使用建议

- **Prompt** 格式为复制粘贴优化，可读性好
- **Universal** 格式保留完整结构，适合程序化导入
- 提示片段通常 500-2000 字符，在任意平台的限制范围内
- 记忆上下文可优雅降级：即使是部分上下文也比没有强
