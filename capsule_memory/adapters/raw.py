from __future__ import annotations
from typing import Any
from capsule_memory.adapters.base import BaseAdapter, TurnData


class RawAdapter(BaseAdapter):
    """Adapter accepting raw strings, for scenarios without any SDK dependency."""
    adapter_name = "raw"

    def extract_turn(self, user_message: str, assistant_response: str, **kwargs: Any) -> TurnData:
        return TurnData(
            user_message=user_message,
            assistant_response=assistant_response,
            model=kwargs.get("model", ""),
            tokens_used=kwargs.get("tokens", 0),
        )
