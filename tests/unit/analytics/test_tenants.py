"""Tenant ranking by revenue with concentration figures."""

import pandas as pd
import pytest

from propco_agent.analytics.tenants import top_tenants
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from tests.helpers.ledger import make_ledger, row

pytestmark = pytest.mark.unit
KW = {"policy": DataPolicy.RAW, "as_of": "2025-M03"}


class TestGolden:
    def test_top_five_2024(self, ledger: pd.DataFrame) -> None:
        ranking = top_tenants(ledger, LedgerFilter(period=Period.year(2024)), n=5, **KW)
        assert [t.tenant for t in ranking.items] == [
            "Tenant 7",
            "Tenant 14",
            "Tenant 11",
            "Tenant 13",
            "Tenant 3",
        ]
        top = ranking.items[0]
        assert top.revenue == 703009.03
        assert top.share_pct == 30.63
        assert top.properties == ["Building 120"]
        assert ranking.items[4].revenue == 159707.57
        assert ranking.total_revenue == 2295528.74
        assert ranking.concentration_top3_pct == 54.28
        assert ranking.period == Period.year(2024)
        assert ranking.kind == "tenant_ranking"

    def test_all_time(self, ledger: pd.DataFrame) -> None:
        ranking = top_tenants(ledger, LedgerFilter(), n=1, **KW)
        assert ranking.items[0].tenant == "Tenant 7"
        assert ranking.items[0].revenue == 880535.66
        assert ranking.total_revenue == 2887652.89
        assert ranking.tenant_count == 18

    def test_n_larger_than_population_returns_all(self, ledger: pd.DataFrame) -> None:
        assert len(top_tenants(ledger, LedgerFilter(), n=50, **KW).items) == 18


class TestSynthetic:
    def test_only_revenue_rows_count(self) -> None:
        frame = make_ledger(
            row(tenant_name="T1", profit=100.0),
            row(tenant_name="T1", ledger_type="expenses", ledger_group="x", profit=-500.0),
            row(tenant_name="T2", profit=50.0),
        )
        ranking = top_tenants(frame, LedgerFilter(), n=5, **KW)
        assert [(t.tenant, t.revenue) for t in ranking.items] == [("T1", 100.0), ("T2", 50.0)]
        assert ranking.total_revenue == 150.0

    def test_property_is_the_most_frequent_one(self) -> None:
        frame = make_ledger(
            row(tenant_name="T1", property_name="B1", profit=1.0),
            row(tenant_name="T1", property_name="B1", profit=1.0),
            row(tenant_name="T1", property_name=None, profit=1.0),
        )
        assert top_tenants(frame, LedgerFilter(), n=1, **KW).items[0].properties == ["B1"]

    def test_no_tenant_revenue_gives_empty_ranking(self) -> None:
        frame = make_ledger(row(tenant_name=None, profit=1.0))
        ranking = top_tenants(frame, LedgerFilter(), n=5, **KW)
        assert ranking.items == []
        assert ranking.total_revenue == 0.0
        assert ranking.concentration_top3_pct == 0.0
