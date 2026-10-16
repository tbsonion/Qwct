# QWCT 3.2 — Original RAW D1 source / tick / price basis / repeat-lineage census

## First native 3.2 attempt: output truncated (fix committed)

The first QuantConnect native run **e644d96e3916606d003cab3db02a8934** (LEAN 2.5.0.0.18184) produced actual original source results through June 6, 2024 but stopped printing after the **10KB log limit** warning. The uploaded 32-line log contains **no full-month SOURCE SUMMARY**; therefore no 92-record source classification or deduplication conclusion can be made from it.

The corrected [main.py](./main.py) still checks all original selected mirror source records but **removes per-record printouts and old NEAR/READY sample floods**, keeping concise DAY, SOURCE SUMMARY, STATUS, CONSISTENCY, REJECTS and at most eight compact category samples. Run the corrected main.py **once** on the same June 2024 window to obtain complete native counts. No M1/M5 replay and no production trading changes.

**Status:** Code and deterministic pure guard tests are committed. **Native 3.2 QuantConnect runtime has NOT been executed or verified**. GitHub CI status is not independently confirmed. Original 2.8, 3.0 and 3.1 sources and live strategy are unchanged; no actual P&L or orders.

## Why this is the next cost-effective experiment

The **real 3.0 native QuantConnect Fundamental50 point-in-time (PIT)** run on 2024-06-01..30 found **92 automatically tagged D1 mirrored level×stock-day records** that passed the original *morning* Stage2, strength, distance ≤1 ATR, support/resistance reversal, trend direction, and independent breach/retest causality. These are not 92 Gerchik trades or necessarily 92 unique levels. Native 3.1 June3 **first-three positive** AMAT/NFLX/SRPT and one MSFT control showed 0 exact **original** source-wick touches across four days, and discrepancies in original swing RAW price versus D1 cluster median. The source price/basis question deserves a **D1-only screen before any wider M1/M5 replay**.

## Implementation — standalone native LEAN Technical Backtest (no strategy P&L)

[**`main.py`**](./main.py) contains the complete algorithm (**under Cloud 32KB**). It starts from exact QWCT 3.0 verified PIT skeleton, with:
- same **original LEAN Fundamental 50 membership**, strict or verified native next-session selector via exchange calendar (no invented membership, no changed dates), same **180 as-of RAW D1 TradeBars**, original native Wilder ATR(14), SMA50, 20-day volume SMA, `levels_for_session`, `audit_mirror`, `mirror_gates`. 3.0 `QWCT MIRROR SUMMARY/GATES` counters are untouched.
- all 50 eligible PIT members checked daily **before** shadow top-10, then add to `ready_records` **only** D1 mirror proxy records satisfying EXACT original 3.0 morning gates. Original 3.0 count should again read `mirror_ready=92`, `scans=19`, `stock_days=950`, `d1_ready=949`, `stage2=861` for June 2024 (not assumed until native run).
- original **first_idx** and **last_idx** verified using original `_confirmed_swings` on real closed RAW D1, with original `high` for mirror from old resistance or `low` from old support; verifies swing timestamps, source date and `formed_at`. Reports exact original RAW swing price and native original symbol minimum price variation, **not** the approximate ATR-median cluster as an exact order-ready Gerchik BSU.
- One **batched original LEAN SCALED_RAW D1 `History[TradeBar]` call per eligible *day*** only for distinct eligible symbols, with 180 bars. Rejects noncausal, unordered or missing individual history, compares BOTH original source D1 and latest preceding-session D1 date and **original LEAN EndTime** to the same RAW days. Reports independent `grid=ON_GRID/OFF_GRID/UNKNOWN`, `basis=MATCH/REBASED_SOURCE_HISTORY/LATEST_CLOSE_DIFFERENCE/UNKNOWN_...`. A subcent RAW original relative to **the current native symbol tick grid** is a provenance warning, **not** proof of incorrect historical price. SCALED_RAW differences are historical corporate-action basis observations; this code **never changes** source prices or threshold and never claims it has recovered the only author-correct fixed BSU.
- Each morning-ready level×ticker×day is audited and counted in memory. The initial per-level SOURCE RECORD logs exceeded the QuantConnect Free 10KB cap, so the corrected build logs only aggregate counters and at most two samples per category: OFF_GRID, REBASED, UNKNOWN, MATCH_ON_GRID. The final `QWCT 3.2 SOURCE SUMMARY` + `SOURCE STATUS` reports the **exact observed number checked**, separately original confirmed sources, off-native-grid, RAW/SCALED basis match/rebased/unknown, cross-product consistency `source_consistent`, and **distinct source-lineage keys** with repeated `level-day` occurrences and cluster-median drift. Lineage identity is a **software key** (ticker+original high/low kind+original and last swing dates+mirror valid_from+exact RAW source price) and does NOT prove all consecutive mirror formation episodes are identical textbook BSUs.
- `QWCT 3.2 SOURCE CONSISTENCY` confirms `records==ready_from_3_0`; **missing SCALED_RAW stays UNKNOWN** and is still counted as a record. No M1/M5, consolidator, fills, order calls, TICK/SEC TVX, future levels or fabricated ticks.

