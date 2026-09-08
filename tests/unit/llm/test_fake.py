"""The scripted fake chat model used everywhere tests need an LLM."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from propco_agent.llm.fake import ScriptedFakeChatModel, ScriptExhaustedError

pytestmark = pytest.mark.unit


class Answer(BaseModel):
    text: str
    score: int


def test_returns_scripted_strings_in_order() -> None:
    model = ScriptedFakeChatModel(responses=["one", "two"])
    assert model.invoke([HumanMessage("a")]).content == "one"
    assert model.invoke([HumanMessage("b")]).content == "two"


def test_records_every_call_for_assertions() -> None:
    model = ScriptedFakeChatModel(responses=["x"])
    model.invoke([HumanMessage("hello")])
    assert len(model.calls) == 1
    assert model.calls[0][-1].content == "hello"


def test_pydantic_response_is_serialised_as_json_content() -> None:
    model = ScriptedFakeChatModel(responses=[Answer(text="hi", score=3)])
    message = model.invoke([HumanMessage("q")])
    assert isinstance(message, AIMessage)
    assert Answer.model_validate_json(str(message.content)) == Answer(text="hi", score=3)


def test_exhausted_script_raises() -> None:
    model = ScriptedFakeChatModel(responses=[])
    with pytest.raises(ScriptExhaustedError):
        model.invoke([HumanMessage("q")])


def test_scripted_exception_is_raised() -> None:
    model = ScriptedFakeChatModel(responses=[ConnectionError("boom")])
    with pytest.raises(ConnectionError, match="boom"):
        model.invoke([HumanMessage("q")])


class TestStructuredOutput:
    def test_instance_is_returned_as_parsed(self) -> None:
        model = ScriptedFakeChatModel(responses=[Answer(text="a", score=1)])
        assert model.with_structured_output(Answer).invoke([HumanMessage("q")]) == Answer(
            text="a", score=1
        )

    def test_dict_is_validated(self) -> None:
        model = ScriptedFakeChatModel(responses=[{"text": "a", "score": 1}])
        assert model.with_structured_output(Answer).invoke([HumanMessage("q")]).score == 1

    def test_invalid_payload_reports_parsing_error_when_raw_included(self) -> None:
        model = ScriptedFakeChatModel(responses=[{"text": "a"}])
        out = model.with_structured_output(Answer, include_raw=True).invoke([HumanMessage("q")])
        assert out["parsed"] is None
        assert out["parsing_error"] is not None
        assert isinstance(out["raw"], AIMessage)

    def test_valid_payload_with_raw(self) -> None:
        model = ScriptedFakeChatModel(responses=['{"text": "a", "score": 2}'])
        out = model.with_structured_output(Answer, include_raw=True).invoke([HumanMessage("q")])
        assert out["parsed"] == Answer(text="a", score=2)
        assert out["parsing_error"] is None

    def test_invalid_payload_raises_without_raw(self) -> None:
        model = ScriptedFakeChatModel(responses=[{"text": "a"}])
        with pytest.raises(ValueError, match="score"):
            model.with_structured_output(Answer).invoke([HumanMessage("q")])

    def test_structured_calls_are_recorded_too(self) -> None:
        model = ScriptedFakeChatModel(responses=[Answer(text="a", score=1)])
        model.with_structured_output(Answer).invoke([HumanMessage("structured q")])
        assert model.calls[0][-1].content == "structured q"

    def test_llm_type(self) -> None:
        assert ScriptedFakeChatModel(responses=[])._llm_type == "scripted-fake"
