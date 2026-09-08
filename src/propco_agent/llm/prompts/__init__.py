"""Prompt templates as Markdown files, rendered with dataset context.

Templates use ``string.Template`` (``$name``) so JSON braces in examples need no escaping.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from importlib import resources
from string import Template

from pydantic import BaseModel, Field


class PromptName(StrEnum):
    """One template per LLM role."""

    ROUTER = "router"
    EXTRACTOR = "extractor"
    SYNTH = "synth"
    GENERAL = "general"


class PromptContext(BaseModel):
    """Dataset facts injected into every prompt."""

    properties: list[str]
    tenants: list[str]
    as_of: str  # YYYY-MM
    data_min: str  # YYYY-MM
    data_max: str  # YYYY-MM
    currency: str = "EUR"
    extra: dict[str, str] = Field(default_factory=dict)


@cache
def _template(name: PromptName) -> Template:
    package = resources.files("propco_agent.llm.prompts")
    text = package.joinpath(f"{name.value}.md").read_text(encoding="utf-8")
    return Template(text)


def render_prompt(name: PromptName, ctx: PromptContext) -> str:
    """Render the template for ``name`` with ``ctx``. Raises ``KeyError`` on a missing variable."""
    return _template(name).substitute(
        properties=", ".join(ctx.properties),
        tenants=", ".join(ctx.tenants),
        as_of=ctx.as_of,
        data_min=ctx.data_min,
        data_max=ctx.data_max,
        currency=ctx.currency,
        **ctx.extra,
    )