### Exact one user step

1. Open original **QuantConnect Cloud project `Qwct-M5-Cohort-Research`**, click **`main.py` in the Backtest code editor**, *not* Research Notebook / `research.ipynb`.
2. Open [**3.2 `main.py` on GitHub**](./main.py), click **Copy raw file**, replace the entire contents of **Cloud root `main.py`** with it. **Keep** Cloud `strategy/config.py`, `strategy/levels.py`, `strategy/indicators.py`, and `strategy/timing_gate.py` unchanged. The new standalone main contains the original causal mirror auditor — no new helper files needed.
3. Run **one QuantConnect Technical Backtest**, not a profitability simulation, on existing defaults or params **`scan_start=2024-06-01`, `scan_end=2024-06-30`, `timing_mode=next_session`**.
4. Send only **`QWCT MIRROR SUMMARY`, `QWCT MIRROR GATES`, `QWCT 3.2 SOURCE SUMMARY`, `QWCT 3.2 SOURCE STATUS`, `QWCT 3.2 SOURCE CONSISTENCY`** and any `QWCT MIRROR REJECTS`/error. Individual source rows may be sent as an exported full log if needed (92 expected). Never pretend 92 until output confirms exactly.

### Interpreting the next output

- If baseline `eligible_proxies` or source `ready_from_3_0` differs from 92 or original 19/950/949/861 coverages differ, **stop interpreting source rates** and diagnose PIT timing/native data changes.
- If `records!=ready_from_3_0`, or source tally has unexpected `UNKNOWN_EXCEPTION` / source provenance not confirmed, **fail closed**; do not count missing data as valid.
- If `basis=REBASED` or `grid=OFF_GRID`, hold source case for historical corporate-action / original D1 price review. Do not automatically throw out every historical off-grid source as invalid, use cluster medians as fake fixed BSUs, or bend the half-tick BPU1 equality.
- If any `source_consistent` records exist, those are merely **source-data-consistent D1 *proxies***, not Gerchik approved levels. Only THEN plan a deterministically sampled separate native M1→M5 study with **human-approved manual source-level** decision, no accidental cherry-picking.

### Tests

Pure code/AST tests: [`tests/test_source_census_research.py`](../../tests/test_source_census_research.py) (source swing proof, tick grid, origin/close RAW-SCALED basis, end-time mismatch, PIT same 3.0 code, 32KB Cloud budget, no M5/orders). They were registered with the existing [cohort pure checks workflow](../../.github/workflows/qwct-cohort-pure-checks.yml). They do **not** constitute a native QuantConnect execution.
