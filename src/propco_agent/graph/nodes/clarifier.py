"""Clarifier node: human-in-the-loop via LangGraph ``interrupt``.

Pauses the graph with a question for the user; on resume the reply is folded into the
original question and the graph re-enters at the guard. Bounded by ``MAX_CLARIFY_ROUNDS``.
"""

from __future__ import annotations

from langgraph.types import interrupt

from propco_agent.graph.deps import Deps
from propco_agent.graph.state import AgentState, Node, NodeUpdate, timed
from propco_agent.llm.rules import CLARIFICATION

MAX_CLARIFY_ROUNDS = 2
_GIVE_UP = (
    "I could not work out what to compute after two clarifications. Please ask a single, "
    "specific question, for example: 'total P&L for 2024', 'this quarter vs the same period "
    "last year', 'top 5 tenants', 'details for Building 17' or 'is anything unusual in the numbers?'."
)


def make_clarifier(deps: Deps) -> Node:
    """Build the clarifier node."""
    _ = deps  # no dependencies today; kept for a uniform node signature

    def clarifier(state: AgentState) -> NodeUpdate:
        rounds = state.get("clarify_rounds", 0)
        route = state.get("route")
        question_text = (
            state.get("clarification")
            or (route.clarification if route is not None else None)
            or CLARIFICATION
        )
        with timed("clarifier") as done:
            if rounds >= MAX_CLARIFY_ROUNDS:
                return {
                    "answer": _GIVE_UP,
                    "clarification": None,
                    "trace": [done(f"gave up after {rounds} clarification rounds")],
                }
            reply = str(interrupt({"clarification": question_text})).strip()
            original = state.get("question", "").strip()
            merged = f"{original} — {reply}" if original else reply
            return {
                "question": merged,
                "clarification": None,
                "clarify_rounds": rounds + 1,
                "resolved": None,
                "unresolved": None,
                "trace": [done(f"asked: {question_text[:60]!r}; user replied: {reply[:60]!r}")],
            }

    return clarifier
