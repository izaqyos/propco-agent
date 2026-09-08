"""Structured output with retry-on-validation-error and error mapping."""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from propco_agent.domain.errors import LLMUnavailableError
from propco_agent.llm.fake import ScriptedFakeChatModel
from propco_agent.llm.structured import invoke_structured

pytestmark = pytest.mark.unit


class Route(BaseModel):
    intent: str
    confidence: float


MESSAGES = [SystemMessage("classify"), HumanMessage("what is the p&l?")]


def test_valid_first_attempt() -> None:
    model = ScriptedFakeChatModel(responses=[Route(intent="pnl", confidence=0.9)])
    result = invoke_structured(model, Route, MESSAGES, max_retries=2)
    assert result == Route(intent="pnl", confidence=0.9)
    assert len(model.calls) == 1


def test_invalid_then_valid_retries_with_feedback() -> None:
    model = ScriptedFakeChatModel(
        responses=[{"intent": "pnl"}, Route(intent="pnl", confidence=0.8)]
    )
    result = invoke_structured(model, Route, MESSAGES, max_retries=2)
    assert result.confidence == 0.8
    assert len(model.calls) == 2
    feedback = model.calls[1][-1]
    assert isinstance(feedback, HumanMessage)
    assert "confidence" in str(feedback.content)  # the validation error is fed back
    assert model.calls[1][0] == MESSAGES[0]  # original system prompt kept


def test_exhausting_retries_raises_unavailable() -> None:
    model = ScriptedFakeChatModel(responses=[{"x": 1}, {"x": 2}, {"x": 3}])
    with pytest.raises(LLMUnavailableError, match="3 attempts"):
        invoke_structured(model, Route, MESSAGES, max_retries=2)
    assert len(model.calls) == 3


def test_zero_retries_means_single_attempt() -> None:
    model = ScriptedFakeChatModel(responses=[{"x": 1}, Route(intent="pnl", confidence=1)])
    with pytest.raises(LLMUnavailableError):
        invoke_structured(model, Route, MESSAGES, max_retries=0)
    assert len(model.calls) == 1


def test_transport_errors_are_mapped_to_unavailable() -> None:
    model = ScriptedFakeChatModel(responses=[TimeoutError("slow")])
    with pytest.raises(LLMUnavailableError, match="TimeoutError") as excinfo:
        invoke_structured(model, Route, MESSAGES, max_retries=2)
    assert isinstance(excinfo.value.__cause__, TimeoutError)
