"""
CapsuleMemory Quick Start Example (uses Mock mode, no API Key required)

Run:
    CAPSULE_MOCK_EXTRACTOR=true python examples/quickstart_claude.py

On Windows:
    set CAPSULE_MOCK_EXTRACTOR=true && python examples/quickstart_claude.py
"""
from __future__ import annotations
import asyncio, os, json, tempfile
from pathlib import Path
from capsule_memory import CapsuleMemory

MOCK_TURNS = [
    ("I'm building an e-commerce backend with Django",
     "Great choice! Django is excellent for e-commerce projects. What issues are you facing?"),
    ("My queries are slow, loading user orders takes forever",
     "This is typically an N+1 query problem. Solution:\n```python\n"
     "# Use prefetch_related\nusers = User.objects.prefetch_related('orders').all()\n```\n"
     "This reduces N+1 queries to just 2 SQL queries."),
    ("Awesome, this method works great!",
     "Glad to help! prefetch_related is one of the most common Django performance optimizations."),
    ("How about ForeignKey optimization?",
     "ForeignKey uses select_related:\n```python\n"
     "# 1. ForeignKey/OneToOne -> select_related\n"
     "orders = Order.objects.select_related('user', 'product').all()\n"
     "# 2. ManyToMany/reverse FK -> prefetch_related\n```"),
    ("Got it, thanks!",
     "You're welcome! Mastering these two methods solves most Django performance issues."),
]


async def main() -> None:
    storage_path = os.path.join(tempfile.gettempdir(), "capsule_quickstart_test")
    trigger_events = []

    def on_trigger(event):
        trigger_events.append(event)
        print(f"\n[Trigger] Detected reusable skill: {event.skill_draft.suggested_name} "
              f"(confidence: {event.skill_draft.confidence:.0%})")

    cm = CapsuleMemory(
        storage=__import__("capsule_memory.storage.local", fromlist=["LocalStorage"]).LocalStorage(storage_path),
        on_skill_trigger=on_trigger,
    )

    print("=== Step 1: Create Session and Ingest Conversation ===")
    async with cm.session("demo_user", origin_platform="quickstart") as session:
        for user_msg, ai_msg in MOCK_TURNS:
            turn = await session.ingest(user_msg, ai_msg)
            print(f"  Turn {turn.turn_id}: {user_msg[:40]}...")
        await asyncio.sleep(0.1)  # Wait for background detection tasks
        snap = await session.snapshot()
        print(f"\n  Snapshot: {snap}")

    print("\n=== Step 2: List Sealed Capsules ===")
    capsules = await cm.store.list(user_id="demo_user")
    assert len(capsules) > 0, "Seal failed, no capsules found"
    capsule = capsules[0]
    print(f"  Capsule ID: {capsule.capsule_id}")
    print(f"  Type: {capsule.capsule_type.value}")
    print(f"  Turn Count: {capsule.metadata.turn_count}")

    print("\n=== Step 3: Export to Universal Format ===")
    export_path = os.path.join(tempfile.gettempdir(), f"capsule_demo_{capsule.capsule_id}.json")
    await cm.export_capsule(capsule.capsule_id, export_path, format="universal")
    universal = json.loads(Path(export_path).read_text())
    print(f"  Exported to: {export_path}")
    print(f"  Facts count: {len(universal['facts'])}")
    print(f"  Skills count: {len(universal['skills'])}")
    print(f"\n  prompt_injection preview:\n{universal['prompt_injection'][:300]}...")

    print("\n=== Step 4: Recall Memory ===")
    recall = await cm.recall("Django query optimization", user_id="demo_user")
    assert "prompt_injection" in recall
    print(f"  Recalled {len(recall['facts'])} facts")
    print(f"  prompt_injection available: {'yes' if recall['prompt_injection'] else 'no'}")

    print("\n=== All steps passed! ===")


if __name__ == "__main__":
    os.environ.setdefault("CAPSULE_MOCK_EXTRACTOR", "true")
    asyncio.run(main())
