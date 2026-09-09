# User guide

For the asset manager using the chat. No setup knowledge needed.

## 1. What you can ask

The assistant answers questions about the PropCo ledger: five buildings, eighteen tenants, monthly postings from January 2024 to March 2025, in EUR.

| Kind of question | Examples |
|---|---|
| P&L, revenue or expenses for a period, property or tenant | `total P&L for 2024` · `revenue for tenant 7 in Q2 2024` · `expenses in June 2024` · `management fees in 2024` |
| One period against another | `this quarter vs the same period last year` · `Q1 2025 vs Q1 2024` · `2024 vs 2025` |
| Properties against each other | `compare Building 120 with Building 160 in 2024` |
| One property's profile | `details for Building 17` · `tell me about building 180` |
| Tenants | `who are my top tenants?` · `top 3 tenants last year` |
| Data quality | `is anything unusual in the numbers?` · `any duplicates?` |
| Several things at once | `Who are my top tenants, and is anything unusual in the numbers?` |
| Concepts | `what is NOI?` · `explain cap rate` (general knowledge, not from your data) |

English and Dutch both work. "Bldg 17", "building #17" and "Building 17" all mean the same property.

## 2. What it cannot tell you

The ledger holds no prices, market values, appraisal dates, street addresses, floor areas or occupancy. Ask for one of those and the assistant says so plainly and gives what it does have (revenue, expenses, contribution, tenants). It never invents a figure.

## 3. Reading an answer

1. **The figure** comes first, formatted as `€1,171,521.55`. Negative amounts carry a leading minus: `-€85,952.54`.
2. **Contribution vs net.** A property's P&L excludes entity-level overhead (mortgage interest, management fees, taxes) and is labelled *contribution*. Portfolio-wide P&L includes that overhead and is labelled *net*. The two are not directly comparable; the answer names which one it is.
3. **"This year" means the data's year.** The ledger ends in March 2025, so "this year" is 2025 through March, labelled *YTD*, and "this quarter" is 2025-Q1. The answer states the anchor every time.
4. **Notes** list the disclosures: anchoring, partial periods, whether a comparison is like-for-like (same number of months), a metric that was substituted (price → P&L), and data-quality warnings.
5. **Steps** shows the processing path (for example `guard → router → extractor → resolver → analyst_pnl → synthesizer`). Expand **Agent trace** under the answer for the same path with timing per step.

## 4. When it asks you something

If the question is too vague, names a property that does not exist, or refers to a period outside the data, the assistant asks a short question and offers options ("Did you mean: Building 120, Building 140, …?"). Reply in the chat; your reply is combined with the original question. After two rounds without a usable question it stops and suggests examples.

## 5. Sidebar controls

1. **Data policy** — `raw` (default) sums the ledger exactly as posted. `dedup` drops rows that are exact duplicates of another row. About 44 % of rows are such duplicates, and without a transaction id nobody can prove which are errors, so `raw` is the trustworthy default and `dedup` is a second opinion. Switching changes every figure; the anomaly report explains why.
2. **New conversation** — clears the chat and starts a fresh thread.
3. **Try one** — example questions, one click each.

## 6. Other tabs

1. **Data explorer** — P&L by property and year, net P&L per quarter, top tenants. Follows the data-policy switch.
2. **Anomalies** — everything the assistant would flag on its own: duplicate rows, reversal pairs, a ledger code booked under two categories, an unusual posting volume in June 2024, tenant concentration. Each finding has its evidence.
3. **Graph** — the processing pipeline as a diagram.

## 7. If something looks off

1. A yellow **degraded mode** notice means the language model was unreachable; the assistant answered with rule-based understanding and a templated text. The numbers are unaffected. Ask again later for a fuller answer.
2. A number you expected is missing from the prose: the assistant only states figures it computed; if the model tried to add one, the answer falls back to the template. Check the trace.
3. The first answer after a long pause can take 20–40 seconds while the app wakes up.

## 8. Good questions, better questions

| Instead of | Ask |
|---|---|
| `numbers?` | `total P&L for 2024` |
| `how are we doing?` | `this quarter vs the same period last year` |
| `Building 12` | `Building 120` (the assistant will offer the choice) |
| `2025 vs 2024` (3 months vs 12) | `Q1 2025 vs Q1 2024` |
| `what is the price of Building 17?` | `details for Building 17` (prices are not in the ledger) |
