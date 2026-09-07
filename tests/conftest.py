"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def data_path() -> Path:
    """Path to the real assignment dataset."""
    return REPO_ROOT / "data" / "amiio.parquet"
