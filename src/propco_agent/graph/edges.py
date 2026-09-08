"""Conditional edges: pure functions from state to the next node name (or ``Send`` fan-out)."""

from __future__ import annotations

from langgraph.graph import END
from langgraph.types import Send

from propco_agent.domain.models import DataPolicy, Intent
from propco_agent.graph.nodes.analysts import ANALYST_BY_INTENT
from propco_agent.graph.nodes.compound import SUB_FAIL, SUB_QUESTION
from propco_agent.graph.state import AgentState

_NON_DATA = {
    Intent.CLARIFY: "clarifier",
    Intent.UNSUPPORTED: "unsupported",
    Intent.GENERAL_KNOWLEDGE: "general",
}


def after_guard(state: AgentState) -> str:
    """Valid input goes to the router; anything else asks the user."""
    return "router" if state["guard"].ok else "clarifier"


def after_router(state: AgentState) -> str | list[Send]:
    """Dispatch by intent; compound questions fan out one ``Send`` per sub-question."""
    route = state["route"]
    if route.intent in _NON_DATA:
        return _NON_DATA[route.intent]
    if route.is_compound:
        return [
            Send(
                SUB_QUESTION,
                {
                    "question": sub,
                    "thread_id": state.get("thread_id", "sub"),
                    "policy": state.get("policy", DataPolicy.RAW),
                },
            )
            for sub in route.sub_questions
        ]
    return "extractor"


def after_router_sub(state: AgentState) -> str:
    """Inside the subgraph only data intents are computable."""
    return SUB_FAIL if state["route"].intent in _NON_DATA else "extractor"


def after_resolver(state: AgentState) -> str:
    """Resolved queries go to their analyst; unresolved ones ask the user."""
    if state.get("unresolved") is not None:
        return "clarifier"
    return ANALYST_BY_INTENT[state["route"].intent]


def after_resolver_sub(state: AgentState) -> str:
    """Subgraph variant: unresolved sub-questions are reported, not asked."""
    if state.get("unresolved") is not None:
        return SUB_FAIL
    return ANALYST_BY_INTENT[state["route"].intent]


def after_clarifier(state: AgentState) -> str:
    """A final answer ends the run; otherwise the enriched question re-enters at the guard."""
    return END if state.get("answer") else "guard"
