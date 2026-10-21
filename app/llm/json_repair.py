"""
JSON extraction, cleaning, and repair utility for structured LLM outputs.
Handles markdown fences, trailing commas, and boundary extraction.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


def clean_json_text(raw_text: str) -> str:
    """Strip markdown formatting and locate the primary JSON object or array."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty response string cannot be parsed as JSON.")

    text = raw_text.strip()

    # 1. Strip markdown code block wrappers (```json ... ``` or ``` ...)
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # 2. Extract outermost JSON structure ({ ... } or [ ... ])
    start_brace = text.find("{")
    start_bracket = text.find("[")

    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        end_brace = text.rfind("}")
        if end_brace != -1 and end_brace > start_brace:
            text = text[start_brace : end_brace + 1]
    elif start_bracket != -1:
        end_bracket = text.rfind("]")
        if end_bracket != -1 and end_bracket > start_bracket:
            text = text[start_bracket : end_bracket + 1]

    # 3. Clean common LLM JSON syntax errors (trailing commas before closing brackets)
    text = re.sub(r",\s*([\}\]])", r"\1", text)

    return text.strip()


def extract_structured_json(raw_text: str) -> Union[Dict[str, Any], List[Any]]:
    """Parse JSON with multi-stage sanitization. Raises ValueError on unrecoverable syntax."""
    # Attempt direct parse first
    try:
        return json.loads(raw_text)
    except Exception:
        pass

    # Attempt sanitized parse
    cleaned = clean_json_text(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("Failed parsing cleaned JSON text (error: %s). Content preview: %s", e, cleaned[:200])
        raise ValueError(f"Malformed JSON in model output: {e}") from e
