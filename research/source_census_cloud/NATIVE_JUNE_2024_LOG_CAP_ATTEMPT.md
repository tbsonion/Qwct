# QWCT 3.2 — First native attempt, incomplete due to QuantConnect 10KB log cap

**Source**: user's 32-line native LEAN export. Research run `e644d96e3916606d003cab3db02a8934`, LEAN 2.5.0.0.18184, June 1–30, 2024; first original code printed detailed source rows per mirror level×session. The export stops after a QuantConnect message on June 6: **'maximum of 10kb of log data per backtest, and 10kb total max per day'**. The final aggregate `QWCT 3.2 SOURCE SUMMARY`, `SOURCE STATUS`, and `SOURCE CONSISTENCY` are **not visible**. It would be false to claim all 92 source records have been examined or categorized based on this output alone.

## Actual observations visible before truncation

- **June 3** exactly three morning-ready source records: AMAT original RAW first swing resistance high `$214.255`, cluster `$214.460`, `tick=$0.01`, **OFF_GRID + REBASED_SOURCE_HISTORY**; NFLX `$634.54` vs cluster `$633.775`, **ON_GRID + MATCH**; SRPT `$124.51` vs `$125.000`, **ON_GRID + MATCH**. All three logged `state=RAW_SOURCE_CONFIRMED`. The daily log states `mirrors=77 near=17 ready=3`.
- **June 4** printed META `$481.34` **ON_GRID + MATCH**, NFLX `$634.54` **ON_GRID + MATCH**, UNH `$496.00` **ON_GRID + MATCH**, JPM `$200.48` **ON_GRID + REBASED_SOURCE_HISTORY**; day `ready=4`.
- **June 5** printed AMD `$162.56` and `$165.50` both **ON_GRID + MATCH**; MSFT `$415.32` **ON_GRID + REBASED**; META `$481.34` and UNH `$496.00` repeats **ON_GRID + MATCH**; NOW `$677.51` and `$691.25` **ON_GRID + MATCH**; VRT `$88.69` **ON_GRID + MATCH**. Day `ready=8`.
- **June 6** shows selected early cases including CRWD `$333.19` and `$337.00` **MATCH**, AVGO `$1403.72` **MATCH**, MCHP `$91.86` and `$94.15` **REBASED**, UNH `$496.00` **MATCH**, and PANW `$292.87` **MATCH**, before the **10KB log cap**. June 6's full day and all later dates are not visible; there are Factor file precision/first-date warnings (not independent proof of invalid prices).

These lines establish that the intended historical RAW source and SCALED_RAW flags work for some individual records; they do **not** establish the complete source basis breakdown or level-lineage deduplication across 92 records.

## Fix implemented

New revision of [`main.py`](./main.py) retains the exact same original PIT Fundamental50 selection, original 180 closed native RAW D1 bars, Stage2/role/proximity/trend eligibility gates, native tick + SCALED_RAW comparison, and distinct lineage counters. It **removes full SOURCE RECORD line per level-day and suppresses original 40 NEAR + 50 READY example floods**, logging at most two examples per classification category and short per-day + final summary instead. New pure regression guards reject the old log flood pattern. One repeat June 2024 technical research-only Cloud Backtest with the revised single `main.py` is needed; **no M5, orders, or configuration change**.
