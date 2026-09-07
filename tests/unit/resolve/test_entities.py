"""Fuzzy resolution of property and tenant mentions to canonical dataset names."""

import pytest

from propco_agent.resolve.entities import normalize_mention, resolve_property, resolve_tenant

pytestmark = pytest.mark.unit

PROPERTIES = ["Building 120", "Building 140", "Building 160", "Building 17", "Building 180"]
TENANTS = [f"Tenant {i}" for i in range(1, 19)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bldg #17", "building 17"),
        ("BUILDING  17", "building 17"),
        ("bldg. 120", "building 120"),
        ("building no. 140", "building 140"),
        ("Tenant  7", "tenant 7"),
        ("the asset at building 17", "building 17"),
    ],
)
def test_normalize_mention(raw: str, expected: str) -> None:
    assert normalize_mention(raw) == expected


class TestResolveProperty:
    @pytest.mark.parametrize(
        "mention", ["Building 17", "building 17", "Bldg 17", "bldg #17", "the building 17 asset"]
    )
    def test_variants_resolve_to_canonical(self, mention: str) -> None:
        match = resolve_property(mention, PROPERTIES)
        assert match.match == "Building 17"
        assert match.score >= 90

    def test_number_is_decisive_not_prefix(self) -> None:
        # "17" must not drift to 170-ish or 120 because of the shared "Building" prefix
        assert resolve_property("17", PROPERTIES).match == "Building 17"
        assert resolve_property("180", PROPERTIES).match == "Building 180"

    def test_unknown_number_gives_no_match_but_suggestions(self) -> None:
        match = resolve_property("Building 12", PROPERTIES)
        assert match.match is None
        assert "Building 120" in match.suggestions
        assert len(match.suggestions) <= 3

    def test_street_address_is_unresolved_with_all_candidates(self) -> None:
        match = resolve_property("123 Main St", PROPERTIES)
        assert match.match is None
        assert match.suggestions == PROPERTIES[:3]

    def test_empty_mention(self) -> None:
        match = resolve_property("", PROPERTIES)
        assert match.match is None
        assert match.score == 0

    def test_result_echoes_query(self) -> None:
        assert resolve_property("Bldg 17", PROPERTIES).query == "Bldg 17"


class TestResolveTenant:
    def test_exact(self) -> None:
        assert resolve_tenant("Tenant 7", TENANTS).match == "Tenant 7"

    def test_number_disambiguates_1_from_10_to_18(self) -> None:
        assert resolve_tenant("tenant 1", TENANTS).match == "Tenant 1"
        assert resolve_tenant("tenant 18", TENANTS).match == "Tenant 18"

    def test_unknown_tenant(self) -> None:
        match = resolve_tenant("Acme Corp", TENANTS)
        assert match.match is None
        assert len(match.suggestions) == 3
