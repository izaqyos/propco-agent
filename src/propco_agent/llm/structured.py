"""Structured output that survives imperfect models.

``invoke_structured`` asks the model for a pydantic object; when the reply does not validate,
the validation error is fed back and the model gets another try. Transport failures and
exhausted retries surface as :class:`LLMUnavailableError` so callers can degrade gracefully.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from propco_agent.domain.errors import LLMUnavailableError

_FEEDBACK = (
    "Your previous reply did not match the required schema. Validation error:\n{error}\n"
    "Reply again with only a JSON object that satisfies the schema."
)


def invoke_structured[T: BaseModel](
    model: BaseChatModel, schema: type[T], messages: Sequence[BaseMessage], *, max_retries: int = 2
) -> T:
    """Return a validated ``schema`` instance or raise :class:`LLMUnavailableError`."""
    runnable = model.with_structured_output(schema, include_raw=True)
    history: list[BaseMessage] = list(messages)
    attempts = max_retries + 1
    last_error: Exception | None = None

    for _ in range(attempts):
        try:
            output: dict[str, Any] = runnable.invoke(history)  # type: ignore[assignment]
        except Exception as exc:
            raise LLMUnavailableError(f"{type(exc).__name__}: {exc}") from exc
        parsed = output.get("parsed")
        if isinstance(parsed, schema):
            return parsed
        last_error = output.get("parsing_error") or ValueError("model returned no parsable object")
        history = [*history, output["raw"], HumanMessage(_FEEDBACK.format(error=last_error))]

    raise LLMUnavailableError(
        f"structured output failed after {attempts} attempts: {last_error}"
    ) from last_error
