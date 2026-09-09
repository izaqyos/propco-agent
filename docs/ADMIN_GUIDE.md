# Administrator guide

Running, configuring and operating the app. Deployment recipes are in [DEPLOY.md](DEPLOY.md); this guide covers day-2 operations.

## 1. Components

| Component | Where | State |
|---|---|---|
| Streamlit app | one process, port 8501 | per-session chat history |
| LangGraph service | inside the app process | in-memory checkpointer (threads) and node cache |
| Ledger | `data/amiio.parquet`, loaded once at start | read-only |
| Language model | Gemini (HTTPS), Ollama (loopback or sidecar), or fake | none |

Everything lives in one process. Restarting it clears conversations and the cache; the ledger and configuration are files.

## 2. Configuration

All settings are `PROPCO_*` environment variables; `.env` is read locally and Streamlit secrets are bridged in the cloud. Reference: `.env.example`. The ones that matter operationally:

| Variable | Default | Notes |
|---|---|---|
| `PROPCO_LLM_PROVIDER` | `gemini` | `gemini` needs `GOOGLE_API_KEY`; `ollama` needs a reachable server; `fake` answers from rules and templates only |
| `PROPCO_GEMINI_MODEL_SMALL` / `_LARGE` | `gemini-2.5-flash-lite` / `gemini-2.5-flash` | routing+extraction / prose. Any current Flash id works |
| `PROPCO_OLLAMA_BASE_URL`, `PROPCO_OLLAMA_MODEL` | `http://localhost:11434`, `qwen3.5:9b` | the model must support tools; thinking is disabled by the client |
| `PROPCO_DATA_PATH` | `data/amiio.parquet` | any parquet with the same columns |
| `PROPCO_DATA_POLICY` | `raw` | default view; users can switch per session |
| `PROPCO_AS_OF` | last month in data | override the anchor for relative periods, e.g. `2024-M12` |
| `PROPCO_CURRENCY` | `EUR` | formatting only |
| `PROPCO_LLM_TIMEOUT_S`, `PROPCO_LLM_MAX_RETRIES` | `60`, `2` | per call; schema retries and SDK retries |
| `PROPCO_MAX_INPUT_CHARS`, `PROPCO_RECURSION_LIMIT` | `2000`, `25` | hard bounds |
| `PROPCO_LOG_JSON` | `false` (`true` in Docker) | JSON lines on stdout |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | unset | opt-in tracing; nothing else to configure |

Settings are read once at process start. Change → restart.

## 3. Secrets

1. The Gemini key is read from the environment (`GOOGLE_API_KEY`, or `GEMINI_API_KEY`) by the Google SDK. It is never stored on a settings object, never logged, never written to disk by the app.
2. Local: `.env` (gitignored). Docker: `--env-file .env` or an orchestrator secret. Streamlit Cloud: the app's Secrets panel.
3. Rotation: create the new key, update the secret, restart (Streamlit Cloud restarts on secret change), then revoke the old key. There is no in-app cache of the key.
4. A pre-commit hook blocks common key patterns from being committed; `git grep -iE "sk-|api_key\s*="` on the repository should only hit `.env.example` and docs.

## 4. Health and monitoring

1. Health endpoint: `GET /_stcore/health` → `ok`. Used by the Docker `HEALTHCHECK` and the CI probe.
2. Logs: one `turn` record per question (`thread_id`, `request_id`, `intent`, `needs_input`, `degraded`, `elapsed_ms`, `nodes`, `results`, `errors`), plus `node` records at debug level. No question or answer text is logged.
3. What to alert on: a rising share of `degraded=true` (provider down or out of quota), `errors>0` on many turns, `elapsed_ms` p95 well above 15 s with Gemini (provider latency), and process restarts (memory).
4. Tracing: set `LANGSMITH_TRACING=true` and the key to see every prompt and model reply per run in LangSmith. Prompts contain user text; treat the tracing project accordingly.

## 5. Capacity and quotas

1. One question costs three model calls (two on the small model, one on the large); a repeated identical question costs one (router and extractor cached for an hour); general-knowledge and out-of-scope questions cost two and one.
2. Gemini free tier: separate per-model buckets, roughly 10–15 requests per minute and a daily cap; check the live values in Google AI Studio. Exhausted quota shows as HTTP 429 → SDK retries → degraded answers. Move to a paid tier or lower the demo load; the app needs no change.
3. Memory: the process holds the ledger (a few MB), the checkpointer (every thread's state until restart) and the cache. For a demo audience this stays far under 1 GB; for continuous use restart daily or swap in the Postgres checkpointer (see ARCHITECTURE.md §9).
4. Concurrency: sub-questions of a compound request run in parallel; users are served by Streamlit's per-session threads sharing one service. Ollama serialises requests on one GPU — fine for a few users, not for many.

## 6. Data

1. Replacing the ledger: same twelve columns (`entity_name, property_name, tenant_name, ledger_type, ledger_group, ledger_category, ledger_code, ledger_description, month, quarter, year, profit`), `month` as `YYYY-Mmm`. The schema check runs at load and refuses anything else with a clear message. Property and tenant names, ledger groups and categories are read from the data and injected into prompts automatically.
2. Anchor: with new data the default `as_of` moves to the new last month. Set `PROPCO_AS_OF` only to pin it.
3. The parquet is baked into the Docker image; mount a volume over `/app/data` to change it without rebuilding.

## 7. Model changes

1. Different Gemini model: change the two model variables and restart. Run `make eval` (`PROPCO_LLM_PROVIDER=gemini`) and compare with `docs/EVAL.md` before switching a live deployment: intents, grounding rate, latency.
2. Different local model: must support tool/JSON output; keep `reasoning=False` semantics (the client sets it). Run `scripts/smoke_llm.py` first — it shows how well the model fills the extraction schema.
3. Prompts live in `src/propco_agent/llm/prompts/*.md`. After any change run the unit tests (they check delimiters, intents and few-shot presence) and the live eval.

## 8. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Every answer shows the degraded notice | provider unreachable, missing key, or quota | check `GOOGLE_API_KEY` / Ollama; look for `router: ...` in the turn's `errors`; test the key with `scripts/smoke_llm.py` |
| App fails at start with `LedgerSchemaError` | data file does not match the contract | fix the columns or point `PROPCO_DATA_PATH` at a valid file |
| `GOOGLE_API_KEY ... is not set` | provider is `gemini` without a key | set the key or switch `PROPCO_LLM_PROVIDER` |
| Answers take 20–90 s on Ollama | thinking mode enabled by a custom client, or a large model | keep the shipped client; use a 7–9B instruct model |
| A question loops asking for clarification | two rounds then it stops by design | ask a single specific question |
| Numbers differ between two users | one uses `dedup`, the other `raw` | the policy is per session; see the sidebar |
| Streamlit Cloud shows a wake-up page | app slept after 12 h idle | wait 20–40 s; open the URL before a demo |
| Memory grows over days | in-memory checkpointer and cache | restart; or move to a persistent checkpointer |

## 9. Routine tasks

| Task | Command |
|---|---|
| Run locally | `make run` |
| Full quality gate | `make check` |
| Licence check | `make licenses` |
| Live evaluation | `PROPCO_LLM_PROVIDER=gemini make eval` (or `ollama`) |
| Browser smoke | `make e2e-browser` |
| Build and run image | `make docker-build && make docker-run` |
| Regenerate the graph diagram | see `docs/diagrams/graph.md` |
| Dependency update | edit `pyproject.toml`, `uv lock`, run `make check` and `make licenses` |
