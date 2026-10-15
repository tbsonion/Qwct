# QWCT 2.6 — Native dynamic D1 → M5 research cohort (May 2024)

**Status:** Code and pure regression guards committed. **A real native QuantConnect 2.6 Cloud backtest has NOT run yet**, and any BPU1/BPU2 counts are UNKNOWN until its log is received. No trading orders, SEC/TICK data, backtested fills, or claimed profitability.

## Purpose: broader point-in-time evidence, without changing the trading rules

Previous real native QWCT 2.5 six-case fixed-cohort run `b6c0a9982e638d3f5fd1aa0e56a1f84e` observed **6/6 D1 BSU proxies READY, 468 validated M5 bars, BPU1=0/BPU2=0** over six stock-days in April 2024. The initial six symbol-day test has finished; repeating it unchanged is not a useful next step.

New QWCT 2.6 is a **different, independent, continuously-selected Fundamental/D1 Shadow cohort for all 2024 May trading dates**, up to 50 native Fundamental candidates/day, legacy stage2 filter, and max 10 **D1 role-aligned Shadow** stocks/day. It **does not cherry-pick tickers after seeing future M5 candles** or infer signals from price proximity. Exact BPU1 native-tick and immediate BPU2 rules of the existing `strategy.patterns_bsu.BsuDetector` remain unchanged.

**Ready-solution review:** We reused the actual, previously native-verified QWCT 2.4 functions `d1_shadow_shortlist`, `classify_snapshot`, `origin_d1_audit` and `compare_raw_scaled` **unchanged** (copied from `research/universe_cloud/main.py`). Reused canonical `strategy/__init__.py` Cloud selector, `strategy.levels`, native `AverageTrueRange` / `SimpleMovingAverage`, `BsuDetector`, `validate_m5_tradebar`, and LEAN native `TradeBarConsolidator(timedelta(minutes=5))`. No new indicator, separate broker, homemade candle generator or execution engine.

## Create a NEW QuantConnect Python LEAN Cloud project — seven files

Project: **`Qwct-M5-Cohort-Research`**. Do not modify or replace `Qwct-LEAN-Test`, `Qwct-BSU-Research`, `Qwct-Universe-Research`, or `Qwct-M5-SixCase-Research`.

| Cloud file | GitHub main file to copy |
|---|---|
| `main.py` | [`research/cohort_cloud/main.py`](./main.py) |
| `strategy/__init__.py` | [`research/universe_cloud/strategy_init_cloud.py`](../universe_cloud/strategy_init_cloud.py) **(copy contents, rename to `__init__.py`)** |
| `strategy/config.py` | [`strategy/config.py`](../../strategy/config.py) |
| `strategy/indicators.py` | [`strategy/indicators.py`](../../strategy/indicators.py) |
| `strategy/levels.py` | [`strategy/levels.py`](../../strategy/levels.py) |
| `strategy/patterns_bsu.py` | [`strategy/patterns_bsu.py`](../../strategy/patterns_bsu.py) |
| `strategy/native_m5_validation.py` | [`strategy/native_m5_validation.py`](../../strategy/native_m5_validation.py) |

**IMPORTANT:** The bundled Universe selector `strategy_init_cloud.py` **is NOT the nearly empty `strategy_init_cloud.py` from the six-case project.** Use precisely the link above. It provides canonical `select_liquid_fundamentals` and `passes_gerchik_screener`.

**Defaults (set automatically in new `main.py`):** `scan_start = 2024-05-01`, `scan_end = 2024-05-31` (31 calendar days, fixed independent test). Custom date span allowed only up to **35 calendar days** per run. Saved project parameters override defaults. First line must contain `QWCT 2.6 COHORT ACTIVE 2024-05-01..2024-05-31`. Do **not** rerun Apr10–19 by accident.

## Timing and data validity — do not confuse replay with real-time trading

