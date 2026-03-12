"""Utilities for sanitizing LLM responses before structured parsing."""
from __future__ import annotations

import json
import re
from typing import Any


def sanitize_llm_json(raw: str) -> Any:
    """
    Extract and parse JSON from an LLM response that may contain markdown
    fencing, explanatory text, or other decoration around the actual JSON.

    Strategy (ordered by specificity):
      1. Direct parse — works when the model obeys "return JSON only"
      2. Fenced code block extraction — handles ```json ... ``` wrapping
      3. Brace/bracket matching — finds the outermost { } or [ ] span
      4. Raises json.JSONDecodeError if all strategies fail

    Args:
        raw: Raw LLM response string.

    Returns:
        Parsed Python object (dict or list).

    Raises:
        json.JSONDecodeError: When no valid JSON can be extracted.
    """
    text = raw.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fenced code block — ```json\n...\n``` or ```\n...\n```
    fence_match = re.search(r"```(?:json|JSON)?\s*\n?([\s\S]*?)```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: outermost brace/bracket matching
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        if start == -1:
            continue
        end = text.rfind(close_ch)
        if end <= start:
            continue
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError(
        "No valid JSON found in LLM response", text, 0
    )
