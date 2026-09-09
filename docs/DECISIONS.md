# Decisions

Short architecture decision records. Each one: the choice, what it was chosen over, why, and what it costs. Newest last.

## ADR-1 · LLM at the edges, deterministic core

**Chosen:** the model classifies, extracts and phrases; code resolves, filters and computes.
**Over:** (a) a single tool-calling agent that picks pandas tools itself; (b) LLM-generated pandas/SQL executed at runtime.
**Why:** reproducible numbers, unit-testable analytics with golden values, no arithmetic drift, no code execution from model output. (a) is flexible but every run is a different path and the model still writes the final figures; (b) is fast to build and impossible to make safe or testable.
**Cost:** new question types need a new analyst node plus an intent. Acceptable: the domain has a handful of question shapes, and the general-knowledge node covers the long tail of concept questions.

## ADR-2 · Router → specialists, not a supervisor loop

**Chosen:** one routing step to a fixed set of specialist nodes, plus `Send` fan-out for compound questions.
**Over:** a supervisor agent that repeatedly decides which worker to call next until done.
**Why:** predictable cost (three model calls per question), a trace a reviewer can read, no risk of the supervisor looping. The graph is still multi-agent — each node has one job and its own prompt or tool set — it just has a static topology.
**Cost:** less adaptive on questions that need several tools in sequence. Compound questions cover the common case ("A, and also B"); true multi-step planning is out of scope and said so.

## ADR-3 · Structured output with retry-and-feedback, not free-text parsing

**Chosen:** `with_structured_output(schema, include_raw=True)`; on validation failure the error text is sent back and the model gets one or two more attempts; transport failures surface as one exception type.
**Over:** regex or JSON parsing of free text; giving up on the first bad reply.
**Why:** pydantic schemas are the contract between model and code; the feedback loop fixes most small-model slips (a missing field, a wrong enum) without a second design.
**Cost:** a worst case of three calls for one classification. Bounded by `llm_max_retries`.

## ADR-4 · Rules as a fallback layer, not the primary

**Chosen:** keyword rules run (a) when the model is unavailable and (b) after the model, to fill fields it left empty and to re-parse period phrases it returned only as text.
**Over:** rules only (no model) or model only (no rules).
**Why:** rules alone cannot handle Dutch, paraphrase or compound questions; the model alone leaves gaps on small models (observed on `qwen3.5:9b`: `raw: "Q2 2024"` with no year or quarter). Together they are robust and the fallback path is fully testable without a model.
**Cost:** two code paths to keep in sync. Mitigated by the merge being a single, tested function.

## ADR-5 · Grounding check on the synthesizer

**Chosen:** every number in the model's prose must appear in the computed results; otherwise the templated answer is shown and the event is traced.
**Over:** trusting the model; or never using the model for prose at all.
**Why:** the one failure mode a finance user will not forgive is a made-up figure. The check is cheap and conservative; the templated answer is always available.
**Cost:** a legitimate paraphrase that rounds a figure (`€1.17M`) fails the check and falls back to the template. Documented, and preferable to the alternative.

## ADR-6 · Raw-sum data policy, anomalies flagged

**Chosen:** sum the ledger as posted; detect and report duplicates, reversals, double-mapped codes, spikes, concentration; expose a `dedup` view as an explicit toggle.
**Over:** deduplicating by default; silently fixing the provable double mapping.
**Why:** no transaction id means duplicates cannot be proven; deduplication changes 2024 P&L by 42 % and makes a quarter negative. Reporting what a human analyst would notice is more useful, and more honest, than guessing. See DATA_NOTES.md.
**Cost:** the default total includes rows that may be duplicates. Said plainly in every anomaly report.

## ADR-7 · "Today" is the data's last month

**Chosen:** relative phrases anchor to `2025-M03` (the last month with data), disclosed in every such answer; override with `PROPCO_AS_OF`.
**Over:** the wall clock (2026), which has no data and would make "this year" an empty answer.
**Why:** the user's mental "now" is the last closed month; an assistant that says "no data for this year" about a ledger that ends in March is useless.
**Cost:** must be disclosed every time or it misleads. It is.

## ADR-8 · Clarification via `interrupt`, two rounds

**Chosen:** the graph pauses with a question; the reply is merged into the original question and re-enters at the guard; after two rounds it stops with examples.
**Over:** returning a clarification as a normal answer and starting over on the next message.
**Why:** `interrupt` keeps the thread's state (what was already resolved) and demonstrates the human-in-the-loop primitive the framework is built around. The bound prevents an infinite loop with a confused user or a stuck model.
**Cost:** a checkpointer is required (in-memory here, Postgres at scale) and the UI must know a turn is pending. Both are small.

## ADR-9 · Subgraph per sub-question, reducers for merging

**Chosen:** compound questions fan out with `Send`; each branch runs a compiled subgraph and returns only reducible keys (`results`, `trace`, `errors`, `degraded`).
**Over:** answering sub-questions sequentially in one loop; or letting branches write scalar state.
**Why:** parallel branches are the natural fit and the reducers make the merge explicit. Returning only reducible keys avoids the class of "concurrent update to a non-reducer key" errors.
**Cost:** a failed sub-question cannot ask for clarification mid-branch; it is reported in the answer instead. Fan-out is capped at four.

## ADR-10 · Gemini Flash free tier, Ollama for development, fake for tests

**Chosen:** provider-agnostic factory; `gemini-3.5-flash-lite` for router/extractor and `gemini-3.5-flash` for prose in deployment; `qwen3.5:9b` via Ollama offline; a scripted fake in CI.
**Over:** one provider hard-wired.
**Why:** the interviewer asked for the Gemini free tier; the split model tiering doubles the effective free quota and matches the tasks (classification is easy, prose is not). Ollama makes development free and offline. The fake makes 400 tests deterministic and fast.
**Cost:** three code paths in one factory and provider-specific settings (`reasoning=False` on Ollama). Twenty lines.

## ADR-11 · Streamlit `AppTest` as the e2e layer, Playwright as smoke

**Chosen:** the headless `AppTest` runner for all UI flows (counts towards coverage), three Playwright tests against a real server for "does it render in a browser".
**Over:** Playwright for everything.
**Why:** `AppTest` runs in-process in milliseconds and asserts on widgets, which is what UI logic needs; the browser tests catch the class of problems `AppTest` cannot (server start, static assets, real rendering).
**Cost:** two test styles. The browser job is separate in CI and opt-in locally.

## ADR-12 · pandas over DuckDB or Polars

**Chosen:** pandas 3 on a 3,924-row frame loaded once.
**Over:** DuckDB (SQL over parquet) or Polars.
**Why:** the whole dataset fits in memory many times over; pandas is what reviewers read fluently; the repository protocol isolates the choice so a DuckDB implementation is a drop-in when the data grows.
**Cost:** none at this size. At millions of rows the repository swap is the first thing to do.

## ADR-13 · Node cache keyed on the question

**Chosen:** `CachePolicy` on router and extractor, keyed on `(question, policy)`, one-hour TTL.
**Over:** no cache; caching the whole answer.
**Why:** repeated or rephrased-identical questions are common in a demo and in real use, and the free tier is rate-limited. Caching only the understanding steps keeps the answer fresh if the data policy or as-of changes.
**Cost:** a degraded routing decision made during a provider outage is cached for the TTL. Acceptable for an hour; a shorter TTL for degraded results is a one-line change if it matters.
