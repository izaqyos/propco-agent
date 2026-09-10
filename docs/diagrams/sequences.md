# Use-case sequences

Each diagram is one question through the graph. Node names match `src/propco_agent/graph/`. Model calls are marked `LLM`; everything else is deterministic code.

Each mermaid block is followed by a static SVG render of the same diagram (`img/`), in case your viewer doesn't render mermaid — GitHub, VS Code with the mermaid preview extension, and mermaid.live all do; a plain file browser or an outdated preview extension may not.

## 1. P&L for a period

`What is the total P&L for all my properties this year?`

```mermaid
sequenceDiagram
    actor U as User
    participant G as guard
    participant R as router (LLM)
    participant E as extractor (LLM)
    participant V as resolver
    participant A as analyst_pnl
    participant S as synthesizer (LLM)
    U->>G: question
    G->>R: ok
    R->>E: intent=pnl, confidence 0.95
    E->>V: periods=[relative this_year], metric=pnl
    V->>V: as-of 2025-M03 → 2025 YTD (through 2025-03), note recorded
    V->>A: LedgerFilter(period=2025 YTD)
    A->>S: PnLResult total €361,810.32, 743 rows, partial_period=true
    S->>S: grounding check: every number ∈ results
    S-->>U: answer + notes (as-of anchor, YTD) + Steps line
```

![P&L for a period](img/seq-1-pnl-for-a-period.svg)

## 2. Period comparison, like-for-like

`How does this quarter compare to the same period last year?`

```mermaid
sequenceDiagram
    actor U as User
    participant R as router (LLM)
    participant E as extractor (LLM)
    participant V as resolver
    participant A as analyst_compare_periods
    participant S as synthesizer (LLM)
    U->>R: question
    R->>E: period_compare
    E->>V: [this_quarter, same_period_last_year]
    V->>V: 2025-Q1, base = first period → 2024-Q1
    V->>A: periods=[2025-Q1, 2024-Q1]
    A->>S: a=€361,810.32 b=€262,309.07 Δ=€99,501.25 (+37.93 %), like_for_like=true
    S-->>U: answer
```

![Period comparison, like-for-like](img/seq-2-period-comparison-like-for-like.svg)

## 3. Clarification with `interrupt`, then resume

`details for 123 Main St`

```mermaid
sequenceDiagram
    actor U as User
    participant R as router (LLM)
    participant E as extractor (LLM)
    participant V as resolver
    participant C as clarifier
    participant G as guard
    U->>R: question
    R->>E: asset_details
    E->>V: properties=["123 Main St"]
    V->>C: Unresolved("no property matching '123 Main St'", suggestions=[Building 120, 140, 160])
    C-->>U: interrupt: "… Did you mean: Building 120, Building 140, Building 160?"
    Note over C,U: graph paused, thread state kept by the checkpointer
    U->>C: Command(resume="Building 17")
    C->>G: question = "details for 123 Main St — Building 17", clarify_rounds=1
    G->>R: ok
    R->>E: asset_details
    E->>V: properties=["Building 17"]
    V-->>U: … analyst_asset_details → synthesizer → answer
```

![Clarification with interrupt, then resume](img/seq-3-clarification-with-interrupt-then-resume.svg)

## 4. Compound question, `Send` fan-out

`Who are my top tenants, and is anything unusual in the numbers?`

```mermaid
sequenceDiagram
    actor U as User
    participant R as router (LLM)
    participant P as parent graph
    participant S1 as sub_question #1 (subgraph)
    participant S2 as sub_question #2 (subgraph)
    participant S as synthesizer (LLM)
    U->>R: question
    R->>P: sub_questions=["Who are my top tenants?", "Is anything unusual in the numbers?"]
    par branch 1
        P->>S1: Send(question #1)
        S1->>S1: router → extractor → resolver → analyst_tenants
        S1-->>P: results=[TenantRanking], trace, errors
    and branch 2
        P->>S2: Send(question #2)
        S2->>S2: router → extractor → resolver → analyst_anomalies
        S2-->>P: results=[AnomalyReport], trace, errors
    end
    P->>S: results (reducer-merged), notes, trace
    S-->>U: one answer covering both, or "Not answered: …" for a failed branch
```

![Compound question, Send fan-out](img/seq-4-compound-question-send-fan-out.svg)

## 5. Unsupported metric, substituted and disclosed

`What is the price of my asset at Building 17 compared to Building 120?`

```mermaid
sequenceDiagram
    actor U as User
    participant R as router (LLM)
    participant E as extractor (LLM)
    participant V as resolver
    participant A as analyst_compare_properties
    participant S as synthesizer (LLM)
    U->>R: question
    R->>E: price_compare
    E->>V: properties=[Building 17, Building 120], metric=price
    V->>V: price ∉ SUPPORTED → metric=pnl, note: "'price' is not in the ledger dataset …"
    V->>A: properties, metric=pnl, period=all data (note)
    A->>S: ranked=[Building 120, Building 17]
    S-->>U: ranking by P&L contribution + the disclosure that price is not available
```

![Unsupported metric, substituted and disclosed](img/seq-5-unsupported-metric-substituted-and-disclosed.svg)

## 6. Provider outage, graceful degradation

Any question while the model is unreachable or out of quota.

```mermaid
sequenceDiagram
    actor U as User
    participant R as router
    participant E as extractor
    participant V as resolver
    participant A as analyst_*
    participant S as synthesizer
    U->>R: question
    R--xR: LLM raises → LLMUnavailableError
    R->>E: rule_route(question), degraded=true, error recorded
    E--xE: LLM raises
    E->>V: rule_extract(question)
    V->>A: resolved query (identical to the LLM path)
    A->>S: results (identical numbers)
    S--xS: LLM raises
    S-->>U: templated answer + Steps, UI shows a "degraded mode" notice
```

![Provider outage, graceful degradation](img/seq-6-provider-outage-graceful-degradation.svg)

## 7. Anomaly check

`is anything unusual in the numbers?`

```mermaid
sequenceDiagram
    actor U as User
    participant R as router (LLM)
    participant V as resolver
    participant A as analyst_anomalies
    participant S as synthesizer (LLM)
    U->>R: question
    R->>V: anomaly_check (extractor finds nothing, resolver defaults period = all data)
    V->>A: LedgerFilter()
    A->>A: duplicate_rows, reversal_pairs, double_mapped_codes, monthly_volume_spike, monthly_net_spike, zero_rows, unallocated_overhead, tenant_concentration
    A->>S: AnomalyReport (7 findings on the raw view)
    S-->>U: findings ordered by severity, each with its evidence
```

![Anomaly check](img/seq-7-anomaly-check.svg)
