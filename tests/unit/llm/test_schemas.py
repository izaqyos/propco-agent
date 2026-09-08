"""Schemas the LLM must fill: strict enough to catch garbage, loose enough for real questions."""

import pytest
from pydantic import ValidationError

from propco_agent.domain.models import Intent, LedgerType
from propco_agent.llm.schemas import ExtractedEntities, RouteDecision
from propco_agent.resolve.metrics import Metric
from propco_agent.resolve.periods import PeriodSpec, RelativePeriod

pytestmark = pytest.mark.unit


class TestRouteDecision:
    def test_minimal(self) -> None:
        d = RouteDecision(intent=Intent.PNL, confidence=0.9)
        assert d.sub_questions == []
        assert d.clarification is None
        assert d.is_compound is False

    def test_compound_when_two_or_more_sub_questions(self) -> None:
        d = RouteDecision(
            intent=Intent.PNL, confidence=0.8, sub_questions=["P&L 2024?", "top tenants?"]
        )
        assert d.is_compound is True

    def test_single_sub_question_is_not_compound(self) -> None:
        assert (
            RouteDecision(intent=Intent.PNL, confidence=0.8, sub_questions=["x"]).is_compound
            is False
        )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RouteDecision(intent=Intent.PNL, confidence=1.5)

    def test_unknown_intent_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouteDecision(intent="weather", confidence=0.5)  # type: ignore[arg-type]

    def test_extra_fields_ignored(self) -> None:
        d = RouteDecision.model_validate({"intent": "pnl", "confidence": 0.5, "note": "x"})
        assert d.intent is Intent.PNL


class TestExtractedEntities:
    def test_defaults_are_empty(self) -> None:
        e = ExtractedEntities()
        assert (e.properties, e.tenants, e.periods) == ([], [], [])
        assert e.metric is None
        assert e.top_n is None

    def test_full(self) -> None:
        e = ExtractedEntities(
            properties=["Bldg 17", "Building 120"],
            periods=[PeriodSpec(relative=RelativePeriod.THIS_YEAR, raw="this year")],
            metric=Metric.PNL,
            ledger_type=LedgerType.REVENUE,
            top_n=5,
        )
        assert e.periods[0].relative is RelativePeriod.THIS_YEAR
        assert e.metric is Metric.PNL

    def test_top_n_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntities(top_n=0)
        with pytest.raises(ValidationError):
            ExtractedEntities(top_n=101)

    def test_json_schema_is_exportable_for_prompts(self) -> None:
        schema = ExtractedEntities.model_json_schema()
        assert "properties" in schema["properties"]
        assert "PeriodSpec" in schema["$defs"]
