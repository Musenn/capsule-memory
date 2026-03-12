# 💊 CapsuleMemory + Dify Integration Guide

> **English** | [中文](integrate_dify_zh.md)

## Overview

Integrate CapsuleMemory with Dify workflows and chatflows using HTTP Request nodes.
No SDK installation required — Dify calls the CapsuleMemory REST API directly.

## Prerequisites

1. CapsuleMemory REST server running:
   ```bash
   capsule-memory serve --port 8000
   ```
2. Dify instance accessible (cloud or self-hosted)

---

## Scenario 1: Dify Workflow Integration

### Step 1: Add HTTP Request Node for Memory Recall

In your Dify workflow editor, add an **HTTP Request** node before the LLM node.

**HTTP Request Configuration:**
```json
{
  "method": "GET",
  "url": "http://your-server:8000/api/v1/recall",
  "params": {
    "q": "{{#input.query#}}",
    "user_id": "{{#input.user_id#}}",
    "top_k": "3"
  },
  "headers": {
    "Authorization": "Bearer {{#env.CAPSULE_API_KEY#}}"
  },
  "timeout": 10
}
```

> Screenshot location: Dify workflow canvas showing HTTP Request node connected before LLM node

### Step 2: Variable Mapping

Map the HTTP response to the LLM node's system prompt:

| Source Variable | Target | Description |
|---|---|---|
| `http_response.body.prompt_injection` | LLM System Prompt (append) | Memory context block |
| `http_response.body.facts` | Optional context variable | Structured facts list |
| `http_response.body.sources` | Debug output | Source capsule IDs |

In the LLM node's system prompt, append:
```
{{#http_node.body.prompt_injection#}}
```

### Step 3: Add HTTP Request Node for Memory Ingestion (Optional)

After the LLM node, add another HTTP Request to save the interaction:

**Create Session (first call):**
```json
{
  "method": "POST",
  "url": "http://your-server:8000/api/v1/sessions",
  "params": {
    "user_id": "{{#input.user_id#}}"
  }
}
```

**Ingest Turn:**
```json
{
  "method": "POST",
  "url": "http://your-server:8000/api/v1/sessions/{{#session_node.body.session_id#}}/ingest",
  "body": {
    "user_message": "{{#input.query#}}",
    "assistant_response": "{{#llm_node.text#}}",
    "user_id": "{{#input.user_id#}}"
  }
}
```

---

## Scenario 2: Dify Chatflow Integration

### Step 1: Configure Conversation Variable

In your Chatflow settings, add a conversation variable `capsule_session_id` (type: string).

### Step 2: Pre-processing Hook

Add an HTTP Request node in the pre-processing flow:

```json
{
  "method": "GET",
  "url": "http://your-server:8000/api/v1/recall",
  "params": {
    "q": "{{#sys.query#}}",
    "user_id": "{{#sys.user_id#}}",
    "top_k": "3"
  }
}
```

### Step 3: System Prompt Template

In the LLM node, use this system prompt template:

```
You are a helpful assistant. Use the following memory context if relevant:

{{#pre_process.body.prompt_injection#}}

Answer the user's question based on this context and your knowledge.
```

### Step 4: Post-processing Hook (Save Memory)

Add an HTTP Request node in the post-processing flow to ingest the turn:

```json
{
  "method": "POST",
  "url": "http://your-server:8000/api/v1/sessions/{{#conversation.capsule_session_id#}}/ingest",
  "body": {
    "user_message": "{{#sys.query#}}",
    "assistant_response": "{{#llm.text#}}",
    "user_id": "{{#sys.user_id#}}"
  }
}
```

---

## Tips

- **Session Management**: Create one CapsuleMemory session per Dify conversation. Store the `session_id` in Dify's conversation variables.
- **Sealing**: Add a "seal" HTTP Request when the conversation ends or reaches a turn threshold.
- **Performance**: The recall API typically responds in < 100ms with LocalStorage. For production, consider SQLiteStorage for vector search.
- **Security**: Set `CAPSULE_API_KEY` on the server and pass it in Dify's HTTP headers.
