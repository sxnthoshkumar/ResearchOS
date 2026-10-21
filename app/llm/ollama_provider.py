"""
Ollama Local LLM Provider.
Interacts with local Ollama daemon via native `/api/chat` and `/api/tags` endpoints.
Provides zero-cost local neural inference with model health checks and robust error handling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


def is_model_match(installed_name: str, target_model: str) -> bool:
    """Accurately match configured model against Ollama installed model tags.

    Handles:
    - Exact match (e.g. 'qwen2.5:3b' == 'qwen2.5:3b')
    - Registry prefix stripping (e.g. 'library/qwen2.5:3b' == 'qwen2.5:3b')
    - Default latest tag resolution (e.g. 'phi3:latest' matches 'phi3')
    - Tag prefix/suffix handling (e.g. 'qwen2.5:3b' matching 'qwen2.5:3b')
    """
    if not installed_name or not target_model:
        return False
    inst = installed_name.strip().lower()
    targ = target_model.strip().lower()

    if inst == targ:
        return True

    # Strip registry prefixes if present (e.g. library/ or registry.ollama.ai/library/)
    if "/" in inst:
        inst = inst.split("/")[-1]
    if "/" in targ:
        targ = targ.split("/")[-1]

    if inst == targ:
        return True

    # Check base and tag
    inst_base, _, inst_tag = inst.partition(":")
    targ_base, _, targ_tag = targ.partition(":")

    if inst_base == targ_base:
        if inst_tag in ("", "latest") and targ_tag in ("", "latest"):
            return True
        if inst_tag == targ_tag:
            return True
        if targ_tag and inst_tag.startswith(targ_tag):
            return True

    return False


class OllamaLLMProvider(BaseLLMProvider):
    """Client for local Ollama chat completion API (/api/chat)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    def get_provider_name(self) -> str:
        return f"ollama({self.model})"

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 2500,
        response_format_json: bool = False,
    ) -> LLMResponse:
        """Call Ollama /api/chat with full conversational context."""
        url = f"{self.base_url}/api/chat"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if response_format_json:
            payload["format"] = "json"

        # Explicit connect & read timeouts (10s connect, self.timeout read)
        client_timeout = httpx.Timeout(self.timeout, connect=10.0)

        try:
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 404:
                    err_msg = (
                        f"Ollama model '{self.model}' was not found at {self.base_url}. "
                        f"Please download it in your terminal via 'ollama pull {self.model}'."
                    )
                    logger.error(err_msg)
                    raise RuntimeError(err_msg)

                response.raise_for_status()
                data = response.json()

        except httpx.ConnectError as e:
            err_msg = (
                f"Ollama service is unavailable at {self.base_url}. "
                f"Please ensure the Ollama daemon is running ('ollama serve' or start the Ollama desktop app)."
            )
            logger.error("%s (Details: %s)", err_msg, e)
            raise RuntimeError(err_msg) from e

        except httpx.TimeoutException as e:
            err_msg = (
                f"Ollama inference timed out after {self.timeout}s on model '{self.model}' at {self.base_url}. "
                "Consider increasing LLM_TIMEOUT_SECONDS or ensuring GPU acceleration is active."
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        except httpx.HTTPStatusError as e:
            err_msg = f"Ollama HTTP error [{e.response.status_code}]: {e.response.text}"
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        except httpx.RequestError as e:
            err_msg = f"Network communication error with Ollama at {self.base_url}: {e}"
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        # Extract message content
        message_data = data.get("message", {})
        content = message_data.get("content", "").strip()

        # Extract token usage telemetry
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        total_tokens = prompt_tokens + completion_tokens

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=0.0,  # Local inference has zero API bill
            raw_response={
                "total_duration_ns": data.get("total_duration"),
                "eval_duration_ns": data.get("eval_duration"),
                "done": data.get("done", True),
                "done_reason": data.get("done_reason"),
            },
        )

    async def check_health(self) -> Dict[str, Any]:
        """Check whether Ollama daemon is reachable and whether the configured model is installed.

        Distinguishes four explicit operational states:
        1. online: daemon reachable AND configured model installed.
        2. model_missing: daemon reachable BUT configured model not found.
        3. offline: daemon unreachable / connection refused.
        4. timeout / error: request timed out or returned HTTP error.
        """
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_models = data.get("models", [])
                    available_names: List[str] = []
                    for m in raw_models:
                        name = m.get("name") or m.get("model") or ""
                        if name:
                            available_names.append(name)

                    model_installed = any(
                        is_model_match(name, self.model)
                        for name in available_names
                    )

                    msg = (
                        f"Model '{self.model}' is installed and ready."
                        if model_installed
                        else f"Model '{self.model}' not found in Ollama. Run 'ollama pull {self.model}'."
                    )
                    return {
                        "reachable": True,
                        "status": "online" if model_installed else "model_missing",
                        "base_url": self.base_url,
                        "configured_model": self.model,
                        "model_installed": model_installed,
                        "available_models": available_names,
                        "message": msg,
                        "error": None,
                    }

                return {
                    "reachable": False,
                    "status": "error",
                    "base_url": self.base_url,
                    "configured_model": self.model,
                    "model_installed": False,
                    "available_models": [],
                    "message": f"Ollama returned HTTP error [{resp.status_code}].",
                    "error": f"HTTP {resp.status_code}: {resp.text[:100]}",
                }

        except httpx.ConnectError as e:
            return {
                "reachable": False,
                "status": "offline",
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_installed": False,
                "available_models": [],
                "message": f"Cannot connect to Ollama daemon at {self.base_url}. Ensure Ollama is running ('ollama serve').",
                "error": str(e),
            }
        except httpx.TimeoutException as e:
            return {
                "reachable": False,
                "status": "timeout",
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_installed": False,
                "available_models": [],
                "message": f"Connection to Ollama timed out after 4.0s at {self.base_url}.",
                "error": str(e),
            }
        except Exception as e:
            return {
                "reachable": False,
                "status": "error",
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_installed": False,
                "available_models": [],
                "message": f"Health check failed: {str(e)[:100]}",
                "error": str(e),
            }
