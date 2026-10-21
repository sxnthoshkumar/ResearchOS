"""
OpenAI-Compatible Hosted LLM Provider.
Interacts with OpenAI, Groq, Ollama, vLLM, or any OpenAI-spec compatible chat completions endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class CompatibleLLMProvider(BaseLLMProvider):
    """Client for OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.api_key = api_key or settings.LLM_API_KEY
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    def get_provider_name(self) -> str:
        return f"openai_compatible({self.model})"

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 2500,
        response_format_json: bool = False,
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured for OpenAI-compatible provider.")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error("LLM Provider HTTP %s: %s", e.response.status_code, e.response.text)
                raise RuntimeError(f"LLM API Error [{e.response.status_code}]: {e.response.text}") from e
            except httpx.RequestError as e:
                logger.error("LLM Connection Error: %s", e)
                raise RuntimeError(f"Failed to connect to LLM endpoint at {self.base_url}: {e}") from e

        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "").strip()

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        # Approximate cost calculation for standard hosted models (e.g. gpt-4o-mini ~ $0.15 / 1M in, $0.60 / 1M out)
        est_cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.00000060)

        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(est_cost, 6),
            raw_response={"id": data.get("id"), "finish_reason": choice.get("finish_reason")},
        )
