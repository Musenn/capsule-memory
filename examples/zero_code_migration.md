# Zero-Code Memory Migration Guide

> **English** | [中文](zero_code_migration_zh.md)

## Overview

Migrate your AI conversation memories between platforms without writing any code.
Uses the CapsuleMemory Widget export feature and plain-text prompt snippets.

---

## Step 1: Export from CapsuleMemory Widget

1. Open the page where the CapsuleMemory Widget is embedded
2. Click the **capsule icon** to open the capsule list panel
3. Find the capsule you want to migrate
4. Click the **Export** button on the capsule card
5. Select **"Prompt"** format from the dropdown

> Screenshot location: Widget panel showing capsule list with Export button highlighted

6. A `.txt` file downloads containing a plain-text prompt snippet like:

```
=== Memory Context ===
[Source: quickstart | Time: 2025-03-10 14:30]
[Topic: Django Query Optimization]

Background: Discussion about optimizing Django ORM queries...

Key Facts:
  - user.lang: Python
  - framework: Django
  - optimization: prefetch_related for M2M, select_related for FK

Available Skills:
  [Django N+1 Fix] Use prefetch_related to eliminate N+1 queries
    Trigger: when user reports slow database queries
    Instructions: Add prefetch_related('related_model') to queryset...

=== Memory Context End ===
```

---

## Step 2: Paste into ChatGPT

1. Open **ChatGPT** (chat.openai.com)
2. Click on your conversation or start a new one
3. Click **"Custom Instructions"** or **"System Prompt"** (if using API playground)
4. Paste the exported prompt snippet into the system instructions field
5. ChatGPT now has your historical context for this conversation

> Screenshot location: ChatGPT custom instructions dialog with pasted memory context

---

## Step 3: Paste into Claude

1. Open **Claude** (claude.ai)
2. Start a new conversation
3. In your first message, paste the prompt snippet and prefix it with:

```
Please use the following context from a previous conversation session:

[paste the exported prompt snippet here]

Now, continuing from this context: [your new question]
```

> Screenshot location: Claude conversation with pasted memory context as first message

---

## Step 4: Paste into Any AI Platform

The prompt snippet format is universal plain text. It works with:

- **ChatGPT** → Custom Instructions or first message
- **Claude** → Project Knowledge or first message
- **Gemini** → First message context
- **Local LLMs** (Ollama, LM Studio) → System prompt field
- **Dify / Coze / FastGPT** → System prompt variable
- **API calls** → system message content

---

## Alternative: Universal JSON Export

For programmatic migration between CapsuleMemory instances:

1. Export using **"Universal"** format instead of "Prompt"
2. The `.json` file follows the `universal-memory/1.0` schema
3. Import on the target platform:
   ```bash
   capsule-memory import exported_file.json --user new_user
   ```

Or via REST API:
```bash
curl -X POST http://target-server:8000/api/v1/capsules/import \
  -F "file=@exported_file.json" \
  -F "user_id=new_user"
```

---

## Tips

- The **Prompt** format is optimized for copy-paste readability
- The **Universal** format preserves full structure for programmatic import
- Prompt snippets are typically 500-2000 characters — well within any platform's limit
- Memory context degrades gracefully: even partial context is better than none
