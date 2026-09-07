"""Duplicate-row policy.

The ledger has no transaction id, so an exact duplicate row cannot be told apart from a
legitimate repeated posting. RAW (default) trusts the ledger as posted; DEDUP is an
explicit alternative view. See docs/ASSUMPTIONS.md.
"""

from __future__ import annotations

import pandas as pd

from propco_agent.domain.models import DataPolicy


def apply_policy(frame: pd.DataFrame, policy: DataPolicy) -> pd.DataFrame:
    """Return a new frame according to ``policy``. Never mutates the input."""
    if policy is DataPolicy.DEDUP:
        return frame.drop_duplicates().reset_index(drop=True)
    return frame.copy()
