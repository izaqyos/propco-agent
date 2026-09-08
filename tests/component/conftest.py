"""Component-test fixtures: real ledger, fake models, shared Deps."""

from __future__ import annotations

from pathlib import Path

import pytest

from propco_agent.config import LLMProvider, Settings
from propco_agent.data.repository import ParquetLedgerRepository
from propco_agent.graph.deps import Deps
from propco_agent.llm.factory import Role
from propco_agent.llm.fake import ScriptedFakeChatModel


@pytest.fixture(scope="session")
def repo(data_path: Path) -> ParquetLedgerRepository:
    return ParquetLedgerRepository(data_path)


@pytest.fixture
def fake_models() -> dict[Role, ScriptedFakeChatModel]:
    return {role: ScriptedFakeChatModel() for role in Role}


@pytest.fixture
def deps(repo: ParquetLedgerRepository, fake_models: dict[Role, ScriptedFakeChatModel]) -> Deps:
    settings = Settings(_env_file=None, llm_provider=LLMProvider.FAKE)
    return Deps(repo=repo, settings=settings, models=dict(fake_models))
