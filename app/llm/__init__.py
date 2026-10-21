"""
LLM Provider Factory.
"""

from typing import Optional

from app.config import settings
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from app.llm.demo_provider import DemoLLMProvider
from app.llm.compatible_provider import CompatibleLLMProvider
from app.llm.ollama_provider import OllamaLLMProvider


def get_llm_provider(
    force_demo: bool = False,
    provider_name: Optional[str] = None,
) -> BaseLLMProvider:
    """
    Return configured LLM provider according to settings or explicit override.
    Does NOT silently fall back from real LLM inference to demo logic.
    """
    selected_provider = (provider_name or settings.LLM_PROVIDER).lower()

    if force_demo or selected_provider == "demo":
        return DemoLLMProvider()

    if selected_provider == "ollama":
        return OllamaLLMProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    if selected_provider in ("openai", "generic"):
        return CompatibleLLMProvider(
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    # Fallback to DemoLLMProvider only if unrecognized and demo allowed
    return DemoLLMProvider()


__all__ = [
    "BaseLLMProvider",
    "LLMMessage",
    "LLMResponse",
    "DemoLLMProvider",
    "CompatibleLLMProvider",
    "OllamaLLMProvider",
    "get_llm_provider",
]
