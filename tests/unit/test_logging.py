"""Structured logging: JSON or console, request ids bound per turn, nothing sensitive."""

import json
import logging

import pytest
import structlog

from propco_agent.logging import bind_request, configure_logging, get_logger, new_request_id

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def test_json_logs_are_single_line_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json_output=True, level="INFO")
    get_logger("test").info("hello", node="router", ms=12.5)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "hello"
    assert record["node"] == "router"
    assert record["ms"] == 12.5
    assert record["level"] == "info"
    assert "timestamp" in record


def test_console_logs_are_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json_output=False, level="INFO")
    get_logger("test").info("hello", node="router")
    out = capsys.readouterr().out
    assert "hello" in out
    assert "node" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])


def test_request_id_is_bound_to_every_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json_output=True, level="INFO")
    with bind_request(thread_id="t1", request_id="r-123"):
        get_logger("test").info("inside")
    get_logger("test").info("outside")
    inside, outside = (
        json.loads(line) for line in capsys.readouterr().out.strip().splitlines()[-2:]
    )
    assert inside["request_id"] == "r-123"
    assert inside["thread_id"] == "t1"
    assert "request_id" not in outside


def test_new_request_id_is_short_and_unique() -> None:
    a, b = new_request_id(), new_request_id()
    assert a != b
    assert len(a) == 12


def test_level_filters(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json_output=True, level="WARNING")
    get_logger("test").info("dropped")
    get_logger("test").warning("kept")
    out = capsys.readouterr().out
    assert "dropped" not in out
    assert "kept" in out


def test_configure_is_idempotent() -> None:
    configure_logging(json_output=True, level="INFO")
    configure_logging(json_output=True, level="INFO")
    assert logging.getLogger().level == logging.INFO
