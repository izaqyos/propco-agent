"""Row selection from a LedgerFilter."""

import pandas as pd
import pytest

from propco_agent.analytics.filters import apply_filter
from propco_agent.domain.models import LedgerFilter, LedgerType, Period
from tests.helpers.ledger import expense, make_ledger, row

pytestmark = pytest.mark.unit


class TestOnRealLedger:
    def test_empty_filter_keeps_everything(self, ledger: pd.DataFrame) -> None:
        assert len(apply_filter(ledger, LedgerFilter())) == 3924

    def test_property(self, ledger: pd.DataFrame) -> None:
        out = apply_filter(ledger, LedgerFilter(properties=["Building 17"]))
        assert len(out) == 1450
        assert set(out["property_name"]) == {"Building 17"}

    def test_exclude_unallocated(self, ledger: pd.DataFrame) -> None:
        out = apply_filter(ledger, LedgerFilter(include_unallocated=False))
        assert len(out) == 3924 - 581
        assert out["property_name"].notna().all()

    def test_period_uses_month_keys(self, ledger: pd.DataFrame) -> None:
        out = apply_filter(ledger, LedgerFilter(period=Period.quarter(2024, 2)))
        assert len(out) == 1102
        assert set(out["quarter"]) == {"2024-Q2"}

    def test_ledger_type(self, ledger: pd.DataFrame) -> None:
        assert len(apply_filter(ledger, LedgerFilter(ledger_type=LedgerType.REVENUE))) == 3135

    def test_tenant(self, ledger: pd.DataFrame) -> None:
        out = apply_filter(ledger, LedgerFilter(tenants=["Tenant 7"]))
        assert set(out["tenant_name"]) == {"Tenant 7"}


class TestOnSyntheticLedger:
    def test_group_and_category(self) -> None:
        frame = make_ledger(
            row(ledger_group="rental_income", ledger_category="revenue_rent_taxed"),
            row(ledger_group="sales_discounts", ledger_category="rent_discount_taxed"),
            expense(),
        )
        assert len(apply_filter(frame, LedgerFilter(ledger_group="sales_discounts"))) == 1
        assert len(apply_filter(frame, LedgerFilter(ledger_category="bank_charges"))) == 1

    def test_property_filter_implies_no_unallocated_rows(self) -> None:
        frame = make_ledger(row(property_name="Building 17"), expense())
        out = apply_filter(
            frame, LedgerFilter(properties=["Building 17"], include_unallocated=True)
        )
        assert len(out) == 1

    def test_does_not_mutate_input(self) -> None:
        frame = make_ledger(row(), expense())
        apply_filter(frame, LedgerFilter(ledger_type=LedgerType.EXPENSES))
        assert len(frame) == 2
