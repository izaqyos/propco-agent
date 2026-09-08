"""Fail when a *runtime* dependency carries a licence outside the permissive allowlist.

Dev-only tools are excluded (they are not distributed). SPDX expressions such as
``MPL-2.0 AND (Apache-2.0 OR MIT)`` are split into atoms; every atom must be allowed.
Usage: ``uv run python scripts/check_licenses.py``
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

ALLOWED: frozenset[str] = frozenset(
    {
        "mit",
        "mit-0",
        "mit license",
        "mit-cmu",
        "bsd",
        "bsd license",
        "bsd-2-clause",
        "bsd-3-clause",
        "3-clause bsd license",
        "0bsd",
        "apache-2.0",
        "apache 2.0",
        "apache license 2.0",
        "apache software license",
        "isc",
        "isc license",
        "isc license (iscl)",
        "mpl-2.0",
        "mpl 2.0",
        "mozilla public license 2.0",
        "mozilla public license 2.0 (mpl 2.0)",
        "psf-2.0",
        "python software foundation license",
        "python-2.0",
        "zlib",
        "cc0-1.0",
        "the unlicense (unlicense)",
        "unlicense",
        "public domain",
    }
)

_SPLIT = re.compile(r"\s*(?:;|\bAND\b|\bOR\b|\(|\))\s*", re.IGNORECASE)


def atoms(expression: str) -> list[str]:
    """Break a licence string / SPDX expression into lower-cased atoms."""
    return [part.strip().lower() for part in _SPLIT.split(expression) if part.strip()]


def disallowed(expression: str) -> list[str]:
    """Atoms of ``expression`` that are not in the allowlist."""
    return [atom for atom in atoms(expression) if atom not in ALLOWED]


def runtime_packages() -> set[str]:
    """Names of the packages a production install pulls in (no dev extras)."""
    out = subprocess.run(
        ["uv", "export", "--no-dev", "--no-hashes", "--no-emit-project", "--quiet"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    names = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        names.add(re.split(r"[=<>!~\[; ]", line, maxsplit=1)[0].lower())
    return names


def installed_licenses() -> list[dict[str, str]]:
    """``pip-licenses`` output for the current environment."""
    out = subprocess.run(
        ["uv", "run", "pip-licenses", "--from=mixed", "--format=json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows: list[dict[str, str]] = json.loads(out)
    return rows


def main() -> int:
    """Print offenders and return a shell exit code."""
    runtime = runtime_packages()
    offenders = [
        (row["Name"], row["Version"], row["License"], bad)
        for row in installed_licenses()
        if row["Name"].lower() in runtime and (bad := disallowed(row["License"]))
    ]
    checked = sum(1 for row in installed_licenses() if row["Name"].lower() in runtime)
    if offenders:
        for name, version, licence, bad in offenders:
            print(f"DISALLOWED  {name} {version}: {licence}  -> {bad}")
        print(f"{len(offenders)} runtime package(s) with non-permissive licences")
        return 1
    print(f"licences ok: {checked} runtime packages, all permissive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
