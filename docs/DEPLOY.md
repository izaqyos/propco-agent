# Deployment

Three ways to run it. Same code, same settings; only the LLM provider and the host change.

## 1. Local, offline (Ollama)

1. Install [Ollama](https://ollama.com) and pull the model: `ollama pull qwen3.5:9b`.
2. `cp .env.example .env`, set `PROPCO_LLM_PROVIDER=ollama`.
3. `uv sync --all-extras && make run` → http://localhost:8501.

Notes.
1. `reasoning=False` is set on the Ollama client. With thinking on, qwen-class models spend 20–90 s per structured call; with it off, 5–8 s per question end to end.
2. First question after start is slower (model load).

## 2. Local, Gemini

1. Create a key in Google AI Studio and put it in `.env` as `GOOGLE_API_KEY=...` (the file is gitignored; never commit it).
2. `PROPCO_LLM_PROVIDER=gemini`. Defaults: `gemini-2.5-flash-lite` for routing and extraction, `gemini-2.5-flash` for writing. Override with `PROPCO_GEMINI_MODEL_SMALL` / `_LARGE`.
3. `make run`.

Free-tier consequences and how the code handles them.
1. Two models means two separate rate-limit buckets; a simple question costs two calls on the small model and one on the large one.
2. Repeated questions hit the LangGraph node cache (router and extractor) and cost no model calls.
3. HTTP 429 is retried by the Google SDK (`max_retries`), then the node degrades to rule-based routing and a templated answer. The numbers never change; only the prose does.

## 3. Streamlit Community Cloud (the submitted URL)

1. Repository must be public; the app file is `app/streamlit_app.py`; Python 3.12.
2. In the app's Secrets, paste:

   ```toml
   GOOGLE_API_KEY = "..."
   PROPCO_LLM_PROVIDER = "gemini"
   ```

   `app/components/secrets.py` copies `PROPCO_*` and the key into the environment at startup; existing environment variables win.
3. Deploy. Health endpoint: `/_stcore/health`.

Limits worth knowing.
1. About 1 GB RAM. The app loads a 28 KB parquet file and pandas; it idles far below that.
2. Apps sleep after 12 h without traffic; the first visitor sees a wake-up page for 20–40 s.
3. One process per app: the in-memory checkpointer and cache are per process, which is fine here and documented as the first thing to swap when scaling (see ARCHITECTURE.md).

## 4. Docker

```bash
docker build -t propco-agent:local .
docker run --rm -p 8501:8501 --env-file .env propco-agent:local
```

1. Two-stage image, `uv sync --frozen --no-dev`, non-root user, `HEALTHCHECK` on `/_stcore/health`, JSON logs on stdout.
2. `docker compose up --build` starts the app plus an Ollama sidecar (`docker compose exec ollama ollama pull qwen3.5:9b` once). Ollama is not published on the host; only the app reaches it.
3. Image size is ~940 MB, dominated by pandas, pyarrow and the LangChain stack. Acceptable for a service image; a distroless or Alpine build was not worth the wheel-compatibility risk for this exercise.

## 5. Configuration reference

All settings are `PROPCO_*` environment variables (see `.env.example`). The ones you will actually touch:

| Variable | Default | Effect |
|---|---|---|
| `PROPCO_LLM_PROVIDER` | `gemini` | `gemini`, `ollama` or `fake` (tests) |
| `PROPCO_DATA_POLICY` | `raw` | `raw` sums the ledger as posted; `dedup` drops exact duplicate rows |
| `PROPCO_AS_OF` | last month in data | anchor for "this year", "last quarter" |
| `PROPCO_CURRENCY` | `EUR` | formatting only |
| `PROPCO_LOG_JSON` | `false` | JSON logs (set in the Docker image) |
| `LANGSMITH_TRACING` + `LANGSMITH_API_KEY` | unset | LangChain tracing, opt-in, nothing else to configure |

## 6. Verification after deploy

1. Open the URL; the sidebar shows rows, properties, tenants, as-of month and the provider.
2. Ask `What is the total P&L for all my properties this year?` → `€361,810.32`, labelled 2025 YTD through 2025-03, with a Steps line.
3. Ask `numbers?` → a clarification question; answer `total P&L 2024` → `€1,171,521.55`.
4. Open the Anomalies tab → duplicate rows, reversal pairs and ledger code 4650 listed.
