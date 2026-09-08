"""Guard node: reject input that is not a natural-language question before spending an LLM call."""

from __future__ import annotations

import re

from propco_agent.graph.deps import Deps
from propco_agent.graph.state import AgentState, GuardResult, Node, NodeUpdate, timed

_EXAMPLES = (
    "For example: 'total P&L for 2024', 'this quarter vs the same period last year', "
    "'top tenants', 'details for Building 17'."
)
_CODE_START = re.compile(
    r"^\s*(?:[{\[<]|(?:select|insert|update|delete|with|drop)\b)", re.IGNORECASE
)
_MIN_PRINTABLE_RATIO = 0.7


def make_guard(deps: Deps) -> Node:
    """Build the guard node."""
    max_chars = deps.settings.max_input_chars

    def guard(state: AgentState) -> NodeUpdate:
        with timed("guard") as done:
            text = " ".join(state.get("question", "").split())
            rejection = _reject(text, max_chars)
            if rejection is not None:
                key, message = rejection
                return {
                    "question": text,
                    "guard": GuardResult(ok=False, reason=key),
                    "clarification": message,
                    "trace": [done(f"rejected: {key}")],
                }
            return {"question": text, "guard": GuardResult(ok=True), "trace": [done("ok")]}

    return guard


def _reject(text: str, max_chars: int) -> tuple[str, str] | None:
    if not text:
        return "empty", f"I need a question to work with. {_EXAMPLES}"
    printable = sum(ch.isprintable() for ch in text) / len(text)
    if printable < _MIN_PRINTABLE_RATIO:
        return "unreadable", f"I could not read that message. Please ask in plain text. {_EXAMPLES}"
    if len(text) > max_chars:
        return (
            "too long",
            f"Your message is {len(text)} characters; the limit is {max_chars}. Please shorten it.",
        )
    if _CODE_START.match(text):
        return (
            "not natural language",
            f"That looks like code or structured data. Please ask in natural language. {_EXAMPLES}",
        )
    return None
