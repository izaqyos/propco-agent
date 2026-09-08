"""Translate a :class:`LedgerFilter` into a row selection."""

from __future__ import annotations

import pandas as pd

from propco_agent.domain.models import LedgerFilter

UNALLOCATED = "unallocated"


def apply_filter(frame: pd.DataFrame, filt: LedgerFilter) -> pd.DataFrame:
    """Return the rows of ``frame`` selected by ``filt`` (a new frame; input untouched)."""
    mask = pd.Series(True, index=frame.index)
    if filt.properties:
        mask &= frame["property_name"].isin(filt.properties)
    elif not filt.include_unallocated:
        mask &= frame["property_name"].notna()
    if filt.tenants:
        mask &= frame["tenant_name"].isin(filt.tenants)
    if filt.period is not None:
        mask &= frame["month"].isin(filt.period.months())
    if filt.ledger_type is not None:
        mask &= frame["ledger_type"] == filt.ledger_type.value
    if filt.ledger_group is not None:
        mask &= frame["ledger_group"] == filt.ledger_group
    if filt.ledger_category is not None:
        mask &= frame["ledger_category"] == filt.ledger_category
    return frame.loc[mask].copy()
