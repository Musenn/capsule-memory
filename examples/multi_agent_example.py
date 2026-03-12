"""
Multi-Agent shared memory demo using CapsuleMemory.

Scenario:
- Agent A (analyst) completes data analysis and seals memory
- Agent B (developer) inherits Agent A's memory via fork, continues work
- Uses LocalStorage (production can swap for RedisStorage for real-time broadcast)

Run:
    CAPSULE_MOCK_EXTRACTOR=true python examples/multi_agent_example.py

On Windows:
    set CAPSULE_MOCK_EXTRACTOR=true && python examples/multi_agent_example.py
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from capsule_memory import CapsuleMemory
from capsule_memory.storage.local import LocalStorage


async def main() -> None:
    storage_path = os.path.join(tempfile.gettempdir(), "multi_agent_demo")
    storage = LocalStorage(path=storage_path)
    cm_a = CapsuleMemory(storage=storage, on_skill_trigger=lambda e: None)
    cm_b = CapsuleMemory(storage=storage, on_skill_trigger=lambda e: None)

    # ── Agent A: Analyst ──────────────────────────────────────────────────
    print("=== Agent A: Analyst ===")
    async with cm_a.session("agent_a", origin_platform="analysis_agent") as session_a:
        await session_a.ingest(
            "Analyze user growth data",
            "Over the past 30 days, 12K new users were added, a 23% month-over-month increase. "
            "Primary source is social media channels.",
        )
        await session_a.ingest(
            "What are the key metrics?",
            "Retention rate (Day7: 45%) and paid conversion rate (3.2%) are the key north star metrics.",
        )
        await asyncio.sleep(0.1)

    capsules_a = await cm_a.store.list(user_id="agent_a")
    assert len(capsules_a) > 0, "Agent A failed to seal capsule"
    capsule_a = capsules_a[0]
    print(f"  Agent A sealed capsule: {capsule_a.capsule_id}")
    print(f"  Type: {capsule_a.capsule_type.value}")
    print(f"  Turns: {capsule_a.metadata.turn_count}")

    # ── Fork capsule to Agent B ───────────────────────────────────────────
    print("\n=== Fork Memory to Agent B ===")
    forked = await cm_a.store.fork(
        capsule_a.capsule_id,
        new_user_id="agent_b",
        new_agent_id="dev_agent",
        additional_tags=["forked", "from_analyst"],
    )
    print(f"  Forked capsule: {forked.capsule_id}")
    print(f"  Forked from: {forked.metadata.forked_from}")
    print(f"  New user: {forked.identity.user_id}")
    print(f"  New agent: {forked.identity.agent_id}")

    # ── Agent B: Developer ────────────────────────────────────────────────
    print("\n=== Agent B: Developer ===")

    # Recall Agent A's memory
    recall = await cm_b.recall("user growth analysis results", user_id="agent_b")
    print(f"  Recalled context ({len(recall['facts'])} facts, {len(recall['sources'])} sources):")
    if recall["prompt_injection"]:
        # Print first 200 chars of prompt injection
        preview = recall["prompt_injection"][:200]
        print(f"  {preview}...")

    # Agent B continues work with inherited context
    async with cm_b.session("agent_b", origin_platform="dev_agent") as session_b:
        await session_b.ingest(
            "Based on the analysis results, what should we do?",
            "Need to optimize Day7 retention rate. Recommendations:\n"
            "1. Add onboarding tutorial flow\n"
            "2. Push personalized content\n"
            "3. Implement re-engagement notifications",
        )
        await asyncio.sleep(0.1)

    # ── Verify both agents' capsules exist ────────────────────────────────
    print("\n=== Verification ===")
    capsules_b = await cm_b.store.list(user_id="agent_b")
    assert len(capsules_b) >= 2, f"Expected >= 2 capsules for agent_b, got {len(capsules_b)}"
    print(f"  Agent A capsules: {len(capsules_a)}")
    print(f"  Agent B capsules: {len(capsules_b)} (1 forked + 1 own)")

    # Verify diff between original and forked
    diff = await cm_a.store.diff(capsule_a.capsule_id, forked.capsule_id)
    print(f"  Diff summary_changed: {diff['summary_changed']}")

    # Verify merge works
    if len(capsules_b) >= 2:
        merged = await cm_b.store.merge(
            [c.capsule_id for c in capsules_b[:2]],
            title="Agent B Merged Knowledge",
        )
        print(f"  Merged capsule: {merged.capsule_id}")
        print(f"  Merged type: {merged.capsule_type.value}")

    print("\n=== All steps passed! ===")


if __name__ == "__main__":
    os.environ.setdefault("CAPSULE_MOCK_EXTRACTOR", "true")
    asyncio.run(main())
