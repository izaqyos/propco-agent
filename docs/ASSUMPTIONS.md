# Assumptions

The task brief leaves several things open. Each assumption below is a decision, with the reason and where it lives in code. Change the decision, change the linked setting or module.

## Dataset

1. **Format.** The brief says CSV; the file supplied is Parquet (`data/amiio.parquet`). Loaded as-is. `LedgerRepository` is a protocol, so a CSV or API-backed implementation is a drop-in (`src/propco_agent/data/repository.py`).
2. **Scope.** One entity (`PropCo`), five properties (`Building 17/120/140/160/180`), 18 tenants, months `2024-M01`..`2025-M03`. Nothing outside this range exists; questions about other years get an explicit "not in the dataset" answer with the available range.
3. **Currency is EUR.** Ledger descriptions are Dutch (`Bankkosten`, `Huurkorting`, `Opbrengst Huren`). The brief's `$` examples are treated as illustrative. Configurable via `PROPCO_CURRENCY`.
4. **`profit` is a signed contribution.** Revenue rows are mostly positive, expense rows mostly negative; P&L for any slice is `sum(profit)`. Negative revenue rows are discounts or reversals, positive expense rows are credits. Rows are never filtered by sign, only by `ledger_type`.
5. **Rows without a property are entity-level overhead** (mortgage interest, asset-management fees, taxes, insurance; about -1.29M over the range).
   - Property-level P&L is reported as **contribution** (excludes overhead).
   - Portfolio P&L is reported as **net** (includes overhead).
   - Every answer names which one it is. An allocation view (overhead spread by revenue share) is offered but not the default.
6. **No valuation data.** There is no price, market value, appraisal date, street address, floor area or occupancy in the ledger. Questions about these return what the ledger does hold (revenue, expenses, contribution, tenants, active months) and say plainly what it does not. The brief's "123 Main St priced at $500,000" example is therefore unanswerable by design; a valuation feed is a documented extension point, not a stub with fake numbers.
7. **Property references are names, not addresses.** "Bldg 17", "building 17", "#17" resolve to `Building 17` by fuzzy match. Anything below the match threshold triggers a clarification with the closest candidates.

## Data quality policy

8. **Trust the ledger as posted (RAW).** 1,747 rows (44%) are exact duplicates of another row and 449 pairs are exact `+x / -x` reversals within the same month. The ledger has no transaction id, so a duplicate cannot be distinguished from a legitimate repeated posting (same tenant, same amount, same month, two units). Dropping duplicates changes 2024 P&L by 42% and turns 2024-Q2 negative, which is not defensible. Default: sum what is posted, **flag** what looks off. `PROPCO_DATA_POLICY=dedup` exposes the alternative view with a warning.
9. **One provable defect is flagged, not silently fixed.** Ledger code 4650 (`Bankkosten | Bank charges`) is mapped to two categories (`bank_charges` and `financial_expenses`): 242 rows, -7,255.08 in total, roughly half of it double counted. Fixing one row-level bug while keeping 1,700 suspicious rows would be inconsistent; the anomaly report lists it.
10. **June 2024 is treated as a real anomaly, not an error.** 804 rows (2.5x a normal month, z = 3.3) from a batch of corrections and reversals. Its RAW net is ordinary; only the deduplicated view turns it into a -247,866 month. It is reported, not smoothed. Spike detection runs on both posting volume and monthly net (|z| > 2.5).

## Time

11. **"Today" is the last month in the data.** The wall clock (2026) has no data. Relative phrases ("this year", "this quarter", "last month") are anchored to `as_of = 2025-M03`, and every such answer discloses the anchor ("2025 YTD through 2025-03"). Override with `PROPCO_AS_OF`.
12. **Partial periods are compared like-for-like.** "2025 vs 2024" compares 2025-Q1 with 2024-Q1 and says so; a full-year vs partial-year comparison is only produced if the user insists, with a warning.
13. **Quarters are calendar quarters.** No fiscal-year offset.

## Language model

14. **Provider.** Gemini Flash free tier, per the interviewer. `gemini-2.5-flash-lite` for routing and extraction, `gemini-2.5-flash` for prose. Ollama (`qwen3.5:9b`) is a fully offline alternative; tests use a scripted fake. Switch with `PROPCO_LLM_PROVIDER`.
15. **The model never does arithmetic.** Numbers come from deterministic pandas code; the model classifies, extracts and phrases. Every money figure in an answer is checked against the computed result before it is shown; on mismatch a templated answer is returned instead.
16. **Free-tier quotas are a design input.** Repeated questions are served from a node-level cache, HTTP 429 triggers exponential backoff, and quota exhaustion degrades to a templated answer over the deterministic result rather than an error.
17. **User text is data, not instructions.** It is passed to the model inside delimiters with a fixed system prompt; nothing in the user's message can change the graph's route or the numbers.

## Scope

18. **Single user, single entity.** No authentication, multi-tenancy or row-level security. The Streamlit session is the conversation thread. The architecture notes describe the path to Postgres-backed checkpoints and per-user threads.
19. **English and Dutch input** are handled by the model; other languages are best-effort.
20. **General real-estate questions** (NOI, cap rate, yield) are answered from model knowledge, labelled as such, and never mixed with ledger figures.
