"""Domain error hierarchy. Every error raised by propco_agent derives from PropcoError."""

from __future__ import annotations


class PropcoError(Exception):
    """Base class for all application errors."""


class LedgerSchemaError(PropcoError):
    """The ledger frame does not match the expected schema."""


class UnknownEntityError(PropcoError):
    """A property, tenant or period could not be resolved against the dataset."""

    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.suggestions: list[str] = list(suggestions or [])


class UnsupportedMetricError(PropcoError):
    """The requested metric is not present in the dataset (e.g. price, appraisal date)."""


class LLMUnavailableError(PropcoError):
    """The configured LLM could not be reached or kept failing after retries."""
