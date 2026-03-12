from __future__ import annotations
from capsule_memory.adapters.base import BaseAdapter, TurnData
from capsule_memory.exceptions import AdapterError


class AnthropicAdapter(BaseAdapter):
    adapter_name = "anthropic"

    def extract_turn(self, messages: list[dict[str, str]], response: object) -> TurnData:
        try:
            user_message = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
            )
            if hasattr(response, "content"):
                content_blocks = response.content
                assistant_response = next(
                    (b.text for b in content_blocks if hasattr(b, "text")), ""
                )
                model = getattr(response, "model", "")
                usage = getattr(response, "usage", None)
                tokens = (
                    (getattr(usage, "input_tokens", 0) or 0)
                    + (getattr(usage, "output_tokens", 0) or 0)
                )
                raw = response.model_dump() if hasattr(response, "model_dump") else {}
            elif isinstance(response, dict):
                assistant_response = response["content"][0]["text"]
                model = response.get("model", "")
                tokens = (
                    response.get("usage", {}).get("input_tokens", 0)
                    + response.get("usage", {}).get("output_tokens", 0)
                )
                raw = response
            else:
                raise AdapterError(f"Unknown Anthropic response type: {type(response)}")
            return TurnData(user_message=user_message, assistant_response=assistant_response,
                            model=model, tokens_used=tokens, raw_response=raw)
        except (KeyError, IndexError, AttributeError) as e:
            raise AdapterError(f"Anthropic adapter extraction failed: {e}") from e
