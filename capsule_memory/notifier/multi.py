from __future__ import annotations
import logging
from capsule_memory.models.events import SkillTriggerEvent
from capsule_memory.notifier.base import BaseNotifier

logger = logging.getLogger(__name__)


class MultiNotifier(BaseNotifier):
    """Dispatches events to multiple notifiers."""

    def __init__(self, notifiers: list[BaseNotifier]) -> None:
        self._notifiers = notifiers

    async def notify(self, event: SkillTriggerEvent) -> None:
        for notifier in self._notifiers:
            try:
                await notifier.notify(event)
            except Exception as e:
                logger.warning("MultiNotifier: %s failed: %s", type(notifier).__name__, e)
