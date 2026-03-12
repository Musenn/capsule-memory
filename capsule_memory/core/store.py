from __future__ import annotations
import builtins
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from capsule_memory.exceptions import CapsuleNotFoundError, StorageError
from capsule_memory.models.capsule import (
    Capsule, CapsuleIdentity, CapsuleLifecycle, CapsuleMetadata,
    CapsuleStatus, CapsuleType,
)
from capsule_memory.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class CapsuleStore:
    """
    High-level operations interface for CapsuleMemory: merge, diff, fork, list, get_context_for_injection.
    All write operations go through BaseStorage for backend-agnostic persistence.
    """

    def __init__(self, storage: BaseStorage) -> None:
        self._storage = storage

    # ─── Basic read/write proxies ─────────────────────────────────────────────

    async def save(self, capsule: Capsule) -> str:
        """Save a capsule, return capsule_id."""
        return await self._storage.save(capsule)

    async def list(
        self,
        user_id: str | None = None,
        capsule_type: CapsuleType | None = None,
        tags: builtins.list[str] | None = None,
        status: CapsuleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Capsule]:
        """List capsules, proxy to storage.list()."""
        return await self._storage.list(
            user_id=user_id,
            capsule_type=capsule_type,
            tags=tags,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get(self, capsule_id: str) -> Capsule:
        """
        Get a capsule, raises CapsuleNotFoundError if not found.

        Args:
            capsule_id: Capsule unique ID.

        Returns:
            The corresponding Capsule object.

        Raises:
            CapsuleNotFoundError: When no capsule with the given ID exists.
        """
        capsule = await self._storage.get(capsule_id)
        if capsule is None:
            raise CapsuleNotFoundError(capsule_id)
        return capsule

    async def delete(self, capsule_id: str) -> bool:
        """Delete a capsule by ID, return True if deleted."""
        return await self._storage.delete(capsule_id)

    # ─── Core high-level operations ───────────────────────────────────────────

    async def merge(
        self,
        capsule_ids: builtins.list[str],
        title: str = "",
        tags: builtins.list[str] | None = None,
        user_id: str | None = None,
    ) -> Capsule:
        """
        Merge multiple capsules into a new HYBRID or MEMORY capsule.

        Merge rules:
        - facts: Deduplicate by key across all sources, keep highest confidence
        - skills: Deduplicate by skill_name, keep the latest
        - context_summary: Concatenate all sources, separated by newlines
        - tags: Merge and deduplicate all source tags and input tags
        - turn_count: Sum

        Args:
            capsule_ids: List of capsule IDs to merge, at least 2.
            title: New capsule title, defaults to "Merged: {first source ID prefix}".
            tags: Additional tags.
            user_id: New capsule owner, defaults to first source's user_id.

        Returns:
            The merged new Capsule (persisted).

        Raises:
            CapsuleNotFoundError: Any capsule_id not found.
            StorageError: Fewer than 2 capsule_ids.
        """
        if len(capsule_ids) < 2:
            raise StorageError("merge() requires at least 2 capsule_ids")

        sources: builtins.list[Capsule] = []
        for cid in capsule_ids:
            sources.append(await self.get(cid))

        target_user_id = user_id or sources[0].identity.user_id

        # ── Aggregate facts (deduplicate by key, keep highest confidence)
        facts_by_key: dict[str, Any] = {}
        for capsule in sources:
            raw_facts = self._extract_facts(capsule)
            for f in raw_facts:
                key = f.get("key", "") if isinstance(f, dict) else getattr(f, "key", "")
                conf = (
                    f.get("confidence", 0.0)
                    if isinstance(f, dict) else getattr(f, "confidence", 0.0)
                )
                existing = facts_by_key.get(key)
                existing_conf = (
                    existing.get("confidence", 0.0)
                    if isinstance(existing, dict)
                    else (getattr(existing, "confidence", 0.0) if existing else -1)
                )
                if existing is None or conf > existing_conf:
                    facts_by_key[key] = f

        # ── Aggregate skills (deduplicate by skill_name, keep last occurrence)
        skills_by_name: dict[str, dict[str, Any]] = {}
        for capsule in sources:
            for skill in self._extract_skills(capsule):
                name = skill.get("skill_name", "")
                if name:
                    skills_by_name[name] = skill

        # ── Aggregate summaries, tags, turn counts
        summaries = [
            self._extract_summary(c) for c in sources
            if self._extract_summary(c)
        ]
        merged_summary = "\n---\n".join(summaries)

        all_tags: builtins.list[str] = builtins.list(tags or [])
        for c in sources:
            all_tags.extend(c.metadata.tags)
        merged_tags = list(dict.fromkeys(all_tags))  # deduplicate preserving order

        total_turns = sum(c.metadata.turn_count for c in sources)

        # ── Build new capsule
        has_skills = bool(skills_by_name)
        has_facts = bool(facts_by_key)
        if has_skills and has_facts:
            capsule_type = CapsuleType.HYBRID
            payload: dict[str, Any] = {
                "memory": {
                    "facts": list(facts_by_key.values()),
                    "context_summary": merged_summary,
                    "entities": {},
                    "timeline": [],
                    "raw_turns": [],
                },
                "skills": list(skills_by_name.values()),
            }
        elif has_skills:
            capsule_type = CapsuleType.SKILL
            skill = list(skills_by_name.values())[0]
            payload = dict(skill)
        else:
            capsule_type = CapsuleType.MEMORY
            payload = {
                "facts": list(facts_by_key.values()),
                "context_summary": merged_summary,
                "entities": {},
                "timeline": [],
                "raw_turns": [],
            }

        merged = Capsule(
            capsule_type=capsule_type,
            identity=CapsuleIdentity(
                user_id=target_user_id,
                session_id=f"merged_{uuid4().hex[:8]}",
                origin_platform="capsule-merge",
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.SEALED,
                sealed_at=datetime.now(timezone.utc),
            ),
            metadata=CapsuleMetadata(
                title=title or f"Merged: {capsule_ids[0][:8]}",
                tags=merged_tags,
                turn_count=total_turns,
            ),
            payload=payload,
        )
        merged.integrity.checksum = merged.compute_checksum()
        await self._storage.save(merged)
        logger.info(
            "Merged %d capsules into %s (type=%s)",
            len(capsule_ids), merged.capsule_id, capsule_type.value,
        )
        return merged

    async def diff(
        self,
        capsule_id_a: str,
        capsule_id_b: str,
    ) -> dict[str, Any]:
        """
        Compare two capsules and return a structured diff report.

        Comparison dimensions:
        - added_facts: facts in B but not in A (by key)
        - removed_facts: facts in A but not in B
        - modified_facts: same key but different value
        - added_skills: skills in B not in A (by skill_name)
        - removed_skills: skills in A not in B
        - summary_changed: whether context_summary differs

        Args:
            capsule_id_a: Baseline capsule ID ("old version").
            capsule_id_b: Comparison capsule ID ("new version").

        Returns:
            Dict with added_facts / removed_facts / modified_facts /
            added_skills / removed_skills / summary_changed.

        Raises:
            CapsuleNotFoundError: Any ID not found.
        """
        cap_a = await self.get(capsule_id_a)
        cap_b = await self.get(capsule_id_b)

        facts_a = {
            f.get("key", "") if isinstance(f, dict) else getattr(f, "key", ""): f
            for f in self._extract_facts(cap_a)
        }
        facts_b = {
            f.get("key", "") if isinstance(f, dict) else getattr(f, "key", ""): f
            for f in self._extract_facts(cap_b)
        }

        added_facts = [facts_b[k] for k in facts_b if k not in facts_a]
        removed_facts = [facts_a[k] for k in facts_a if k not in facts_b]
        modified_facts: builtins.list[dict[str, Any]] = []
        for k in facts_a:
            if k in facts_b:
                val_a = (
                    facts_a[k].get("value")
                    if isinstance(facts_a[k], dict) else getattr(facts_a[k], "value", None)
                )
                val_b = (
                    facts_b[k].get("value")
                    if isinstance(facts_b[k], dict) else getattr(facts_b[k], "value", None)
                )
                if str(val_a) != str(val_b):
                    modified_facts.append({
                        "key": k,
                        "old_value": val_a,
                        "new_value": val_b,
                    })

        skills_a = {
            s.get("skill_name", "") for s in self._extract_skills(cap_a)
        }
        skills_b_list = self._extract_skills(cap_b)
        skills_b = {s.get("skill_name", "") for s in skills_b_list}

        added_skills = [s for s in skills_b_list if s.get("skill_name") not in skills_a]
        removed_skill_names = skills_a - skills_b

        summary_a = self._extract_summary(cap_a)
        summary_b = self._extract_summary(cap_b)

        return {
            "capsule_id_a": capsule_id_a,
            "capsule_id_b": capsule_id_b,
            "added_facts": added_facts,
            "removed_facts": removed_facts,
            "modified_facts": modified_facts,
            "added_skills": added_skills,
            "removed_skills": list(removed_skill_names),
            "summary_changed": summary_a != summary_b,
            "facts_delta": len(added_facts) - len(removed_facts),
        }

    async def fork(
        self,
        capsule_id: str,
        new_user_id: str,
        new_agent_id: str | None = None,
        additional_tags: builtins.list[str] | None = None,
    ) -> Capsule:
        """
        Fork a capsule to a new user_id (core operation for cross-Agent memory transfer).

        Fork behavior:
        - Creates a deep copy of the original capsule
        - New capsule identity.user_id = new_user_id
        - New capsule identity.agent_id = new_agent_id (optional)
        - New capsule metadata.forked_from = original capsule_id (provenance)
        - New capsule status = IMPORTED
        - New capsule gets a new capsule_id (does not overwrite original)
        - Original capsule remains unchanged

        Args:
            capsule_id: Source capsule ID to fork.
            new_user_id: User/Agent ID for the new capsule.
            new_agent_id: Agent ID for the new capsule (optional).
            additional_tags: Extra tags to add (optional).

        Returns:
            The new persisted Capsule.

        Raises:
            CapsuleNotFoundError: Source capsule not found.
        """
        source = await self.get(capsule_id)

        # Deep copy payload to avoid sharing mutable objects
        import json
        payload_copy: dict[str, Any] = json.loads(json.dumps(
            source.payload, default=str
        ))

        new_tags = list(source.metadata.tags)
        if additional_tags:
            new_tags = list(dict.fromkeys(new_tags + additional_tags))

        forked = Capsule(
            capsule_type=source.capsule_type,
            identity=CapsuleIdentity(
                user_id=new_user_id,
                agent_id=new_agent_id,
                session_id=f"forked_{uuid4().hex[:8]}",
                origin_platform=source.identity.origin_platform,
            ),
            lifecycle=CapsuleLifecycle(
                status=CapsuleStatus.IMPORTED,
                sealed_at=datetime.now(timezone.utc),
            ),
            metadata=CapsuleMetadata(
                title=source.metadata.title,
                tags=new_tags,
                turn_count=source.metadata.turn_count,
                forked_from=capsule_id,
            ),
            payload=payload_copy,
        )
        forked.integrity.checksum = forked.compute_checksum()
        await self._storage.save(forked)
        logger.info(
            "Forked capsule %s -> %s (new_user=%s)",
            capsule_id, forked.capsule_id, new_user_id,
        )
        return forked

    async def get_context_for_injection(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """
        Recall historical memories related to query, return context structure injectable into system prompt.

        Args:
            query: Current question or topic description for relevance recall.
            user_id: Target user ID.
            top_k: Max capsules to recall.

        Returns:
            Dict with facts / skills / summary / prompt_injection / sources.
        """
        results = await self._storage.search(query, user_id=user_id, top_k=top_k)

        all_facts: builtins.list[dict[str, Any]] = []
        all_skills: builtins.list[dict[str, Any]] = []
        summaries: builtins.list[str] = []
        sources: builtins.list[str] = []

        for capsule, _score in results:
            sources.append(capsule.capsule_id)
            for f in self._extract_facts(capsule):
                all_facts.append(
                    f if isinstance(f, dict)
                    else f.model_dump() if hasattr(f, "model_dump") else dict(f)
                )
            for s in self._extract_skills(capsule):
                all_skills.append(s)
            summary = self._extract_summary(capsule)
            if summary:
                summaries.append(summary)

        lines: builtins.list[str] = ["=== Historical Memory Context ==="]
        if summaries:
            lines.append("Background: " + " | ".join(summaries[:3]))
            lines.append("")
        if all_facts:
            lines.append("Key Facts:")
            for f in all_facts[:20]:
                key = f.get("key", "")
                val = f.get("value", "")
                lines.append(f"  - {key}: {val}")
            lines.append("")
        if all_skills:
            lines.append("Available Skills:")
            for s in all_skills[:10]:
                name = s.get("skill_name", "")
                desc = s.get("description", "")
                lines.append(f"  [{name}] {desc}")
            lines.append("")
        lines.append("=== Historical Memory Context End ===")

        return {
            "facts": all_facts[:20],
            "skills": all_skills[:10],
            "summary": " | ".join(summaries[:3]),
            "prompt_injection": "\n".join(lines),
            "sources": sources,
        }

    # ─── Private helper methods ───────────────────────────────────────────────

    @staticmethod
    def _extract_facts(capsule: Capsule) -> builtins.list[Any]:
        """Safely extract facts list from any capsule type's payload."""
        p = capsule.payload
        if capsule.capsule_type == CapsuleType.HYBRID:
            facts: builtins.list[Any] = p.get("memory", {}).get("facts", [])
            return facts
        elif capsule.capsule_type == CapsuleType.MEMORY:
            facts2: builtins.list[Any] = p.get("facts", [])
            return facts2
        return []

    @staticmethod
    def _extract_skills(capsule: Capsule) -> builtins.list[dict[str, Any]]:
        """Safely extract skills list from any capsule type's payload."""
        p = capsule.payload
        if capsule.capsule_type == CapsuleType.HYBRID:
            skills: builtins.list[dict[str, Any]] = p.get("skills", [])
            return skills
        elif capsule.capsule_type == CapsuleType.SKILL:
            return [p] if p.get("skill_name") else []
        return []

    @staticmethod
    def _extract_summary(capsule: Capsule) -> str:
        """Safely extract context_summary from any capsule type's payload."""
        p = capsule.payload
        if capsule.capsule_type == CapsuleType.HYBRID:
            return str(p.get("memory", {}).get("context_summary", ""))
        elif capsule.capsule_type in (CapsuleType.MEMORY, CapsuleType.SKILL):
            return str(p.get("context_summary", p.get("description", "")))
        elif capsule.capsule_type == CapsuleType.CONTEXT:
            return str(p.get("content", ""))[:200]
        return ""
