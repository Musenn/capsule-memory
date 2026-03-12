from __future__ import annotations
import sys
import logging
from typing import Any
from capsule_memory.models.events import SkillTriggerEvent
from capsule_memory.notifier.base import BaseNotifier

logger = logging.getLogger(__name__)


class CLINotifier(BaseNotifier):
    """CLI notifier using rich for interactive display."""

    def __init__(self, session_ref: Any = None) -> None:
        """
        Args:
            session_ref: Optional SessionTracker reference.
                If provided, user input in CLI triggers confirm_skill_trigger().
                If not provided, only prints notification without blocking.
        """
        self._session: Any = session_ref
        self._console: Any = None
        try:
            from rich.console import Console
            self._console = Console()
        except ImportError:
            pass

    async def notify(self, event: SkillTriggerEvent) -> None:
        draft = event.skill_draft
        bar = "\u2593" * int(draft.confidence * 10) + "\u2591" * (10 - int(draft.confidence * 10))
        panel_content = (
            f"Name: {draft.suggested_name}\n"
            f"Confidence: {bar} {int(draft.confidence * 100)}%\n"
            f"Trigger rule: {draft.trigger_rule.value}\n"
            f"Preview: {draft.preview[:100]}..."
        )

        if self._console is not None:
            from rich.panel import Panel
            self._console.print(Panel(
                panel_content,
                title="Skill Detected",
                border_style="yellow",
            ))
        else:
            print(f"[Skill Detected] {panel_content}")

        if not sys.stdin.isatty() or self._session is None:
            if self._console is not None:
                self._console.print(
                    f"[dim](Non-interactive mode, event_id={event.event_id})[/dim]"
                )
            return

        from rich.prompt import Prompt
        choices = {
            "1": "extract_skill",
            "2": "merge_memory",
            "3": "extract_hybrid",
            "4": "ignore",
            "5": "never",
        }
        if self._console is not None:
            self._console.print(
                "[1] Extract Skill  [2] Merge to Memory  "
                "[3] Hybrid  [4] Ignore  [5] Never Remind"
            )
        choice = Prompt.ask("Choose", choices=list(choices.keys()), default="4")
        resolution = choices[choice]
        await self._session.confirm_skill_trigger(event.event_id, resolution)
        if self._console is not None:
            self._console.print(f"[green]Resolved: {resolution}[/green]")
