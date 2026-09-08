"""A chat model that replays a script. Deterministic, offline, records what it was asked.

Scripted responses may be: a ``str`` (returned as message content), a pydantic model
(serialised to JSON, or returned as the parsed object in structured mode), a ``dict`` /
JSON ``str`` (validated against the schema in structured mode), or an ``Exception``
(raised, to simulate transport failures).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field, ValidationError


class ScriptExhaustedError(RuntimeError):
    """The fake was asked for more responses than were scripted."""


class ScriptedFakeChatModel(BaseChatModel):
    """Replays ``responses`` in order and records every call in ``calls``."""

    responses: list[Any] = Field(default_factory=list)
    keyed: dict[str, Any] = Field(default_factory=dict)  # substring of last message -> response
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        response = self._next(messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=_as_text(response)))]
        )

    def with_structured_output(  # type: ignore[override]
        self, schema: type[BaseModel], *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[Any, Any]:
        """Mimic LangChain's structured output contract on top of the script."""

        def run(messages: Any) -> Any:
            coerced = list(_as_messages(messages))
            self.calls.append(coerced)
            response = self._next(coerced)
            raw = _as_text(response)
            parsed: BaseModel | None = None
            error: Exception | None = None
            if isinstance(response, schema):
                parsed = response
            else:
                try:
                    parsed = (
                        schema.model_validate_json(response)
                        if isinstance(response, str)
                        else schema.model_validate(response)
                    )
                except ValidationError as exc:
                    error = exc
            if include_raw:
                return {"raw": AIMessage(content=raw), "parsed": parsed, "parsing_error": error}
            if error is not None:
                raise error
            return parsed

        return RunnableLambda(run)

    def _next(self, messages: Sequence[BaseMessage] | None = None) -> Any:
        """Keyed response (longest matching key wins, reusable) else the next queued one."""
        if messages and self.keyed:
            last = str(messages[-1].content)
            for key in sorted(self.keyed, key=len, reverse=True):
                if key in last:
                    return _raise_or_return(self.keyed[key])
        if not self.responses:
            raise ScriptExhaustedError("no scripted responses left")
        return _raise_or_return(self.responses.pop(0))


def _raise_or_return(response: Any) -> Any:
    if isinstance(response, BaseException):
        raise response
    return response


def _as_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, BaseModel):
        return response.model_dump_json()
    return json.dumps(response)


def _as_messages(messages: Any) -> Sequence[BaseMessage]:
    if isinstance(messages, BaseMessage):
        return [messages]
    if isinstance(messages, str):
        from langchain_core.messages import HumanMessage

        return [HumanMessage(messages)]
    if hasattr(messages, "to_messages"):
        result: Sequence[BaseMessage] = messages.to_messages()
        return result
    return list(messages)
