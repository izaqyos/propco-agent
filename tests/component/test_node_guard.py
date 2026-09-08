"""Guard node: cheap, deterministic input validation before any LLM call."""

import pytest

from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.guard import make_guard
from propco_agent.graph.state import initial_state

pytestmark = pytest.mark.component


def run(deps: Deps, text: str) -> dict:  # type: ignore[type-arg]
    return make_guard(deps)(initial_state(text, thread_id="t"))


def test_normal_question_passes(deps: Deps) -> None:
    out = run(deps, "What is the total P&L for 2024?")
    assert out["guard"].ok is True
    assert out["trace"][0].node == "guard"


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_is_rejected(deps: Deps, text: str) -> None:
    out = run(deps, text)
    assert out["guard"].ok is False
    assert "empty" in out["guard"].reason
    assert out["clarification"]


def test_too_long_is_rejected(deps: Deps) -> None:
    out = run(deps, "p&l " * 1000)
    assert out["guard"].ok is False
    assert "long" in out["guard"].reason
    assert "2000" in out["clarification"]


@pytest.mark.parametrize(
    "text",
    [
        '{"query": "pnl", "year": 2024}',
        "SELECT sum(profit) FROM ledger WHERE year = 2024",
        "<script>alert(1)</script>",
    ],
)
def test_structured_or_code_input_is_rejected_with_guidance(deps: Deps, text: str) -> None:
    out = run(deps, text)
    assert out["guard"].ok is False
    assert "natural language" in out["clarification"].lower()


def test_binary_garbage_is_rejected(deps: Deps) -> None:
    out = run(deps, "\x00\x01\x02\x03\x04" * 5)
    assert out["guard"].ok is False
    assert "unreadable" in out["guard"].reason


def test_dutch_passes(deps: Deps) -> None:
    assert run(deps, "Wat was de totale winst in 2024?")["guard"].ok is True


def test_question_is_normalised_whitespace(deps: Deps) -> None:
    out = run(deps, "  what   is\nthe p&l  ")
    assert out["question"] == "what is the p&l"
