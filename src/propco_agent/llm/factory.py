"""Build chat models per role from settings. The only module that knows provider SDKs."""

from __future__ import annotations

from enum import StrEnum

from langchain_core.language_models import BaseChatModel

from propco_agent.config import LLMProvider, Settings, has_gemini_key
from propco_agent.domain.errors import LLMUnavailableError
from propco_agent.llm.fake import ScriptedFakeChatModel


class Role(StrEnum):
    """What a model is used for; decides the model tier."""

    ROUTER = "router"
    EXTRACTOR = "extractor"
    SYNTH = "synth"
    GENERAL = "general"


_SMALL_MODEL_ROLES = frozenset({Role.ROUTER, Role.EXTRACTOR})


def get_chat_model(role: Role, settings: Settings) -> BaseChatModel:
    """Chat model for ``role`` under the configured provider. Never performs network I/O."""
    match settings.llm_provider:
        case LLMProvider.FAKE:
            return ScriptedFakeChatModel()
        case LLMProvider.OLLAMA:
            from langchain_ollama import ChatOllama

            # reasoning=False: qwen-class models otherwise "think" for tens of seconds before
            # emitting JSON; num_predict bounds runaway generations.
            return ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=settings.llm_temperature,
                reasoning=False,
                num_predict=1024,
            )
        case LLMProvider.GEMINI:
            if not has_gemini_key():
                raise LLMUnavailableError(
                    "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set; "
                    "set it in the environment or switch PROPCO_LLM_PROVIDER to ollama/fake"
                )
            from langchain_google_genai import ChatGoogleGenerativeAI

            name = (
                settings.gemini_model_small
                if role in _SMALL_MODEL_ROLES
                else settings.gemini_model_large
            )
            return ChatGoogleGenerativeAI(
                model=name,
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_s,
                max_retries=settings.llm_max_retries,
            )


def build_models(settings: Settings) -> dict[Role, BaseChatModel]:
    """One model per role."""
    return {role: get_chat_model(role, settings) for role in Role}
