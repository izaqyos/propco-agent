"""Router node: LLM classification with rule-based degradation."""

import pytest
from langchain_core.messages import SystemMessage

from propco_agent.domain.models import Intent
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.router import make_router
from propco_agent.graph.state import initial_state
from propco_agent.llm.factory import Role
from propco_agent.llm.fake import ScriptedFakeChatModel
from propco_agent.llm.schemas import RouteDecision

pytestmark = pytest.mark.component


def run(deps: Deps, text: str) -> dict:  # type: ignore[type-arg]
    return make_router(deps)(initial_state(text, thread_id="t"))


def test_uses_llm_decision(deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.PNL, confidence=0.9))
    out = run(deps, "total p&l 2024")
    assert out["route"].intent is Intent.PNL
    assert out.get("degraded", False) is False
    assert out["trace"][0].node == "router"
    assert "pnl" in out["trace"][0].summary


def test_prompt_wraps_question_as_data(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.PNL, confidence=0.9))
    run(deps, "total p&l 2024")
    messages = fake_models[Role.ROUTER].calls[0]
    assert isinstance(messages[0], SystemMessage)
    assert "Building 17" in str(messages[0].content)
    assert "<user_question>" in str(messages[-1].content)
    assert "total p&l 2024" in str(messages[-1].content)


def test_falls_back_to_rules_when_llm_unavailable(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(ConnectionError("ollama down"))
    out = run(deps, "who are my top tenants?")
    assert out["route"].intent is Intent.TENANT_ANALYSIS
    assert out["degraded"] is True
    assert any("fallback" in t.summary for t in out["trace"])
    assert out["errors"]


def test_low_confidence_becomes_clarify(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.PNL, confidence=0.2))
    out = run(deps, "numbers")
    assert out["route"].intent is Intent.CLARIFY
    assert out["route"].clarification


def test_clarify_without_text_gets_default_question(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.CLARIFY, confidence=0.9))
    out = run(deps, "hello")
    assert out["route"].clarification


def test_compound_detected_by_rules_when_llm_misses_it(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(
        RouteDecision(intent=Intent.TENANT_ANALYSIS, confidence=0.95)
    )
    out = run(deps, "Who are my top tenants, and is anything unusual in the numbers?")
    assert out["route"].is_compound is True
    assert len(out["route"].sub_questions) == 2
    assert out["route"].intent is Intent.TENANT_ANALYSIS


def test_single_sub_question_is_collapsed(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(
        RouteDecision(intent=Intent.PNL, confidence=0.9, sub_questions=["only one"])
    )
    assert run(deps, "p&l")["route"].sub_questions == []
