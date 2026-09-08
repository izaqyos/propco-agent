# Graph topology

Generated with `AssetManagerService.mermaid()` (LangGraph `get_graph().draw_mermaid()`). Regenerate after any change to `src/propco_agent/graph/builder.py`:

```bash
PROPCO_LLM_PROVIDER=fake uv run python -c "from propco_agent.config import *; from propco_agent.service import AssetManagerService; print(AssetManagerService.from_settings(Settings(_env_file=None, llm_provider=LLMProvider.FAKE)).mermaid())"
```

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	router(router)
	extractor(extractor)
	resolver(resolver)
	analyst_pnl(analyst_pnl)
	analyst_compare_periods(analyst_compare_periods)
	analyst_compare_properties(analyst_compare_properties)
	analyst_tenants(analyst_tenants)
	analyst_asset_details(analyst_asset_details)
	analyst_anomalies(analyst_anomalies)
	guard(guard)
	clarifier(clarifier)
	general(general)
	unsupported(unsupported)
	synthesizer(synthesizer)
	sub_question(sub_question)
	__end__([<p>__end__</p>]):::last
	__start__ --> guard;
	analyst_anomalies --> synthesizer;
	analyst_asset_details --> synthesizer;
	analyst_compare_periods --> synthesizer;
	analyst_compare_properties --> synthesizer;
	analyst_pnl --> synthesizer;
	analyst_tenants --> synthesizer;
	clarifier -.-> __end__;
	clarifier -.-> guard;
	extractor --> resolver;
	guard -.-> clarifier;
	guard -.-> router;
	resolver -.-> analyst_anomalies;
	resolver -.-> analyst_asset_details;
	resolver -.-> analyst_compare_periods;
	resolver -.-> analyst_compare_properties;
	resolver -.-> analyst_pnl;
	resolver -.-> analyst_tenants;
	resolver -.-> clarifier;
	router -.-> clarifier;
	router -.-> extractor;
	router -.-> general;
	router -.-> sub_question;
	router -.-> unsupported;
	sub_question --> synthesizer;
	general --> __end__;
	synthesizer --> __end__;
	unsupported --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Notes:

1. `sub_question` runs a compiled subgraph (router → extractor → resolver → analyst, or `sub_fail`) once per sub-question; the parent fans out with `Send` and the `results`/`trace`/`errors` reducers merge the branches before `synthesizer`.
2. `clarifier` pauses the run with `interrupt()`; the reply re-enters at `guard` with the enriched question. Bounded to two rounds.
3. `router` and `extractor` carry a `CachePolicy` keyed on `(question, policy)` with a one-hour TTL.
