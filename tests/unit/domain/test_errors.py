"""Error hierarchy: every domain error is a PropcoError."""

import pytest

from propco_agent.domain.errors import (
    LedgerSchemaError,
    LLMUnavailableError,
    PropcoError,
    UnknownEntityError,
    UnsupportedMetricError,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "exc_type", [LedgerSchemaError, UnknownEntityError, UnsupportedMetricError, LLMUnavailableError]
)
def test_domain_errors_share_base(exc_type: type[Exception]) -> None:
    assert issubclass(exc_type, PropcoError)
    assert issubclass(exc_type, Exception)


def test_unknown_entity_error_carries_suggestions() -> None:
    err = UnknownEntityError(
        "no property '123 Main St'", suggestions=["Building 17", "Building 120"]
    )
    assert err.suggestions == ["Building 17", "Building 120"]
    assert "123 Main St" in str(err)


def test_unknown_entity_error_defaults_to_no_suggestions() -> None:
    assert UnknownEntityError("x").suggestions == []
