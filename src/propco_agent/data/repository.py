"""Ledger repositories.

``LedgerRepository`` is the seam between analytics and storage: the parquet file today, a
CSV, DuckDB or an API tomorrow. Frames returned by :meth:`frame` are shared and must be
treated as read-only by callers.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from propco_agent.data.policy import apply_policy
from propco_agent.data.schema import validate_ledger
from propco_agent.domain.models import DataPolicy


@runtime_checkable
class LedgerRepository(Protocol):
    """Read-only access to the validated ledger plus its metadata."""

    def frame(self, policy: DataPolicy = DataPolicy.RAW) -> pd.DataFrame:
        """The validated ledger under ``policy``."""
        ...

    @property
    def as_of(self) -> str:
        """Last month present in the data, e.g. ``2025-M03``."""
        ...

    @property
    def data_min(self) -> str:
        """First month present in the data."""
        ...

    @property
    def properties(self) -> list[str]:
        """Sorted canonical property names."""
        ...

    @property
    def tenants(self) -> list[str]:
        """Sorted canonical tenant names."""
        ...

    @property
    def categories(self) -> list[str]:
        """Sorted ledger categories."""
        ...


class _FrameRepository:
    """Shared metadata/caching over a validated frame supplied by a subclass."""

    def _load(self) -> pd.DataFrame:  # pragma: no cover - abstract hook
        raise NotImplementedError

    @cached_property
    def _raw(self) -> pd.DataFrame:
        return validate_ledger(self._load())

    @cached_property
    def _dedup(self) -> pd.DataFrame:
        return apply_policy(self._raw, DataPolicy.DEDUP)

    def frame(self, policy: DataPolicy = DataPolicy.RAW) -> pd.DataFrame:
        """The validated ledger under ``policy`` (cached per policy)."""
        return self._dedup if policy is DataPolicy.DEDUP else self._raw

    @property
    def as_of(self) -> str:
        """Last month present in the data."""
        return str(self._raw["month"].max())

    @property
    def data_min(self) -> str:
        """First month present in the data."""
        return str(self._raw["month"].min())

    @property
    def properties(self) -> list[str]:
        """Sorted canonical property names."""
        return self._sorted_unique("property_name")

    @property
    def tenants(self) -> list[str]:
        """Sorted canonical tenant names (natural order: Tenant 1, Tenant 2, ...)."""
        return sorted(self._sorted_unique("tenant_name"), key=_natural_key)

    @property
    def categories(self) -> list[str]:
        """Sorted ledger categories."""
        return self._sorted_unique("ledger_category")

    def _sorted_unique(self, column: str) -> list[str]:
        return sorted(str(v) for v in self._raw[column].dropna().unique())


class ParquetLedgerRepository(_FrameRepository):
    """Ledger backed by a parquet file, loaded and validated once."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _load(self) -> pd.DataFrame:
        if not self._path.exists():
            raise FileNotFoundError(f"ledger file not found: {self._path}")
        return pd.read_parquet(self._path)


class InMemoryLedgerRepository(_FrameRepository):
    """Ledger backed by an in-memory frame; validated eagerly. Intended for tests."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._source = frame
        _ = self._raw  # validate now so bad fixtures fail at construction

    def _load(self) -> pd.DataFrame:
        return self._source


def _natural_key(value: str) -> tuple[str, int]:
    head, _, tail = value.rpartition(" ")
    return (head, int(tail)) if tail.isdigit() else (value, 0)
