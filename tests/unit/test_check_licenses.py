"""SPDX-aware licence gate: expression splitting and allowlist matching."""

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_licenses.py"
_spec = importlib.util.spec_from_file_location("check_licenses", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
check_licenses = importlib.util.module_from_spec(_spec)
sys.modules["check_licenses"] = check_licenses
_spec.loader.exec_module(check_licenses)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("MIT", ["mit"]),
        ("MPL-2.0 AND (Apache-2.0 OR MIT)", ["mpl-2.0", "apache-2.0", "mit"]),
        ("Apache Software License; BSD License", ["apache software license", "bsd license"]),
        (
            "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
            ["bsd-3-clause", "0bsd", "mit", "zlib", "cc0-1.0"],
        ),
    ],
)
def test_atoms(expression: str, expected: list[str]) -> None:
    assert check_licenses.atoms(expression) == expected


def test_permissive_expressions_pass() -> None:
    for expr in ("MIT", "MPL-2.0 AND (Apache-2.0 OR MIT)", "Apache-2.0 OR BSD-3-Clause", "PSF-2.0"):
        assert check_licenses.disallowed(expr) == []


def test_copyleft_is_flagged() -> None:
    bad = check_licenses.disallowed(
        "Artistic License; GNU General Public License (GPL); GNU General Public License v2 or later (GPLv2+)"
    )
    assert "gnu general public license" in bad
    assert "gpl" in bad
    assert "artistic license" in bad


def test_unknown_is_flagged() -> None:
    assert check_licenses.disallowed("UNKNOWN") == ["unknown"]
