"""Helpers shared by LLM-calling nodes."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from propco_agent.graph.deps import Deps
from propco_agent.llm.prompts import PromptName, render_prompt


def system_message(deps: Deps, name: PromptName) -> SystemMessage:
    """The rendered system prompt for a role."""
    return SystemMessage(render_prompt(name, deps.prompt_context()))


def user_message(question: str, extra: str = "") -> HumanMessage:
    """User text delimited as data; ``extra`` carries structured context such as results."""
    body = f"<user_question>\n{question}\n</user_question>"
    if extra:
        body = f"{body}\n{extra}"
    return HumanMessage(body)
