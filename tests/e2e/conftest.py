"""Streamlit AppTest fixtures. The app runs against the fake provider with no scripted responses,
so every LLM call degrades to rules/templates: fully deterministic end-to-end runs."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from propco_agent.config import reset_settings

APP = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in [k for k in os.environ if k.startswith("PROPCO_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROPCO_LLM_PROVIDER", "fake")
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    return at
