"""Settings: environment-driven, prefixed, validated, never holding secrets."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from propco_agent.config import LLMProvider, Settings, get_settings, has_gemini_key, reset_settings
from propco_agent.domain.models import DataPolicy

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from the developer's / CI's environment (CI sets PROPCO_LLM_PROVIDER=fake)."""
    for key in (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        *[k for k in os.environ if k.startswith("PROPCO_")],
    ):
        monkeypatch.delenv(key, raising=False)
    reset_settings()


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.llm_provider is LLMProvider.GEMINI
    assert s.gemini_model_small == "gemini-3.5-flash-lite"
    assert s.gemini_model_large == "gemini-3.5-flash"
    assert s.ollama_model == "qwen3.5:9b"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.data_path == Path("data/amiio.parquet")
    assert s.data_policy is DataPolicy.RAW
    assert s.as_of is None
    assert s.currency == "EUR"
    assert s.max_input_chars == 2000
    assert s.recursion_limit == 25
    assert s.llm_timeout_s == 60
    assert s.llm_max_retries == 2
    assert s.llm_temperature == 0.0
    assert s.log_json is False


def test_env_prefix_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPCO_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("PROPCO_DATA_POLICY", "dedup")
    monkeypatch.setenv("PROPCO_AS_OF", "2024-M12")
    monkeypatch.setenv("PROPCO_CURRENCY", "usd")
    s = Settings(_env_file=None)
    assert s.llm_provider is LLMProvider.OLLAMA
    assert s.data_policy is DataPolicy.DEDUP
    assert s.as_of == "2024-M12"
    assert s.currency == "USD"


def test_invalid_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPCO_LLM_PROVIDER", "openai")
    with pytest.raises(ValidationError, match="llm_provider"):
        Settings(_env_file=None)


def test_invalid_as_of_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPCO_AS_OF", "March 2025")
    with pytest.raises(ValidationError, match="as_of"):
        Settings(_env_file=None)


def test_unknown_env_vars_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPCO_NOT_A_SETTING", "1")
    Settings(_env_file=None)


def test_get_settings_is_cached_and_resettable(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_settings()
    assert get_settings() is first
    monkeypatch.setenv("PROPCO_CURRENCY", "GBP")
    assert get_settings().currency == "EUR"  # still cached
    reset_settings()
    assert get_settings().currency == "GBP"


def test_has_gemini_key_reads_either_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    assert has_gemini_key() is False
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert has_gemini_key() is True
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "y")
    assert has_gemini_key() is True


def test_settings_never_contain_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "super-secret-value")
    s = Settings(_env_file=None)
    assert "super-secret-value" not in repr(s)
    assert "super-secret-value" not in s.model_dump_json()
