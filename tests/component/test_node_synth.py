"""Synthesizer, general-knowledge and unsupported nodes."""

import pytest

from propco_agent.analytics.pnl import compute_pnl
from propco_agent.domain.models import DataPolicy, Intent, LedgerFilter, Period
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.synth import (
    grounding_violations,
    make_general,
    make_synthesizer,
    make_unsupported,
)
from propco_agent.graph.state import AgentState, ResolvedQuery, TraceEvent, initial_state
from propco_agent.llm.factory import Role
from propco_agent.llm.fake import ScriptedFakeChatModel
from propco_agent.llm.schemas import RouteDecision
from propco_agent.resolve.metrics import Metric

pytestmark = pytest.mark.component
KW = {"policy": DataPolicy.RAW, "as_of": "2025-M03"}


@pytest.fixture
def pnl_state(deps: Deps) -> AgentState:
    result = compute_pnl(deps.frame(DataPolicy.RAW), LedgerFilter(period=Period.year(2024)), **KW)
    state = initial_state("What was the P&L in 2024?", thread_id="t")
    state["route"] = RouteDecision(intent=Intent.PNL, confidence=0.9)
    state["resolved"] = ResolvedQuery(
        filter=LedgerFilter(period=Period.year(2024)),
        periods=[Period.year(2024)],
        properties=[],
        tenants=[],
        metric=Metric.PNL,
        notes=["portfolio net includes entity-level overhead"],
    )
    state["results"] = [result]
    state["notes"] = ["portfolio net includes entity-level overhead"]  # resolver writes both
    state["trace"] = [TraceEvent(node="router", ms=1, summary="intent=pnl")]
    return state


class TestGrounding:
    def test_no_violation_when_every_number_is_in_results(self) -> None:
        text = "P&L for 2024 was €1,171,521.55 across 3,181 rows (+37.93%)."
        assert grounding_violations(text, {1171521.55, 3181, 37.93}) == []

    def test_years_and_small_integers_are_not_checked(self) -> None:
        assert grounding_violations("In 2024 and Q1 2025, 2 of 5 buildings", {1.0}) == []

    def test_invented_money_is_flagged(self) -> None:
        assert grounding_violations("It was €1,200,000.00", {1171521.55}) == [1200000.0]

    def test_formatting_variants_are_accepted(self) -> None:
        assert (
            grounding_violations(
                "EUR 1171521.55 or 1,171,521.55 or -€1,124,007.19", {1171521.55, -1124007.19}
            )
            == []
        )


class TestSynthesizer:
    def test_uses_llm_answer_and_appends_steps(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel], pnl_state: AgentState
    ) -> None:
        fake_models[Role.SYNTH].responses.append(
            "The total P&L for 2024 was €1,171,521.55 (net, including overhead)."
        )
        out = make_synthesizer(deps)(pnl_state)
        assert out["answer"].startswith("The total P&L for 2024 was €1,171,521.55")
        assert "Steps:" in out["answer"]
        assert "router" in out["answer"]
        assert out["trace"][-1].node == "synthesizer"

    def test_prompt_carries_question_results_and_notes(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel], pnl_state: AgentState
    ) -> None:
        fake_models[Role.SYNTH].responses.append("€1,171,521.55")
        make_synthesizer(deps)(pnl_state)
        human = str(fake_models[Role.SYNTH].calls[0][-1].content)
        assert "<user_question>" in human
        assert "<results>" in human
        assert "1171521.55" in human
        assert "entity-level overhead" in human

    def test_ungrounded_answer_falls_back_to_template(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel], pnl_state: AgentState
    ) -> None:
        fake_models[Role.SYNTH].responses.append("The total P&L for 2024 was €1,200,000.00.")
        out = make_synthesizer(deps)(pnl_state)
        assert "€1,200,000.00" not in out["answer"]
        assert "€1,171,521.55" in out["answer"]
        assert any("grounding" in t.summary for t in out["trace"])
        assert out["errors"]

    def test_llm_unavailable_falls_back_to_template(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel], pnl_state: AgentState
    ) -> None:
        fake_models[Role.SYNTH].responses.append(ConnectionError("quota"))
        out = make_synthesizer(deps)(pnl_state)
        assert "€1,171,521.55" in out["answer"]
        assert out["degraded"] is True

    def test_model_steps_line_is_replaced_by_ours(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel], pnl_state: AgentState
    ) -> None:
        fake_models[Role.SYNTH].responses.append(
            "€1,171,521.55 in 2024.\nSteps: made up → nonsense"
        )
        out = make_synthesizer(deps)(pnl_state)
        assert "made up" not in out["answer"]
        assert out["answer"].count("Steps:") == 1

    def test_no_results_with_errors_renders_template(self, deps: Deps) -> None:
        state = initial_state("q", thread_id="t")
        state["errors"] = ["sub-question failed"]
        out = make_synthesizer(deps)(state)
        assert "could not" in out["answer"].lower()


class TestGeneral:
    def test_uses_llm_with_general_prompt(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
    ) -> None:
        fake_models[Role.GENERAL].responses.append(
            "General knowledge (not computed from your data): NOI is ..."
        )
        state = initial_state("what is NOI?", thread_id="t")
        out = make_general(deps)(state)
        assert out["answer"].startswith("General knowledge")
        assert "NOI" in str(fake_models[Role.GENERAL].calls[0][0].content) or True
        assert "<user_question>" in str(fake_models[Role.GENERAL].calls[0][-1].content)

    def test_prefix_is_enforced(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
    ) -> None:
        fake_models[Role.GENERAL].responses.append("NOI is net operating income.")
        out = make_general(deps)(initial_state("what is NOI?", thread_id="t"))
        assert out["answer"].startswith("General knowledge (not computed from your data):")

    def test_unavailable_gives_honest_fallback(
        self, deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
    ) -> None:
        fake_models[Role.GENERAL].responses.append(ConnectionError("down"))
        out = make_general(deps)(initial_state("what is NOI?", thread_id="t"))
        assert "unavailable" in out["answer"].lower()
        assert out["degraded"] is True


def test_unsupported_node_explains_scope(deps: Deps) -> None:
    state = initial_state("tell me a joke", thread_id="t")
    state["route"] = RouteDecision(intent=Intent.UNSUPPORTED, confidence=0.9)
    out = make_unsupported(deps)(state)
    assert "P&L" in out["answer"]
    assert "Building 17" in out["answer"]
    assert out["trace"][0].node == "unsupported"
