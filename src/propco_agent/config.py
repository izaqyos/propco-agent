"""Runtime settings, read from ``PROPCO_*`` environment variables (and a local ``.env``).

API keys are deliberately not settings: the Google SDK reads ``GOOGLE_API_KEY`` /
``GEMINI_API_KEY`` from the environment itself, so the key never lives on an object that
could be logged or serialised.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from propco_agent.domain.models import DataPolicy

_KEY_VARS: tuple[str, ...] = ("GOOGLE_API_KEY", "GEMINI_API_KEY")


class LLMProvider(StrEnum):
    """Which chat-model backend to use."""

    GEMINI = "gemini"
    OLLAMA = "ollama"
    FAKE = "fake"


class Settings(BaseSettings):
    """All tunables in one place. Defaults match the free-tier Gemini deployment."""

    model_config = SettingsConfigDict(
        env_prefix="PROPCO_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM
    llm_provider: LLMProvider = LLMProvider.GEMINI
    gemini_model_small: str = "gemini-3.5-flash-lite"  # routing, extraction
    gemini_model_large: str = "gemini-3.5-flash"  # answer synthesis, general knowledge
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    llm_timeout_s: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    llm_temperature: float = Field(default=0.0, ge=0, le=2)

    # data
    data_path: Path = Path("data/amiio.parquet")
    data_policy: DataPolicy = DataPolicy.RAW
    as_of: str | None = Field(default=None, pattern=r"^\d{4}-M\d{2}$")
    currency: str = "EUR"

    # runtime guards
    max_input_chars: int = Field(default=2000, ge=1)
    recursion_limit: int = Field(default=25, ge=1)
    log_json: bool = False

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, built once."""
    return Settings()


def reset_settings() -> None:
    """Forget the cached settings (tests, or after changing the environment)."""
    get_settings.cache_clear()


def has_gemini_key() -> bool:
    """Whether a Gemini key is present in the environment (never returns the key)."""
    return any(os.environ.get(name) for name in _KEY_VARS)
