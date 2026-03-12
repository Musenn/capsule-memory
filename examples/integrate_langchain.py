"""
Integration example: LangChain + CapsuleMemory.

Demonstrates CapsuleMemoryLangChainMemory as a drop-in replacement
for ConversationBufferMemory.

Prerequisites:
    - pip install capsule-memory langchain langchain-openai
    - OPENAI_API_KEY environment variable set (or CAPSULE_MOCK_EXTRACTOR=true)

Run:
    CAPSULE_MOCK_EXTRACTOR=true python examples/integrate_langchain.py
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from capsule_memory import CapsuleMemory
from capsule_memory.adapters.langchain import CapsuleMemoryLangChainMemory
from capsule_memory.storage.local import LocalStorage


async def main() -> None:
    storage_path = os.path.join(tempfile.gettempdir(), "langchain_demo")
    storage = LocalStorage(path=storage_path)
    cm = CapsuleMemory(storage=storage, on_skill_trigger=lambda e: None)

    print("=== CapsuleMemory + LangChain Integration ===\n")

    # Step 1: Create CapsuleMemory-backed memory
    memory = CapsuleMemoryLangChainMemory(
        cm=cm,
        user_id="langchain_user",
        memory_key="history",
    )
    print("[1] Created CapsuleMemoryLangChainMemory")
    print(f"    memory_key: {memory.memory_key}")
    print(f"    memory_variables: {memory.memory_variables}")

    # Step 2: Simulate LangChain chain interactions
    print("\n[2] Simulating chain interactions (save_context)...")

    interactions = [
        (
            {"input": "What's the best way to handle authentication in Django?"},
            {"output": "Use Django's built-in auth system with django-allauth for social login."},
        ),
        (
            {"input": "How about JWT tokens?"},
            {"output": "Use djangorestframework-simplejwt for JWT. Set ACCESS_TOKEN_LIFETIME."},
        ),
        (
            {"input": "What about session security?"},
            {"output": "Enable CSRF protection, use HTTPS, set SESSION_COOKIE_SECURE=True."},
        ),
    ]

    for inputs, outputs in interactions:
        memory.save_context(inputs, outputs)
        print(f"    Saved: {inputs['input'][:50]}...")

    # Step 3: Load memory variables (recall)
    print("\n[3] Loading memory variables (recall)...")
    variables = memory.load_memory_variables({"input": "Django authentication"})
    history = variables.get("history", "")
    print(f"    Recalled {len(history)} chars of context")
    if history:
        print(f"    Preview: {history[:150]}...")

    # Step 4: Seal the session
    print("\n[4] Sealing session into capsule...")
    memory.seal(title="Django Auth Discussion", tags=["django", "auth"])

    # Step 5: Verify capsule was created
    capsules = await cm.store.list(user_id="langchain_user")
    print(f"    Capsules created: {len(capsules)}")
    if capsules:
        c = capsules[0]
        print(f"    ID: {c.capsule_id}")
        print(f"    Title: {c.metadata.title}")
        print(f"    Turns: {c.metadata.turn_count}")

    # Step 6: Clear and verify fresh state
    print("\n[5] Clearing memory (fresh session)...")
    memory.clear()
    variables_after_clear = memory.load_memory_variables({"input": "Django"})
    print(f"    Context after clear: {len(variables_after_clear.get('history', ''))} chars")

    # Step 7: Recall from sealed capsule (cross-session)
    print("\n[6] Recalling from sealed capsule (cross-session)...")
    recall = await cm.recall("Django authentication", user_id="langchain_user")
    print(f"    Facts: {len(recall.get('facts', []))}")
    print(f"    Sources: {len(recall.get('sources', []))}")
    if recall.get("prompt_injection"):
        print(f"    Injection: {recall['prompt_injection'][:100]}...")

    print("\n=== Integration demo complete ===")


if __name__ == "__main__":
    os.environ.setdefault("CAPSULE_MOCK_EXTRACTOR", "true")
    asyncio.run(main())
