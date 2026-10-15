# QWCT 2.6 — Native dynamic D1 → M5 research cohort (May 2024)

## 2026-10-15 — Real native May 2024 result: no exact BPU1, incomplete coverage to investigate

**Native QuantConnect LEAN 2.5.0.0.18184 backtest `e30da5e09d7fc0b9507871f63f7536c7` completed, May 1–31 2024.** This is the first genuine QWCT 2.6 run, superseding the original "native pending" status in the setup instructions below.

| Observed result | Count |
| --- | ---: |
| Scheduled market-day scans | 22 |
| Fundamental selection callbacks | 22, including 4 weekends |
| Sessions with same-calendar-day Fundamental selection | 18 |
| **Four sessions skipped for missing same-day callback** | **May 6, 13, 20, 28** |
| Fundamental top50 stock-days examined | 900 |
| Native RAW D1-ready / Stage2 pass | 900 / 813 |
| Shadow qualified stock-days | 13 |
| Origin provenance PASS / UNKNOWN / FAIL | 13 / 0 / 0 |
| Native RAW/SCALED origins | 8 MATCH / 5 REBASED |
| Ready BSU **proxies** | 13 |
| Sessions with eligible after-close minute replay | 10 |
| Native M1 TradeBars | 5,000 |
| Validated emitted native M5 bars | 1,001 |
| Closed-M5 BPU1 strict / BPU2 confirmed | **0 / 0** |
| Rejected events | four missed-callback sessions; no other logged reject reasons |
| Executed trades / TVX fills | 0 / NOT TESTED |

**Nearest observed native M5 extrema relative to original RAW pivots (tick=$0.01 for these cases):** **ADBE May 3 short ≈2 ticks ($0.02)** and **FTNT May 8 short ≈2 ticks ($0.02)** were nearest. Neither exactly touched the pivot as required. Next was JNJ May 2, 8 ticks ($0.08), then JNJ May 14, 21 ticks ($0.21). A two-tick miss is **NOT an exact touch**, even if that seems close visually. These are **minimum absolute distances in the checked closed M5 extrema**, not verified tick-by-tick prices or entries.

**Coverage warning — do not mislabel this as a full-month negative result:** every one of the 13 ready cases had exactly **77 validated M5 candles** (`13 × 77 = 1,001`). An uninterrupted regular US equity session normally contains **78 complete five-minute periods** from 09:30 through 16:00. The gap is suspicious and may be explained by the final 15:55–16:00 candle not being emitted by manual `TradeBarConsolidator` replay at an exact-close History boundary; missing last-minute input is another possible explanation. **This is a hypothesis, not yet proved by timestamp evidence.** The backtest's 5,000 M1 bars versus a hypothetical 13×390=5,070 also warrants checking actual closed minute coverage, but missing minutes may reflect real market data availability. Therefore the hard result is **zero observed BPU1 in the available 1,001 validated M5 bars**, not zero possible BPU1 throughout all 13 complete sessions.

**Data-universe coverage warning:** 4 of 22 intended scans were **skipped**, not screened with zero qualified tickers. The Saturday Fundamental callbacks are real, but this experiment still keys selection by the callback's same calendar day. Coverage is only **18 of 22 market sessions**, not a complete 22-day universe. Do not silently infer Monday candidates or retest those days using hindsight.

**Targeted research instrumentation now added to GitHub only:** `research/cohort_cloud/main.py` retains identical Fundamental/D1 origin/basis/Shadow/BPU1/BPU2 logic, but now includes `QWCT COHORT TAIL` for up to four actual symbol-days and summary counts `m1_tail_close`, `m1_tail_early`, `m5_tail_close`, `m5_tail_early`. They print true last native minute and true emitted native M5 timestamps vs exchange close — **without manually flushing, manufacturing missing bars, or relaxing any pattern rule**. This modified code is **NOT what produced the real May run**; these additional tail metrics are **native unverified** until a new backtest.

**Next bounded action:** do **not** rerun the unchanged six April cases or claim "BPU detector broken". Current updated code defaults to **June 2024**: check M1/M5 tail provenance first in that next independent monthly run, so positive/negative signal counts carry valid coverage. Then separately design an explicit, causally safe weekend-callback→Monday effective-session policy if improving coverage is required. Do not fit a two-tick tolerance or use the cluster median as an exact BSU. Manual Gerchik BSU validation and actual -30s SEC/TICK TVX remain separate later gates.


**Status:** One real May 2024 native QuantConnect 2.6 run completed; see evidence above. Later tail-diagnostic code revision is not yet native-tested. No trading orders, SEC/TICK data, backtested fills, or claimed profitability.

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

**Current defaults in updated `main.py`:** `scan_start = 2024-06-01`, `scan_end = 2024-06-30` (new independent month; earlier May run already completed). Custom date span allowed only up to **35 calendar days** per run. **Saved QuantConnect project parameters OVERRIDE these defaults** — remove/update any saved May dates. Expect `QWCT 2.6 COHORT ACTIVE 2024-06-01..2024-06-30`. Do **not** rerun unchanged April or May evidence.

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
