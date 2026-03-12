# 💊 CapsuleMemory + Coze Bot Integration Guide

> **English** | [中文](integrate_coze_zh.md)

## Overview

Integrate CapsuleMemory with Coze bots using the Coze Plugin system
to call the CapsuleMemory REST API as an external HTTP API.

## Prerequisites

1. CapsuleMemory REST server running and accessible from the internet:
   ```bash
   capsule-memory serve --port 8000 --host 0.0.0.0
   ```
2. A Coze account with bot creation permissions

---

## Step 1: Create a Custom Plugin in Coze

1. Go to **Coze Plugin Store** → **Create Plugin**
2. Select **API Plugin** type
3. Configure the plugin:

**Plugin Name:** `CapsuleMemory`
**Description:** `Recall and manage AI memory capsules`
**Base URL:** `http://your-server:8000`

### API Endpoint: Recall Memories

**Method:** GET
**Path:** `/api/v1/recall`
**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| q | string | Yes | Search query for memory recall |
| user_id | string | No | User identifier (default: "default") |
| top_k | integer | No | Number of results (default: 3) |

**Headers:**
```
Authorization: Bearer YOUR_CAPSULE_API_KEY
```

**Response Schema:**
```json
{
  "facts": [{"key": "string", "value": "string"}],
  "skills": [{"name": "string", "description": "string"}],
  "summary": "string",
  "prompt_injection": "string",
  "sources": ["string"]
}
```

### API Endpoint: List Capsules

**Method:** GET
**Path:** `/api/v1/capsules`
**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| user_id | string | No | Filter by user ID |
| type | string | No | Filter by type: memory, skill, hybrid, context |
| limit | integer | No | Max results (default: 20) |

---

## Step 2: Configure Bot to Use the Plugin

1. Open your Coze Bot settings
2. Go to **Plugins** → Add the `CapsuleMemory` plugin
3. In the bot's **System Prompt**, add:

```
You have access to the CapsuleMemory plugin for recalling past conversation context.

When the user asks a question:
1. First call the CapsuleMemory recall API with the user's question as the query
2. If relevant memories are found, use the prompt_injection field as additional context
3. Incorporate the recalled context naturally into your response

When the user asks to save something or you detect valuable information:
- Mention that the information will be remembered for future sessions
```

## Step 3: Bot Workflow Configuration

### Automatic Memory Recall Flow

In the Coze Bot workflow editor:

1. **Trigger:** User sends a message
2. **Action 1:** Call CapsuleMemory `recall` API
   - Input: `q` = user's message
   - Input: `user_id` = conversation user ID
3. **Condition:** Check if `prompt_injection` is non-empty
4. **Action 2:** Pass `prompt_injection` to LLM as additional system context
5. **Action 3:** Generate response with memory-augmented context

---

## Tips

- **Public Access**: Ensure your CapsuleMemory server is accessible from Coze's servers. Use a reverse proxy (nginx) or cloud deployment.
- **Authentication**: Always set `CAPSULE_API_KEY` for production deployments.
- **User Mapping**: Map Coze user IDs to CapsuleMemory user IDs for per-user memory isolation.
- **Rate Limiting**: The REST API handles concurrent requests, but consider rate limiting for public bots.
