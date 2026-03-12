from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable
from capsule_memory.models.events import SkillTriggerEvent
from capsule_memory.notifier.base import BaseNotifier

logger = logging.getLogger(__name__)


class CallbackNotifier(BaseNotifier):
    """Notifier that calls a user-provided callback function."""

    def __init__(self, callback: Callable[..., Any]) -> None:
        self._callback = callback

    async def notify(self, event: SkillTriggerEvent) -> None:
        try:
            result = self._callback(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning("CallbackNotifier error: %s", e)
