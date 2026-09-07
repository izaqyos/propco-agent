"""Data policy: RAW keeps every posted row, DEDUP collapses exact duplicates."""

import pytest

from propco_agent.data.policy import apply_policy
from propco_agent.domain.models import DataPolicy
from tests.helpers.ledger import make_ledger, row

pytestmark = pytest.mark.unit


def test_raw_keeps_duplicates() -> None:
    frame = make_ledger(row(profit=10.0), row(profit=10.0), row(profit=5.0))
    assert len(apply_policy(frame, DataPolicy.RAW)) == 3


def test_dedup_collapses_exact_duplicates_only() -> None:
    frame = make_ledger(row(profit=10.0), row(profit=10.0), row(profit=5.0))
    out = apply_policy(frame, DataPolicy.DEDUP)
    assert out["profit"].tolist() == [10.0, 5.0]


def test_dedup_treats_null_property_as_equal() -> None:
    frame = make_ledger(row(property_name=None), row(property_name=None))
    assert len(apply_policy(frame, DataPolicy.DEDUP)) == 1


def test_policy_returns_a_new_frame() -> None:
    frame = make_ledger(row())
    out = apply_policy(frame, DataPolicy.RAW)
    out.loc[0, "profit"] = 999.0
    assert frame.loc[0, "profit"] == 100.0
