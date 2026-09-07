# propco-agent

LangGraph multi-agent assistant for real-estate asset management. Natural-language questions over a property ledger (P&L, period comparisons, tenant analysis, anomaly detection) with a Streamlit chat UI.

Status: work in progress. Full README (setup, architecture, LangGraph workflow, challenges) lands with the first release.

## Quick start

```bash
uv sync --all-extras
cp .env.example .env          # defaults to local Ollama, qwen3.5:9b
make check                    # ruff + mypy + tests with coverage gate
make run                      # http://localhost:8501
```
