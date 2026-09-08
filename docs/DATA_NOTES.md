# Data notes

What is in `data/amiio.parquet`, what is not, and how the numbers are treated. Figures below are the golden values the unit tests assert (`tests/unit/analytics/`), computed with an independent pandas pass.

## Shape

1. 3,924 rows, 12 columns, one entity (`PropCo`).
2. Dimensions: `property_name` (5 buildings, 581 nulls), `tenant_name` (18 tenants, 759 nulls), `ledger_type` (revenue | expenses), `ledger_group` (5), `ledger_category` (29), `ledger_code` (28 codes), `ledger_description` (Dutch | English).
3. Time: `month` `2024-M01`..`2025-M03` (15 months), `quarter`, `year`. Month, quarter and year are mutually consistent on every row. 2025 has Q1 only.
4. Measure: `profit`, a signed amount. Revenue rows are mostly positive, expense rows mostly negative. P&L of any slice is `sum(profit)`.
5. Currency: EUR. Descriptions are Dutch (`Bankkosten`, `Huurkorting`, `Opbrengst Huren`).

## Not in the data

6. No price, market value, appraisal date, street address, floor area, occupancy, lease terms. Questions about these are answered with what the ledger does hold and an explicit statement of what it does not.

## Sign conventions

7. 22% of expense rows are positive (credits, refunds, reversals). Revenue negatives are rent discounts (`sales_discounts` group) and reversals. Never filter by sign; filter by `ledger_type`.
8. 1,348 rows carry a zero amount. They do not move any total.

## Golden figures (RAW policy)

| Slice | P&L |
|---|---|
| All time | 1,533,331.87 |
| 2024 | 1,171,521.55 (revenue 2,295,528.74, expenses -1,124,007.19) |
| 2025 (Q1 only) | 361,810.32 |
| 2024-Q1 / Q2 / Q3 / Q4 | 262,309.07 / 317,892.76 / 312,364.85 / 278,954.87 |
| 2025-Q1 vs 2024-Q1 | +99,501.25 (+37.93%) |

Per property (contribution, excludes entity-level overhead):

| Property | 2024 | 2025 YTD | All time |
|---|---|---|---|
| Building 120 | 675,640.08 | 174,927.34 | 850,567.42 |
| Building 140 | 412,816.19 | 113,842.66 | 526,658.85 |
| Building 160 | 565,790.15 | 147,274.98 | 713,065.13 |
| Building 17 | 280,388.71 | 72,178.10 | 352,566.81 |
| Building 180 | 303,598.25 | 81,301.78 | 384,900.03 |
| Unallocated overhead | -1,066,711.83 | -227,714.54 | -1,294,426.37 |

Top tenants 2024 by revenue: Tenant 7 703,009.03 (30.63%), Tenant 14 310,188.48, Tenant 11 232,925.56, Tenant 13 217,950.12, Tenant 3 159,707.57. Top three hold 54.28% of tenant revenue.

## Contribution vs net

9. 581 rows have no property: mortgage interest (code 4611), asset-management fees (4820), taxes, insurance. Together -1,294,426.37.
10. Property-level P&L is therefore a **contribution** figure. Portfolio P&L is **net** and includes the overhead. Answers say which one they report. Allocating overhead across properties (by revenue share, floor area, ...) is a natural extension and is not implemented.

## Anomalies

11. **Exact duplicate rows: 1,747 (44.5%)**, carrying 538,220.07. Multiplicity up to 96. There is no transaction id, so a duplicate cannot be distinguished from a legitimate repeated posting (same tenant, amount and month; two units, two invoices).
12. **Reversal pairs: 449** exact `+x / -x` pairs within the same keys and month, 3,349,539.39 gross cancelled. Net effect zero; gross figures and row counts inflated.
13. **Ledger code 4650** (`Bankkosten | Bank charges`) is booked under both `bank_charges` and `financial_expenses`: 242 rows, -7,255.08 in total, so roughly half is double counted. The one defect that is provable from the data alone.
14. **June 2024 volume**: 804 rows against a 262-row monthly average (z = 3.3). A batch of corrections and reversals. In the RAW view the month's net (105,246.74) is unremarkable; in the DEDUP view it collapses to -247,866.64 (z = -3.5), which is one reason DEDUP is not the default.
15. **Tenant concentration**: Tenant 7 is 30.49% of all-time revenue (threshold 25%).

## Policy

16. Default **RAW**: sum what is posted, flag what looks off. `drop_duplicates()` changes 2024 P&L from 1,171,521.55 to 682,529.72 (-42%) and turns 2024-Q2 negative (-37,449.34), which no analyst would sign off on without a transaction-level source.
17. The 4650 double mapping is flagged, not corrected. Correcting one provable defect while keeping 1,700 unprovable duplicates would be inconsistent; the anomaly report lists both.
18. `PROPCO_DATA_POLICY=dedup` and the UI toggle expose the deduplicated view with a warning.

## Time anchor

19. `as_of` is the last month in the data (`2025-M03`), not the wall clock. "This year" resolves to 2025 YTD (Jan-Mar) and every such answer says so. "This quarter vs the same period last year" is 2025-Q1 vs 2024-Q1, like-for-like. Full-year 2025 does not exist; a 2025-vs-2024 comparison is flagged as 3 months against 12.
