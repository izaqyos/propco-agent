"""Contract of the public façade used by the UI (and any future API)."""

import pytest

from propco_agent.config import LLMProvider, Settings
from propco_agent.domain.models import DataPolicy, Intent
from propco_agent.graph.deps import Deps
from propco_agent.llm.factory import Role
from propco_agent.llm.fake import ScriptedFakeChatModel
from propco_agent.llm.schemas import ExtractedEntities, RouteDecision
from propco_agent.resolve.periods import PeriodSpec
from propco_agent.service import AskResult, AssetManagerService

pytestmark = pytest.mark.api


@pytest.fixture
def service(deps: Deps) -> AssetManagerService:
    return AssetManagerService(deps)


def script_pnl(
    fake_models: dict[Role, ScriptedFakeChatModel], answer: str = "€1,171,521.55."
) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.PNL, confidence=0.95))
    fake_models[Role.EXTRACTOR].responses.append(
        ExtractedEntities(periods=[PeriodSpec(year=2024, raw="2024")])
    )
    fake_models[Role.SYNTH].responses.append(answer)


def test_ask_returns_answer_trace_and_results(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    script_pnl(fake_models)
    result = service.ask("What was the P&L in 2024?", thread_id="a1")
    assert isinstance(result, AskResult)
    assert result.needs_input is False
    assert result.clarification is None
    assert "€1,171,521.55" in result.answer
    assert [t.node for t in result.trace][:2] == ["guard", "router"]
    assert result.results[0].kind == "pnl"
    assert result.degraded is False
    assert result.thread_id == "a1"
    assert result.elapsed_ms >= 0


def test_ask_with_policy_override(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    script_pnl(fake_models, answer="€682,529.72.")
    result = service.ask("P&L 2024", thread_id="a2", policy=DataPolicy.DEDUP)
    assert result.results[0].policy is DataPolicy.DEDUP
    assert "€682,529.72" in result.answer


def test_clarification_round_trip(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(
        RouteDecision(intent=Intent.CLARIFY, confidence=0.9, clarification="Which period?")
    )
    first = service.ask("p&l", thread_id="a3")
    assert first.needs_input is True
    assert first.clarification == "Which period?"
    assert first.answer == ""
    assert service.pending_clarification("a3") == "Which period?"

    script_pnl(fake_models)
    second = service.resume("2024", thread_id="a3")
    assert second.needs_input is False
    assert "€1,171,521.55" in second.answer
    assert service.pending_clarification("a3") is None


def test_resume_without_pending_interrupt_is_a_fresh_question(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    script_pnl(fake_models)
    result = service.resume("P&L 2024", thread_id="a4")
    assert "€1,171,521.55" in result.answer


def test_threads_are_isolated(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.CLARIFY, confidence=0.9))
    pending = service.ask("hmm", thread_id="t-a")
    assert pending.needs_input is True
    script_pnl(fake_models)
    other = service.ask("P&L 2024", thread_id="t-b")
    assert other.needs_input is False
    assert service.pending_clarification("t-a") is not None
    assert service.pending_clarification("t-b") is None


def test_stream_yields_trace_then_result(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    script_pnl(fake_models)
    events = list(service.stream("P&L 2024", thread_id="a5"))
    *trace, final = events
    assert [e.node for e in trace] == [
        "guard",
        "router",
        "extractor",
        "resolver",
        "analyst_pnl",
        "synthesizer",
    ]  # type: ignore[union-attr]
    assert isinstance(final, AskResult)
    assert "€1,171,521.55" in final.answer


def test_stream_surfaces_clarification(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.ROUTER].responses.append(RouteDecision(intent=Intent.CLARIFY, confidence=0.9))
    final = list(service.stream("hmm", thread_id="a6"))[-1]
    assert isinstance(final, AskResult)
    assert final.needs_input is True
    assert final.clarification


def test_repeated_question_is_served_from_cache(
    service: AssetManagerService, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    script_pnl(fake_models)
    fake_models[Role.SYNTH].responses.append("€1,171,521.55 again.")
    service.ask("P&L 2024", thread_id="a7")
    router_calls = len(fake_models[Role.ROUTER].calls)
    service.ask("P&L 2024", thread_id="a8")
    assert len(fake_models[Role.ROUTER].calls) == router_calls  # router/extractor cached
    assert len(fake_models[Role.SYNTH].calls) == 2  # synthesis is not cached


def test_mermaid(service: AssetManagerService) -> None:
    assert "router" in service.mermaid()


def test_from_settings_builds_everything_for_fake_provider(data_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(_env_file=None, llm_provider=LLMProvider.FAKE, data_path=data_path)
    service = AssetManagerService.from_settings(settings)
    assert service.deps.repo.as_of == "2025-M03"
    assert set(service.deps.models) == set(Role)


def test_dataset_summary_for_ui(service: AssetManagerService) -> None:
    summary = service.dataset_summary()
    assert summary["properties"] == 5
    assert summary["tenants"] == 18
    assert summary["rows"] == 3924
    assert summary["as_of"] == "2025-M03"
    assert summary["months"] == 15
