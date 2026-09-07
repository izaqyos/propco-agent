"""Ledger repositories: parquet-backed (real dataset goldens) and in-memory."""

from pathlib import Path

import pytest

from propco_agent.data.repository import (
    InMemoryLedgerRepository,
    LedgerRepository,
    ParquetLedgerRepository,
)
from propco_agent.domain.models import DataPolicy
from tests.helpers.ledger import expense, make_ledger, row

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def repo(data_path: Path) -> ParquetLedgerRepository:
    return ParquetLedgerRepository(data_path)


class TestParquetRepository:
    def test_loads_full_dataset(self, repo: ParquetLedgerRepository) -> None:
        assert repo.frame().shape == (3924, 12)

    def test_dedup_view_row_count(self, repo: ParquetLedgerRepository) -> None:
        assert len(repo.frame(DataPolicy.DEDUP)) == 2177

    def test_as_of_is_last_month_in_data(self, repo: ParquetLedgerRepository) -> None:
        assert repo.as_of == "2025-M03"

    def test_data_min_is_first_month(self, repo: ParquetLedgerRepository) -> None:
        assert repo.data_min == "2024-M01"

    def test_properties_sorted_and_complete(self, repo: ParquetLedgerRepository) -> None:
        assert repo.properties == [
            "Building 120",
            "Building 140",
            "Building 160",
            "Building 17",
            "Building 180",
        ]

    def test_tenants_count(self, repo: ParquetLedgerRepository) -> None:
        assert len(repo.tenants) == 18
        assert repo.tenants[0] == "Tenant 1"

    def test_categories_count(self, repo: ParquetLedgerRepository) -> None:
        assert len(repo.categories) == 29

    def test_frame_is_loaded_once(self, repo: ParquetLedgerRepository) -> None:
        assert repo.frame() is repo.frame()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ParquetLedgerRepository(tmp_path / "nope.parquet").frame()

    def test_satisfies_protocol(self, repo: ParquetLedgerRepository) -> None:
        assert isinstance(repo, LedgerRepository)


class TestInMemoryRepository:
    def test_derives_metadata_from_frame(self) -> None:
        frame = make_ledger(
            row(month="2024-M02", property_name="Building 17", tenant_name="Tenant 8"),
            row(month="2024-M05", property_name="Building 120", tenant_name="Tenant 7"),
            expense(month="2024-M03"),
        )
        repo = InMemoryLedgerRepository(frame)
        assert repo.as_of == "2024-M05"
        assert repo.data_min == "2024-M02"
        assert repo.properties == ["Building 120", "Building 17"]
        assert repo.tenants == ["Tenant 7", "Tenant 8"]

    def test_validates_on_construction(self) -> None:
        from propco_agent.domain.errors import LedgerSchemaError

        with pytest.raises(LedgerSchemaError):
            InMemoryLedgerRepository(make_ledger(row()).drop(columns=["profit"]))
