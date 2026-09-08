"""Deps wiring and state helpers."""

import pytest

from propco_agent.domain.models import DataPolicy
from propco_agent.graph.deps import Deps
from propco_agent.graph.state import TraceEvent, initial_state, timed

pytestmark = pytest.mark.component


def test_deps_derive_as_of_and_prompt_context(deps: Deps) -> None:
    assert deps.as_of == "2025-M03"
    ctx = deps.prompt_context()
    assert ctx.as_of == "2025-03"
    assert ctx.data_min == "2024-01"
    assert ctx.data_max == "2025-03"
    assert "Building 17" in ctx.properties
    assert ctx.currency == "EUR"


def test_settings_as_of_override_wins(deps: Deps) -> None:
    deps.settings.as_of = "2024-M12"
    assert deps.as_of == "2024-M12"
    assert deps.prompt_context().as_of == "2024-12"


def test_initial_state_defaults() -> None:
    state = initial_state("hi", thread_id="t1", policy=DataPolicy.DEDUP)
    assert state["question"] == "hi"
    assert state["thread_id"] == "t1"
    assert state["policy"] is DataPolicy.DEDUP
    assert state["results"] == []
    assert state["trace"] == []
    assert state["errors"] == []
    assert state["clarify_rounds"] == 0


def test_timed_produces_trace_event() -> None:
    with timed("guard") as done:
        pass
    event = done("ok")
    assert isinstance(event, TraceEvent)
    assert event.node == "guard"
    assert event.summary == "ok"
    assert event.ms >= 0
