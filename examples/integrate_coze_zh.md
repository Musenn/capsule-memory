# 💊 CapsuleMemory + Coze Bot 集成指南

> [English](integrate_coze.md) | **中文**

## 概述

通过 Coze 插件系统将 CapsuleMemory 与 Coze Bot 集成，以调用 CapsuleMemory REST API 作为外部 HTTP 接口。

## 前置条件

1. CapsuleMemory REST 服务已运行并可从公网访问：
   ```bash
   capsule-memory serve --port 8000 --host 0.0.0.0
   ```
2. 拥有 Coze 账号且具备创建 Bot 的权限

---

## 第一步：在 Coze 中创建自定义插件

1. 前往 **Coze 插件商店** → **创建插件**
2. 选择 **API 插件** 类型
3. 配置插件：

**插件名称：** `CapsuleMemory`
**描述：** `召回与管理 AI 记忆胶囊`
**基础 URL：** `http://your-server:8000`

### API 端点：召回记忆

**方法：** GET
**路径：** `/api/v1/recall`
**参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 记忆召回的搜索查询 |
| user_id | string | 否 | 用户标识（默认 "default"） |
| top_k | integer | 否 | 返回结果数量（默认 3） |

**请求头：**
```
Authorization: Bearer YOUR_CAPSULE_API_KEY
```

**响应格式：**
```json
{
  "facts": [{"key": "string", "value": "string"}],
  "skills": [{"name": "string", "description": "string"}],
  "summary": "string",
  "prompt_injection": "string",
  "sources": ["string"]
}
```

### API 端点：列出胶囊

**方法：** GET
**路径：** `/api/v1/capsules`
**参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 否 | 按用户 ID 过滤 |
| type | string | 否 | 按类型过滤：memory, skill, hybrid, context |
| limit | integer | 否 | 最大结果数（默认 20） |

---

## 第二步：配置 Bot 使用插件

1. 打开 Coze Bot 设置
2. 进入 **插件** → 添加 `CapsuleMemory` 插件
3. 在 Bot 的 **系统提示词** 中添加：

```
你可以使用 CapsuleMemory 插件来召回历史对话上下文。

当用户提问时：
1. 先用用户的问题作为查询调用 CapsuleMemory recall API
2. 如果找到相关记忆，使用 prompt_injection 字段作为额外上下文
3. 将召回的上下文自然地融入你的回复

当用户要求保存某些内容或你检测到有价值的信息时：
- 告知用户该信息将被记住，可在后续会话中使用
```

## 第三步：Bot 工作流配置

### 自动记忆召回流程

在 Coze Bot 工作流编辑器中：

1. **触发器：** 用户发送消息
2. **动作 1：** 调用 CapsuleMemory `recall` API
   - 输入：`q` = 用户消息
   - 输入：`user_id` = 会话用户 ID
3. **条件：** 检查 `prompt_injection` 是否非空
4. **动作 2：** 将 `prompt_injection` 传给 LLM 作为额外系统上下文
5. **动作 3：** 生成带有记忆增强上下文的回复

---

## 使用建议

- **公网访问**：确保 CapsuleMemory 服务可被 Coze 服务器访问。使用反向代理（nginx）或云部署。
- **认证**：生产部署务必设置 `CAPSULE_API_KEY`。
- **用户映射**：将 Coze 用户 ID 映射到 CapsuleMemory 用户 ID，实现按用户隔离记忆。
- **限流**：REST API 可处理并发请求，但公共 Bot 建议增加限流。
