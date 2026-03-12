"""
CapsuleMemory Interactive Demo — Run this script to see all features in action.

Usage:
    conda activate capsule-memory
    set CAPSULE_MOCK_EXTRACTOR=true
    python demo.py
"""
import asyncio
import sys
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import os
os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import tempfile
import shutil
from pathlib import Path
from datetime import datetime


def banner(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


async def main() -> None:
    # Use a temp directory for clean demo
    demo_dir = Path(tempfile.mkdtemp(prefix="capsule_demo_"))
    print(f"Demo storage: {demo_dir}")

    # ─── 1. Initialize CapsuleMemory ───────────────────────────────────
    banner("1. Initialize CapsuleMemory")
    from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig

    config = CapsuleMemoryConfig(storage_path=str(demo_dir), storage_type="local")
    cm = CapsuleMemory(config=config)
    print("[OK] CapsuleMemory initialized")
    print(f"     Storage type: local")
    print(f"     Path: {demo_dir}")

    # ─── 2. Create Session & Ingest Conversations ─────────────────────
    banner("2. Create Session & Ingest Conversation Turns")

    # Each turn is a (user_message, assistant_response) pair
    turns = [
        ("How do I set up a Python virtual environment?",
         "Use `python -m venv myenv` to create one, then activate with `source myenv/bin/activate` on Linux/Mac or `myenv\\Scripts\\activate` on Windows."),
        ("What about conda?",
         "With conda: `conda create -n myenv python=3.11` then `conda activate myenv`. Conda also manages non-Python packages."),
        ("How do I install packages in a venv?",
         "Use `pip install package_name` while the venv is active. For reproducibility, use `pip freeze > requirements.txt`."),
    ]

    async with cm.session(user_id="alice", session_id="demo-session-001") as session:
        print(f"[OK] Session created: {session.config.session_id}")
        for user_msg, ai_resp in turns:
            await session.ingest(user_msg, ai_resp)
            print(f"     Ingested: {user_msg[:55]}...")
        print(f"[OK] {len(turns)} turn pairs ingested")

        # ─── 3. Seal Session → Create Capsule ──────────────────────────
        banner("3. Seal Session -> Create Memory Capsule")
        capsule = await session.seal()
        print(f"[OK] Capsule created!")
        print(f"     ID:    {capsule.capsule_id}")
        print(f"     Type:  {capsule.capsule_type.value}")
        print(f"     Title: {capsule.metadata.title}")
        print(f"     Tags:  {capsule.metadata.tags}")
        print(f"     Turns: {capsule.metadata.turn_count}")
        print(f"     Status: {capsule.lifecycle.status.value}")

    # ─── 4. Create a second capsule ────────────────────────────────────
    banner("4. Create a Second Capsule (Different Topic)")
    turns2 = [
        ("Explain Docker containers vs virtual machines",
         "Docker containers share the host OS kernel and are lightweight. VMs include a full OS and are heavier but more isolated."),
        ("When should I use each?",
         "Use containers for microservices and CI/CD. Use VMs when you need full OS isolation or run different OS kernels."),
    ]
    async with cm.session(user_id="alice", session_id="demo-session-002") as session2:
        for user_msg, ai_resp in turns2:
            await session2.ingest(user_msg, ai_resp)
        capsule2 = await session2.seal()
    print(f"[OK] Capsule 2: {capsule2.capsule_id}")
    print(f"     Title: {capsule2.metadata.title}")

    # ─── 5. List Capsules ──────────────────────────────────────────────
    banner("5. List All Capsules")
    from capsule_memory.storage.local import LocalStorage
    storage = LocalStorage(path=str(demo_dir))
    all_capsules = await storage.list(user_id="alice")
    print(f"[OK] Found {len(all_capsules)} capsules for user 'alice':")
    for i, c in enumerate(all_capsules, 1):
        print(f"     {i}. [{c.capsule_type.value}] {c.metadata.title} (id: {c.capsule_id[:20]}...)")

    # ─── 6. Search Capsules ────────────────────────────────────────────
    banner("6. Search Capsules by Keyword")
    results = await storage.search("Python", user_id="alice")
    print(f'[OK] Search "Python" -> {len(results)} results:')
    for c, score in results:
        print(f"     - {c.metadata.title} (score: {score:.2f})")

    results2 = await storage.search("Docker", user_id="alice")
    print(f'[OK] Search "Docker" -> {len(results2)} results:')
    for c, score in results2:
        print(f"     - {c.metadata.title} (score: {score:.2f})")

    # ─── 7. Get Capsule Details ────────────────────────────────────────
    banner("7. Get Capsule Details")
    retrieved = await storage.get(capsule.capsule_id)
    if retrieved:
        print(f"[OK] Retrieved capsule: {retrieved.capsule_id}")
        print(f"     Title: {retrieved.metadata.title}")
        print(f"     Payload keys: {list(retrieved.payload.keys())}")
        summary = retrieved.payload.get("context_summary", "N/A")
        print(f"     Summary: {summary[:100]}...")

    # ─── 8. Merge Capsules ─────────────────────────────────────────────
    banner("8. Merge Two Capsules")
    from capsule_memory.core.store import CapsuleStore
    store = CapsuleStore(storage)
    merged = await store.merge([capsule.capsule_id, capsule2.capsule_id])
    print(f"[OK] Merged capsule: {merged.capsule_id}")
    print(f"     Type:  {merged.capsule_type.value}")
    print(f"     Title: {merged.metadata.title}")
    print(f"     Tags:  {merged.metadata.tags}")

    # ─── 9. Fork Capsule ───────────────────────────────────────────────
    banner("9. Fork a Capsule for Another User")
    forked = await store.fork(capsule.capsule_id, new_user_id="bob")
    print(f"[OK] Forked capsule: {forked.capsule_id}")
    print(f"     Original user: alice -> New user: {forked.identity.user_id}")
    print(f"     Title: {forked.metadata.title}")

    # ─── 10. Diff Capsules ─────────────────────────────────────────────
    banner("10. Diff Two Capsules")
    diff = await store.diff(capsule.capsule_id, capsule2.capsule_id)
    print(f"[OK] Diff result:")
    print(f"     Keys: {list(diff.keys())}")
    print(f"     Added facts:    {len(diff.get('added_facts', []))}")
    print(f"     Removed facts:  {len(diff.get('removed_facts', []))}")
    print(f"     Modified facts: {len(diff.get('modified_facts', []))}")
    print(f"     Summary changed: {diff.get('summary_changed', 'N/A')}")

    # ─── 11. Export Capsule ────────────────────────────────────────────
    banner("11. Export Capsule to JSON File")
    export_path = str(demo_dir / "exported_capsule.json")
    result_path = await storage.export_capsule(
        capsule.capsule_id, export_path, format="json"
    )
    file_size = os.path.getsize(result_path)
    print(f"[OK] Exported to: {result_path}")
    print(f"     File size: {file_size} bytes")

    # ─── 12. Export with Encryption ────────────────────────────────────
    banner("12. Export with AES-256 Encryption")
    enc_path = str(demo_dir / "encrypted_capsule.enc")
    enc_result = await storage.export_capsule(
        capsule.capsule_id, enc_path, format="json",
        encrypt=True, passphrase="my-secret-key-123"
    )
    enc_size = os.path.getsize(enc_result)
    print(f"[OK] Encrypted export: {enc_result}")
    print(f"     File size: {enc_size} bytes (encrypted)")

    # ─── 13. Import Capsule ────────────────────────────────────────────
    banner("13. Import Capsule from File")
    imported = await storage.import_capsule_file(export_path, user_id="charlie")
    print(f"[OK] Imported capsule: {imported.capsule_id}")
    print(f"     User: {imported.identity.user_id}")
    print(f"     Title: {imported.metadata.title}")

    # ─── 14. Recall Memory Context ─────────────────────────────────────
    banner("14. Recall Memory Context (for prompt injection)")
    context = await store.get_context_for_injection(
        query="how to set up python", user_id="alice"
    )
    print(f"[OK] Context for prompt injection:")
    print(f"     Keys: {list(context.keys())}")
    print(f"     Facts: {len(context.get('facts', []))}")
    print(f"     Skills: {len(context.get('skills', []))}")
    print(f"     Sources: {len(context.get('sources', []))}")
    injection = context.get("prompt_injection", "")
    if injection:
        print(f"     Prompt injection preview:")
        for line in str(injection).split("\n")[:5]:
            print(f"       {line}")
    else:
        print(f"     (No matching memories found for this query)")

    # ─── 15. Count Capsules ────────────────────────────────────────────
    banner("15. Final Statistics")
    alice_count = await storage.count(user_id="alice")
    bob_count = await storage.count(user_id="bob")
    charlie_count = await storage.count(user_id="charlie")
    total = await storage.count()
    print(f"[OK] Capsule counts:")
    print(f"     alice:   {alice_count}")
    print(f"     bob:     {bob_count}")
    print(f"     charlie: {charlie_count}")
    print(f"     total:   {total}")

    # ─── 16. Serialization Formats ─────────────────────────────────────
    banner("16. Serialization Formats")
    from capsule_memory.transport.serializer import CapsuleSerializer

    json_data = CapsuleSerializer.to_json(capsule)
    msgpack_data = CapsuleSerializer.to_msgpack(capsule)
    print(f"[OK] JSON size:    {len(json_data)} bytes")
    print(f"[OK] MsgPack size: {len(msgpack_data)} bytes")
    print(f"     Compression:  {100 - len(msgpack_data)*100//len(json_data)}% smaller")

    # Roundtrip
    restored = CapsuleSerializer.from_msgpack(msgpack_data)
    assert restored.capsule_id == capsule.capsule_id
    print(f"[OK] MsgPack roundtrip: verified")

    # ─── Cleanup ───────────────────────────────────────────────────────
    banner("DEMO COMPLETE")
    print(f"All 16 features demonstrated successfully!")
    print()
    print("Next steps for interactive testing:")
    print("  1. REST API with Swagger UI:")
    print("     conda activate capsule-memory")
    print("     set CAPSULE_MOCK_EXTRACTOR=true")
    print("     python -m capsule_memory.cli serve --port 9100")
    print("     Then open: http://localhost:9100/docs")
    print()
    print("  2. CLI commands:")
    print(f"     python -m capsule_memory.cli --storage {demo_dir} list")
    print(f"     python -m capsule_memory.cli --storage {demo_dir} show <capsule_id>")
    print(f"     python -m capsule_memory.cli --storage {demo_dir} recall \"python venv\"")
    print()
    print(f"Demo data saved at: {demo_dir}")
    print("(You can delete it when done)")


if __name__ == "__main__":
    asyncio.run(main())
