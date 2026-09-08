# Challenges and how they were solved

1. **The brief's examples cannot be answered from the data.** "123 Main St priced at $500,000", "Last Appraisal Date" — the ledger has no addresses, prices or appraisals. Solved by making "not in the dataset" a first-class path: the resolver substitutes P&L for price with a disclosure, the asset profile lists exactly which fields the ledger does not hold, and unknown addresses produce a clarification with the real property names. The assistant never fabricates a price.

2. **44 % of rows are exact duplicates and deduplicating looks wrong.** Dropping them changes 2024 P&L by 42 % and turns a quarter negative. Solved by profiling first, computing golden numbers independently of the code under test, and choosing a raw-sum policy with an anomaly agent that reports duplicates, 449 reversal pairs, a double-mapped ledger code and a volume spike. The alternative view is one toggle away. The reasoning is in DATA_NOTES.md and ASSUMPTIONS.md.

3. **A first read of the data was partly wrong.** Early profiling showed a June 2024 net collapse; the independent golden pass showed it only exists in the deduplicated view (raw June is ordinary; the anomaly is posting volume). Two other figures were corrected the same way. Solved by treating goldens as evidence: the correction is logged in the notes, and the spike detector runs on both row volume and net.

4. **"This year" has no data.** The wall clock is 2026; the ledger ends in March 2025. Solved by anchoring relative periods to the data's last month, disclosing the anchor in every such answer, clipping partial periods to YTD, and forcing like-for-like comparisons (Q1 vs Q1) with a warning when the user asks for full-year vs partial-year.

5. **A small local model fills the schema poorly.** `qwen3.5:9b` found the time phrase but left `year`/`quarter`/`relative` empty and never filled `metric`. Solved twice: worked JSON examples in the extractor prompt (fields now filled in the smoke set), and a code-side merge that re-parses any `raw` period text and fills gaps from keyword rules. The design became "the model finds spans, code parses them".

6. **Thinking mode made every question take 20–90 seconds.** Qwen-class models reason before emitting JSON. Solved with `reasoning=False` and a generation cap on the Ollama client: 5–8 s per question end to end, identical answers.

7. **The model must not invent numbers.** Solved with a grounding check on the synthesizer — every figure in the prose must exist in the computed results — and a templated answer as the fallback. The model's own "Steps" line is discarded and replaced with the real node trace.

8. **Parallel branches and a scripted fake.** `Send` fan-out runs sub-questions concurrently, so a queue-based fake model returned responses in nondeterministic order. Solved by adding keyed responses (chosen by a substring of the latest message) to the fake, and by having branches return only reducer-backed keys so they never collide on scalar state.

9. **LangGraph typing and naming rules.** Node names cannot contain `:`; node callables must satisfy a `Protocol` whose parameter is literally named `state`, so plain `Callable[[State], dict]` fails strict mypy. Solved with `analyst_*` names and a small `Node` protocol used as the factories' return type.

10. **Free-tier quotas as a design input.** Ten requests per minute on Flash would allow about three questions per minute. Solved with model tiering (two quota buckets), node-level caching of router and extractor results, SDK retries on 429, and a degradation chain that still returns correct numbers with a templated answer when the provider is exhausted.

11. **Licence gate that understood SPDX.** `pip-licenses --allow-only` failed on `MPL-2.0 AND (Apache-2.0 OR MIT)` and flagged a dev-only, dual-licensed transitive dependency. Solved with a small script that checks runtime dependencies only and splits SPDX expressions into atoms, each of which must be permissive.

12. **Streamlit script directory vs package imports.** Streamlit runs the app with `app/` as the script directory, so `from app.components import …` fails outside pytest. Solved with a two-line `sys.path` bootstrap at the top of the app and a per-file lint exception; the pure helpers stay importable and unit-tested.

13. **Prompt injection in a chat over financial data.** Solved structurally rather than by filtering: user text is delimited and declared data in every prompt, intents are a closed enum, the resolver only accepts names that exist, and the synthesizer cannot introduce numbers. The live smoke confirms "ignore all previous instructions…" routes to `unsupported`.
