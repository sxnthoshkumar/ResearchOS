"""
Application configuration and environment variable loading using pydantic-settings.
Enforces secret masking and safe defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    DEBUG: bool = False

    # LLM Settings
    LLM_PROVIDER: str = "ollama"  # 'ollama', 'demo', 'openai', 'generic'
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 90

    # Local Ollama Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"

    # Research Sources
    OPENALEX_EMAIL: str = "researcher@example.org"
    MAX_SOURCES_PER_QUERY: int = 10
    SEARCH_TIMEOUT_SECONDS: int = 25

    # Storage
    DATABASE_PATH: str = "data/research_assistant.db"
    EXPORT_DIR: str = "exports"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_demo_mode(self) -> bool:
        prov = self.LLM_PROVIDER.lower()
        if prov == "demo":
            return True
        if prov == "ollama":
            return False
        return not bool(self.LLM_API_KEY and len(self.LLM_API_KEY.strip()) > 5)

    def get_masked_api_key(self) -> str:
        if self.LLM_PROVIDER.lower() == "ollama":
            return "Local Ollama (No API Key Required)"
        if not self.LLM_API_KEY:
            return "None (Demo Mode Active)"
        key = self.LLM_API_KEY.strip()
        if len(key) <= 8:
            return "******"
        return f"{key[:3]}...{key[-4:]}"

    def get_active_model_name(self) -> str:
        if self.LLM_PROVIDER.lower() == "ollama":
            return self.OLLAMA_MODEL
        if self.LLM_PROVIDER.lower() == "demo":
            return "demo-deterministic-engine"
        return self.LLM_MODEL

    def get_public_status(self) -> dict:
        """Returns safe provider status without exposing credentials."""
        is_ollama = self.LLM_PROVIDER.lower() == "ollama"
        base_url = (
            self.OLLAMA_BASE_URL if is_ollama
            else (self.LLM_BASE_URL if not self.is_demo_mode else "Built-in Deterministic Engine")
        )
        return {
            "provider": self.LLM_PROVIDER,
            "model": self.get_active_model_name(),
            "is_demo_mode": self.is_demo_mode,
            "has_api_key": is_ollama or bool(self.LLM_API_KEY and len(self.LLM_API_KEY) > 5),
            "masked_key": self.get_masked_api_key(),
            "base_url": base_url,
            "timeout_seconds": self.LLM_TIMEOUT_SECONDS,
            "openalex_email": self.OPENALEX_EMAIL,
            "ollama_base_url": self.OLLAMA_BASE_URL,
            "ollama_model": self.OLLAMA_MODEL,
        }


settings = Settings()
