from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TurnData:
    user_message: str
    assistant_response: str
    model: str = ""
    tokens_used: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_request: dict[str, Any] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    @property
    @abstractmethod
    def adapter_name(self) -> str: ...

    @abstractmethod
    def extract_turn(self, *args: Any, **kwargs: Any) -> TurnData:
        """Extract TurnData from the AI framework's native response object."""
