"""Dependencies injected into every node: data, settings, models."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from langchain_core.language_models import BaseChatModel

from propco_agent.config import Settings
from propco_agent.data.repository import LedgerRepository
from propco_agent.domain.models import DataPolicy, Period
from propco_agent.llm.factory import Role
from propco_agent.llm.prompts import PromptContext


@dataclass
class Deps:
    """What nodes need. Built once per process; cheap to pass around."""

    repo: LedgerRepository
    settings: Settings
    models: dict[Role, BaseChatModel]

    @property
    def as_of(self) -> str:
        """Anchor for relative periods: settings override, else the data's last month."""
        return self.settings.as_of or self.repo.as_of

    def frame(self, policy: DataPolicy) -> pd.DataFrame:
        """The ledger under ``policy``."""
        return self.repo.frame(policy)

    def prompt_context(self) -> PromptContext:
        """Dataset facts for prompt templates."""
        return PromptContext(
            properties=self.repo.properties,
            tenants=self.repo.tenants,
            as_of=Period.from_data_month(self.as_of).start,
            data_min=Period.from_data_month(self.repo.data_min).start,
            data_max=Period.from_data_month(self.repo.as_of).end,
            currency=self.settings.currency,
        )