- **Selection happens by 09:29 ET** from actual same-day native Fundamental callback, up to **50** candidates. A real native Fundamental Saturday callback is **not silently reinterpreted** as a Monday selection; Monday can be explicitly marked `QWCT COHORT SKIP ... NO_SAME_DAY_CALLBACK`. This is **missing coverage**, not a negative BPU result or proof of no qualified stocks. `weekend_callbacks` count is included.
- One batched, closed, as-of **RAW D1** 180-bar history request for selected 50; same legacy stage2 and original `d1_shadow_shortlist` only. No current session D1 is allowed.
- Up to 10 **Shadow** stock candidates get a second batched native `SCALED_RAW` D1 request, verifying original SOURCE high/low, latest closed RAW/SCALED prices, native tick-grid applicability and native D1 bar-end timestamp consistency. Historical `REBASED` pivots are explicitly labeled and may be observed using the **original RAW** source if newest RAW/SCALED close agrees; historical transformation is NEVER substituted into a RAW M5 level. `MATCH` and `REBASED` are evidence classes, not manually certified BSU approvals. Off-native-grid RAW origins remain disallowed. All other failures are rejected with counted reason.
- **Only at the actual exchange close, including the final backtest day and early-close dates**, make one *additional* **bounded 09:30 → real close** batched `History[TradeBar]` RAW **M1** request for **the already frozen and qualified Shadow symbols only**. It does not subscribe to 50 minute streams, use future minutes in the morning, or model live entries. Native `TradeBarConsolidator(5min)` aggregates **real historical minute TradeBars** into completed native M5; `validate_m5_tradebar` rejects fill-forward/zero-volume/invalid-period candles. A split on a studied day quarantines its affected symbol.
- Reuse existing `BsuDetector.on_bar(ClosedBar(...))`, with exact original historical RAW swing pivot and native tick, preserving `BPU1` strict tick-touch and immediately following `BPU2`, wick breach, 20%-luft stop-distance rule, and 12:00–13:30 bounce-session window. Do not "round" WMT or lower BPU tolerance to inflate positives. A positive M5 BPU2 is an **algorithmic closed-candle proxy**, not automatically a manually valid Gerchik setup or a valid -30s TVX observation.
- Algorithm prints `QWCT COHORT SUMMARY` (callbacks/scans/covered days/D1 origin/basis/M1/M5/BPU1/BPU2/strict/window/invalidated), `QWCT COHORT REJECTS`, `QWCT COHORT COVERAGE`, nearest 10 original pivots (`QWCT COHORT NEAREST`), and up to 12 `QWCT COHORT BPU1/BPU2` examples. Output is compact for QuantConnect Free logging limits; no orders or synthetic fills.

**Why at the market close rather than +1 minute?** QuantConnect may skip after-market-close +1 minute scheduled events on the **final backtest date**. Zero-minute actual close is supported. The retrospective historical request ends at the *actual* current LEAN time, so early market closes also cannot include future data. Source: https://www.quantconnect.com/forum/discussion/13602/everyday-event-doesn-039-t-get-triggered-the-last-day-after-16-00-00/ .

## Backtest, expected proof, and decision gate

1. Create the new **7-file project**; run the **May 1–31, 2024** native QuantConnect Cloud Backtest once.
2. Return complete logs with `QWCT 2.6 COHORT ACTIVE`, `QWCT COHORT SUMMARY`, `QWCT COHORT REJECTS`, `QWCT COHORT COVERAGE`, `QWCT COHORT NEAREST`, and any `BPU1/BPU2` examples. A `M5_CONSOLIDATOR` or `MINUTE_HISTORY` error means **NOT** tested, not "zero signals."
3. If still **zero BPU1/BPU2**, report that outcome without relaxing exact-touch or fitting thresholds to the test. Next hypothesis is valid frozen-level **forward follow-up with separately proven expiry/invalidations**, or more independent monthly windows, not fabricated BPU.
4. If any real strict M5 BPU2 is found, independently label the source as Gerchik BSU from its actual D1 geometry before considering separate SEC/TICK retrospective -30s TVX proof. **No order execution or P&L until trading evidence and validations are complete.**

Official docs: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes ; https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests ; https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators .
