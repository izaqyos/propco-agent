"""Render a live-eval JSON report (tests/eval/reports/*.json) as a Markdown table.

Usage: ``uv run python scripts/eval_report.py tests/eval/reports/ollama_2026-09-08T0230_full.json``
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def render(path: Path) -> str:
    """Markdown summary + per-question table for one report."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    answered = [r for r in rows if r["result_kinds"] and not r["needs_input"]]
    grounded = sum(1 for r in answered if r["llm_answer_grounded"])
    mean_s = statistics.mean(r["seconds"] for r in rows)
    lines = [
        f"Report: `{path.name}` — {len(rows)} questions, mean {mean_s:.1f} s per question, "
        f"{grounded}/{len(answered)} model-written answers passed the grounding check, "
        f"{sum(r['degraded'] for r in rows)} degraded turns.",
        "",
        "| # | Question | Intent | Result | Seconds | LLM prose | Key figure in answer |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, start=1):
        outcome = "clarification" if r["needs_input"] else ", ".join(r["result_kinds"]) or "text"
        prose = (
            "grounded"
            if r["llm_answer_grounded"]
            else ("—" if not r["result_kinds"] else "templated")
        )
        text = (r["text"] or "").replace("\n", " ")
        first_line = text.split(" | ")[0][:110]
        lines.append(
            f"| {i} | {r['question']} | {r['intent']} | {outcome} | {r['seconds']} | {prose} | {first_line} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(Path(sys.argv[1])))
