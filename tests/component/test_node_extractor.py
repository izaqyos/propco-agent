"""Extractor node: LLM entities merged with rule-based gap filling."""

import pytest

from propco_agent.domain.models import LedgerType
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.extractor import make_extractor, merge_entities
from propco_agent.graph.state import initial_state
from propco_agent.llm.factory import Role
from propco_agent.llm.fake import ScriptedFakeChatModel
from propco_agent.llm.schemas import ExtractedEntities
from propco_agent.resolve.metrics import Metric
from propco_agent.resolve.periods import PeriodSpec, RelativePeriod

pytestmark = pytest.mark.component


def run(deps: Deps, text: str) -> dict:  # type: ignore[type-arg]
    return make_extractor(deps)(initial_state(text, thread_id="t"))


class TestMerge:
    def test_llm_fields_win_rules_fill_gaps(self) -> None:
        llm = ExtractedEntities(properties=["Bldg 17"], periods=[PeriodSpec(raw="Q2 2024")])
        rules = ExtractedEntities(
            properties=["Building 17"],
            periods=[PeriodSpec(year=2024, quarter=2, raw="q2 2024")],
            metric=Metric.REVENUE,
            ledger_type=LedgerType.REVENUE,
            top_n=3,
        )
        merged = merge_entities(llm, rules)
        assert merged.properties == ["Bldg 17"]
        assert merged.metric is Metric.REVENUE
        assert merged.ledger_type is LedgerType.REVENUE
        assert merged.top_n == 3
        # the raw-only period from the LLM is completed from the parsed phrase
        assert (merged.periods[0].year, merged.periods[0].quarter) == (2024, 2)
        assert merged.periods[0].raw == "Q2 2024"

    def test_llm_periods_kept_when_complete(self) -> None:
        llm = ExtractedEntities(
            periods=[PeriodSpec(relative=RelativePeriod.THIS_YEAR, raw="this year")]
        )
        rules = ExtractedEntities(periods=[PeriodSpec(year=2024, raw="2024")])
        assert merge_entities(llm, rules).periods == llm.periods

    def test_rules_periods_used_when_llm_found_none(self) -> None:
        rules = ExtractedEntities(periods=[PeriodSpec(year=2024, raw="2024")])
        assert merge_entities(ExtractedEntities(), rules).periods == rules.periods

    def test_raw_only_period_parsed_from_its_own_words(self) -> None:
        llm = ExtractedEntities(periods=[PeriodSpec(raw="same period last year")])
        merged = merge_entities(llm, ExtractedEntities())
        assert merged.periods[0].relative is RelativePeriod.SAME_PERIOD_LAST_YEAR


def test_node_uses_llm_then_merges(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.EXTRACTOR].responses.append(
        ExtractedEntities(tenants=["tenant 7"], periods=[PeriodSpec(raw="Q2 2024")])
    )
    out = run(deps, "revenue for tenant 7 in Q2 2024")
    e = out["extracted"]
    assert e.tenants == ["tenant 7"]
    assert (e.periods[0].year, e.periods[0].quarter) == (2024, 2)
    assert e.metric is Metric.REVENUE  # gap-filled by rules
    assert out["trace"][0].node == "extractor"


def test_node_falls_back_to_rules(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.EXTRACTOR].responses.append(TimeoutError("slow"))
    out = run(deps, "expenses for building 120 in June 2024")
    e = out["extracted"]
    assert e.properties == ["Building 120"]
    assert (e.periods[0].year, e.periods[0].month) == (2024, 6)
    assert e.ledger_type is LedgerType.EXPENSES
    assert out["degraded"] is True


def test_prompt_contains_vocabulary_and_wrapped_question(
    deps: Deps, fake_models: dict[Role, ScriptedFakeChatModel]
) -> None:
    fake_models[Role.EXTRACTOR].responses.append(ExtractedEntities())
    run(deps, "p&l")
    messages = fake_models[Role.EXTRACTOR].calls[0]
    assert "Tenant 1" in str(messages[0].content)
    assert "<user_question>" in str(messages[-1].content)
