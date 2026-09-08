"""What the LLM is asked to produce. Kept small: the model classifies and extracts, code decides."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from propco_agent.domain.models import Intent, LedgerType
from propco_agent.resolve.metrics import Metric
from propco_agent.resolve.periods import PeriodSpec


class RouteDecision(BaseModel):
    """Router output: what kind of request this is."""

    model_config = ConfigDict(extra="ignore")

    intent: Intent
    confidence: float = Field(ge=0, le=1, description="0..1, how sure the router is")
    sub_questions: list[str] = Field(
        default_factory=list,
        description="For compound requests: each independent question, self-contained.",
    )
    clarification: str | None = Field(
        default=None, description="When intent is clarify: the question to ask the user."
    )
    reasoning: str = Field(default="", description="One short sentence, shown in the trace.")

    @property
    def is_compound(self) -> bool:
        """Two or more independent sub-questions."""
        return len(self.sub_questions) >= 2


class ExtractedEntities(BaseModel):
    """Extractor output: the mentions in the question, verbatim, before resolution."""

    model_config = ConfigDict(extra="ignore")

    properties: list[str] = Field(default_factory=list, description="Property mentions as written")
    tenants: list[str] = Field(default_factory=list, description="Tenant mentions as written")
    periods: list[PeriodSpec] = Field(default_factory=list, description="Time references")
    metric: Metric | None = Field(default=None, description="What is being asked for")
    ledger_type: LedgerType | None = None
    ledger_group: str | None = None
    ledger_category: str | None = None
    top_n: int | None = Field(default=None, ge=1, le=100, description="'top 3 tenants' -> 3")
