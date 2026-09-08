"""Bridge Streamlit secrets into the environment before settings are read.

Streamlit Community Cloud exposes secrets via ``st.secrets``; the Google SDK and
``pydantic-settings`` read the environment. Only known keys are copied and existing
environment values win, so local ``.env`` files behave the same everywhere.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

BRIDGED_PREFIXES: tuple[str, ...] = ("PROPCO_",)
BRIDGED_KEYS: frozenset[str] = frozenset(
    {
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "LANGSMITH_API_KEY",
        "LANGSMITH_TRACING",
        "LANGSMITH_PROJECT",
    }
)


def bridge_secrets(secrets: Mapping[str, Any], environ: dict[str, str] | None = None) -> list[str]:
    """Copy eligible ``secrets`` into ``environ`` (default ``os.environ``). Returns the keys set."""
    target = os.environ if environ is None else environ
    copied: list[str] = []
    for key, value in secrets.items():
        if not isinstance(key, str) or key in target:
            continue
        if key in BRIDGED_KEYS or key.startswith(BRIDGED_PREFIXES):
            target[key] = str(value)
            copied.append(key)
    return copied
