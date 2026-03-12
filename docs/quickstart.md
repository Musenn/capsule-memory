# Quick Start

> **English** | [中文](quickstart_zh.md)

## Installation

```bash
pip install capsule-memory
```

## Basic Usage

```python
import asyncio
from capsule_memory import CapsuleMemory

async def main():
    cm = CapsuleMemory()

    # Create a session and ingest conversation turns
    async with cm.session("user_123") as session:
        await session.ingest(
            "I'm building a web scraper with Python",
            "I recommend using httpx for async requests and selectolax for HTML parsing."
        )
        await session.ingest(
            "How to handle rate limiting?",
            "Use asyncio.Semaphore to limit concurrent requests, "
            "and add exponential backoff with tenacity."
        )
    # Session auto-seals on exit

    # List sealed capsules
    capsules = await cm.store.list(user_id="user_123")
    print(f"Capsules: {len(capsules)}")

    # Recall memories
    result = await cm.recall("web scraping best practices", user_id="user_123")
    print(result["prompt_injection"])

asyncio.run(main())
```

## Mock Mode (No API Key)

Set `CAPSULE_MOCK_EXTRACTOR=true` to use mock data extraction (no LLM calls):

```bash
CAPSULE_MOCK_EXTRACTOR=true python your_script.py
```

## Export and Import

```python
# Export to universal format (readable by any platform)
await cm.export_capsule(capsule_id, "memory.json", format="universal")

# Export as plain-text prompt snippet
await cm.export_capsule(capsule_id, "memory.txt", format="prompt")

# Import from file
imported = await cm.import_capsule("memory.json", user_id="new_user")
```

## CLI Usage

```bash
# List capsules
capsule-memory list --user user_123

# Show capsule details
capsule-memory show <capsule_id>

# Export capsule
capsule-memory export <capsule_id> output.json --format universal

# Recall memories
capsule-memory recall "web scraping" --user user_123

# Start REST API server
capsule-memory serve --port 8000

# Start MCP server
capsule-memory mcp
```
