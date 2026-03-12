from __future__ import annotations
from capsule_memory.adapters.base import BaseAdapter, TurnData
from capsule_memory.exceptions import AdapterError


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI Python SDK (openai>=1.0) response format."""
    adapter_name = "openai"

    def extract_turn(self, messages: list[dict[str, str]], response: object) -> TurnData:
        """
        Args:
            messages: The messages list sent to OpenAI (including history).
            response: openai.types.chat.ChatCompletion object or equivalent dict.
        """
        try:
            user_message = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
            )
            if hasattr(response, "choices"):
                assistant_response = response.choices[0].message.content or ""
                model = getattr(response, "model", "")
                tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
                raw = response.model_dump() if hasattr(response, "model_dump") else {}
            elif isinstance(response, dict):
                assistant_response = response["choices"][0]["message"]["content"]
                model = response.get("model", "")
                tokens = response.get("usage", {}).get("total_tokens", 0)
                raw = response
            else:
                raise AdapterError(f"Unknown OpenAI response type: {type(response)}")
            return TurnData(user_message=user_message, assistant_response=assistant_response,
                            model=model, tokens_used=tokens, raw_response=raw)
        except (KeyError, IndexError, AttributeError) as e:
            raise AdapterError(f"OpenAI adapter extraction failed: {e}") from e
