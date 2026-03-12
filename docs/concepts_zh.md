# 核心概念

> [English](concepts.md) | **中文**

## 胶囊类型

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `MEMORY` | 提炼后的对话事实与上下文 | 通用会话历史 |
| `SKILL` | 可复用的技术方案或操作流程 | 代码模式、工作流 |
| `HYBRID` | 记忆 + 技能的组合 | 包含事实和技能的复杂会话 |
| `CONTEXT` | 纯文本上下文（外部导入） | 外部知识注入 |

## 会话生命周期

```
1. 创建会话  →  cm.session("user_id")
2. 录入轮次  →  session.ingest(user_msg, ai_response)
3. 技能检测  →  后台：每轮检查 4 条规则
4. 封存      →  session.seal() 或退出上下文时自动封存
5. 持久化    →  胶囊写入存储后端
```

## 胶囊状态

- **DRAFT** — 会话进行中，尚未封存
- **SEALED** — 已完成封存并持久化，已计算校验和
- **IMPORTED** — 从外部来源导入或从其他胶囊 Fork
- **ARCHIVED** — 软删除，保留用于审计

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

## 存储后端

| 后端 | 搜索方式 | 适用场景 |
|------|----------|----------|
| LocalStorage | 关键词匹配 | 开发环境、单用户 |
| SQLiteStorage | 向量搜索 (384维) | 生产环境、本地部署 |
| RedisStorage | 关键词匹配 | 多服务、实时场景 |
| QdrantStorage | 向量搜索 (384维) | 生产环境、可水平扩展 |

## 协议归属

每个胶囊均携带归属元数据：
- `schema_version`: `capsule-schema/1.0+35c1b411`
- `capsule_id`: 前缀包含协议指纹
- `checksum`: 基于协议密钥材料的 HMAC-SHA256
- `metadata.capsule_created_by`: `capsule-memory`
- `metadata.capsule_project_url`: GitHub 仓库地址
