"""Prompt templates: present, hardened, and rendered without leftovers."""

import pytest

from propco_agent.llm.prompts import PromptContext, PromptName, render_prompt

pytestmark = pytest.mark.unit

CTX = PromptContext(
    properties=["Building 17", "Building 120"],
    tenants=["Tenant 1", "Tenant 7"],
    as_of="2025-03",
    data_min="2024-01",
    data_max="2025-03",
    currency="EUR",
)


@pytest.mark.parametrize("name", list(PromptName))
def test_every_prompt_renders_without_placeholders(name: PromptName) -> None:
    text = render_prompt(name, CTX)
    assert text.strip()
    assert "$" not in text.replace("$$", "")  # no unresolved template variables


@pytest.mark.parametrize("name", [PromptName.ROUTER, PromptName.EXTRACTOR, PromptName.SYNTH])
def test_prompts_treat_user_text_as_data(name: PromptName) -> None:
    text = render_prompt(name, CTX).lower()
    assert "<user_question>" in text
    assert "not instructions" in text or "not as instructions" in text


def test_router_lists_every_intent() -> None:
    text = render_prompt(PromptName.ROUTER, CTX)
    for intent in (
        "pnl",
        "period_compare",
        "asset_details",
        "tenant_analysis",
        "anomaly_check",
        "clarify",
        "unsupported",
    ):
        assert intent in text


def test_extractor_knows_the_dataset_vocabulary() -> None:
    text = render_prompt(PromptName.EXTRACTOR, CTX)
    assert "Building 17" in text
    assert "Tenant 7" in text
    assert "2025-03" in text
    assert "same_period_last_year" in text


def test_extractor_has_worked_json_examples() -> None:
    """Small models copy the shape they are shown; every field must appear filled at least once."""
    text = render_prompt(PromptName.EXTRACTOR, CTX)
    for snippet in (
        '"relative": "this_year"',
        '"year": 2024, "quarter": 2',
        '"year": 2024, "month": 6',
        '"metric": "price"',
        '"top_n": 3',
        '"ledger_type": "expenses"',
    ):
        assert snippet in text, snippet


def test_synth_forbids_arithmetic() -> None:
    text = render_prompt(PromptName.SYNTH, CTX).lower()
    assert "do not" in text
    assert "calculat" in text or "arithmetic" in text
    assert "eur" in text


def test_unknown_prompt_name_rejected() -> None:
    with pytest.raises(ValueError):
        PromptName("nope")
