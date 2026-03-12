from __future__ import annotations
from abc import ABC, abstractmethod
from capsule_memory.models.events import SkillTriggerEvent


class BaseNotifier(ABC):
    """Abstract base class for all notifiers."""

    @abstractmethod
    async def notify(self, event: SkillTriggerEvent) -> None:
        """Notify the user about a skill trigger event."""
