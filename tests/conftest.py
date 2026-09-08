"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def data_path() -> Path:
    """Path to the real assignment dataset."""
    return REPO_ROOT / "data" / "amiio.parquet"


@pytest.fixture(scope="session")
def ledger(data_path: Path) -> pd.DataFrame:
    """The real ledger, validated, RAW policy. Shared and read-only."""
    from propco_agent.data.repository import ParquetLedgerRepository

    return ParquetLedgerRepository(data_path).frame()


@pytest.fixture(scope="session")
def ledger_dedup(data_path: Path) -> pd.DataFrame:
    """The real ledger under the DEDUP policy."""
    from propco_agent.data.repository import ParquetLedgerRepository
    from propco_agent.domain.models import DataPolicy

    return ParquetLedgerRepository(data_path).frame(DataPolicy.DEDUP)
