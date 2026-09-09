"""Provider factory: one place that knows how to build a chat model per role."""

import pytest

from propco_agent.config import LLMProvider, Settings
from propco_agent.llm.factory import Role, build_models, get_chat_model
from propco_agent.llm.fake import ScriptedFakeChatModel

pytestmark = pytest.mark.unit


def settings(provider: LLMProvider) -> Settings:
    return Settings(_env_file=None, llm_provider=provider)


def test_fake_provider_builds_scripted_models_for_every_role() -> None:
    models = build_models(settings(LLMProvider.FAKE))
    assert set(models) == set(Role)
    assert all(isinstance(m, ScriptedFakeChatModel) for m in models.values())


def test_ollama_provider_uses_configured_model_and_url() -> None:
    from langchain_ollama import ChatOllama

    s = Settings(
        _env_file=None,
        llm_provider=LLMProvider.OLLAMA,
        ollama_model="qwen3.5:9b",
        ollama_base_url="http://localhost:11434",
        llm_temperature=0.0,
    )
    model = get_chat_model(Role.ROUTER, s)
    assert isinstance(model, ChatOllama)
    assert model.model == "qwen3.5:9b"
    assert model.base_url == "http://localhost:11434"
    assert model.temperature == 0.0
    # structured roles must not spend minutes "thinking" before emitting JSON
    assert model.reasoning is False
    assert model.num_predict == 1024


def test_gemini_provider_tiers_models_by_role(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    s = settings(LLMProvider.GEMINI)
    small = get_chat_model(Role.ROUTER, s)
    large = get_chat_model(Role.SYNTH, s)
    assert isinstance(small, ChatGoogleGenerativeAI)
    assert "gemini-3.5-flash-lite" in small.model
    assert "gemini-3.5-flash" in large.model
    assert "lite" not in large.model
    assert get_chat_model(Role.EXTRACTOR, s).model == small.model
    assert get_chat_model(Role.GENERAL, s).model == large.model


def test_gemini_without_key_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from propco_agent.domain.errors import LLMUnavailableError

    with pytest.raises(LLMUnavailableError, match="GOOGLE_API_KEY"):
        get_chat_model(Role.ROUTER, settings(LLMProvider.GEMINI))


def test_role_values() -> None:
    assert {r.value for r in Role} == {"router", "extractor", "synth", "general"}
