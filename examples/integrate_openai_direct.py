"""
Integration example: OpenAI + CapsuleMemory REST API (no SDK installation required).

This script demonstrates the "zero-dependency integration" pattern:
1. Recall relevant memories from the CapsuleMemory REST API
2. Inject the recalled context into OpenAI chat completion system prompt
3. Get a context-aware response

Prerequisites:
    - CapsuleMemory REST server running: capsule-memory serve --port 8000
    - OPENAI_API_KEY environment variable set
    - httpx installed: pip install httpx openai

Run:
    python examples/integrate_openai_direct.py
"""
from __future__ import annotations

import asyncio
import os

import httpx


CAPSULE_API_URL = os.getenv("CAPSULE_API_URL", "http://localhost:8000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
USER_ID = "demo_user"


async def recall_from_capsule(query: str) -> str:
    """
    Call the CapsuleMemory REST API to recall relevant memories.

    Args:
        query: The search query for memory recall.

    Returns:
        A prompt_injection string ready to be inserted into the system prompt.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{CAPSULE_API_URL}/api/v1/recall",
            params={"q": query, "user_id": USER_ID, "top_k": 3},
            timeout=10.0,
        )
        if resp.status_code != 200:
            print(f"[Warning] Recall API returned {resp.status_code}, using empty context")
            return ""
        data = resp.json()
        return data.get("prompt_injection", "")


async def chat_with_context(user_message: str, context: str) -> str:
    """
    Send a chat completion request to OpenAI with injected memory context.

    Args:
        user_message: The user's current question.
        context: Memory context from CapsuleMemory recall.

    Returns:
        The assistant's response text.
    """
    if not OPENAI_API_KEY:
        return "[DEMO MODE] OpenAI API key not set. In production, this would call GPT."

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant. "
                            "Use the following memory context if relevant:\n\n"
                            f"{context}"
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def main() -> None:
    print("=== CapsuleMemory + OpenAI Direct Integration ===\n")

    user_query = "How to optimize Django database queries?"

    # Step 1: Recall memories
    print(f"[1] Recalling memories for: '{user_query}'")
    context = await recall_from_capsule(user_query)
    if context:
        print(f"    Context found ({len(context)} chars)")
        print(f"    Preview: {context[:150]}...\n")
    else:
        print("    No context found (server may not be running)\n")

    # Step 2: Chat with context
    print(f"[2] Sending to OpenAI with injected context...")
    response = await chat_with_context(user_query, context)
    print(f"\n[Response]\n{response}")

    print("\n=== Integration demo complete ===")
    print("\nKey takeaway: Any platform can integrate with CapsuleMemory")
    print("by simply calling the REST API — no SDK installation required.")


if __name__ == "__main__":
    asyncio.run(main())
