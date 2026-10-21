"""
Abstract base class and schemas for LLM Providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str  # 'system', 'user', 'assistant'
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None


class BaseLLMProvider(ABC):
    """Abstract interface separating model inference from application domain logic."""

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 2000,
        response_format_json: bool = False,
    ) -> LLMResponse:
        """Generate a response from the model."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass
