# Qwct — evidence-based LEAN pipeline audit (2026-10-09/10)

Status: **source review + actual user-provided Cloud LEAN logs + GitHub CI**.
NOT a completed trading-system certification. No Schwab orders, paper trading,
fill simulations, or profit backtests were used.

## Scope and reference documents

- `AGENTS.md`: only code and signal research; all brokerage execution off,
  no independent OMS / mock broker, no custom indicators/feed/calendar.
- `docs/strategy_spec.md`: Gerchik «Уровни», D1-level preparation before
  opening, M5 confirmation, 8 mandatory ideal-trade gates, 0.2% owner
  risk ($50 on $25k), D1 room >=4R, initial TP >=3R.
- Official LEAN docs:
  - https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-responses
  - https://www.quantconnect.com/docs/v2/writing-algorithms/universes/key-concepts
  - https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
  - https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/key-concepts
  - https://www.quantconnect.com/docs/v2/writing-algorithms/statistics/runtime-statistics
  - https://www.quantconnect.com/docs/v2/writing-algorithms/charting

## Real Cloud LEAN evidence — what actually happened

1. Original 2024-01-01..2025-01-01 smoke ran to completion,
   LEAN 2.5.0.0.18178, 12,419,549 data points. It **repeatedly**
   reported `'TradeBars' object has no attribute 'symbol'` while also
   printing `SCREEN` (10 qualified) and `EOD SIGNAL-ONLY`.
   ObjectStore write failed with an organization permission error.
2. User applied corrected source and ran 2024-01-01..2024-02-05.
   LEAN completed the 1,247,678-data-point smoke in **57.36 seconds**.
   Scanner reported 10 qualified on Jan 2 and subsequent days. The
   supplied short-run log had **no repeat TradeBars failure**; report
   execution remained disabled and portfolio equity stayed $25,000.
3. The short run **did not show an end-of-run count of accepted D1
   scenarios, M5 qualifying gates, rejected setups, or emitted
   intents**. Absence of a `SIGNAL` message is NOT proof of
   correctness or zero opportunities (log rate limiting also occurred
   in the previous long run).
4. The refreshed diagnostic code added AFTER that smoke (charts,
   `set_runtime_statistic`, M5 feed counters and Free-tier report
   summary) has **NOT BEEN VERIFIED in Cloud LEAN yet**.
   Its source-level Python CI is distinct from actual LEAN behavior.

## Code verified against official API

| Stage | Native implementation | Evidence | Remaining gap |
| --- | --- | --- | --- |
| Fundamental universe | `add_universe` and synchronous `on_securities_changed` | 10 live historical qualified names appeared | Candidate ranking/quality vs intended tradeable universe unverified |
| Native batched D1 history | `history[TradeBar](symbols,180,Resolution.DAILY)`, outer `TradeBars`, inner symbol/bar | Cloud failed before fix; succeeded after fix without same error | No independent per-bar/adjustment-time comparison to LEAN |
| Native indicators | `AverageTrueRange(14,WILDERS)`, native SMA(50), native volume SMA(20) | ATR and V20 in scanner log | Indicator timestamps, normalization, and daily close still not independently checked |
| D1 Gerchik levels | `levels_for_session`, confirmed fractal + next-day `valid_from` | Pure as-of tests | No demonstrated ground-truth level quality on actual price charts |
| Scenario evaluator | 14 features + 3 weighted models, min score 4 | Source/unit checks | Actual acceptance counts unknown, exceptions are internally converted to `FeatureResult(None)` |
| M5 feed and confirmations | 5-minute native `consolidate` callback, time-based `MarketData` | LEAN compilation and runtime reached end | Number of delivered bars/eligible gate checks unknown in last observed Cloud run |
| Session windows | `SessionPolicy` ET windows | Source only | Runtime acceptance and early-close edges unverified |
| Execution | `_native_exit_enabled = False`, entry review `can_submit=False` | Native Cloud signals-only logs, zero holdings | **No live/paper/broker execution is certified** |
| Reporting | Free org cannot save ObjectStore | Explicit LEAN permission error | Complete CSV journal NOT exported on Free; only short stats/plots available after unverified diagnostics |

## Serious unresolved gaps — DO NOT call them complete

### P0: the eight risk gates do not imply approval to submit

`strategy/signals.py::evaluate_gates` calls the real `risk_mgr`
only when one is supplied. `main.py` calls `build_intent` with
`risk_mgr=None`. Thus `risk_approved=True` currently means **only a
preliminary cash/shares-per-stop calculation**, NOT checking open positions,
past losses, daily/weekly/monthly limits, attempts, portfolio reservations,
or native buying power. Since all orders are hard disabled, this is a
**research classification** defect, not an executed-risk failure.
Never interpret an `INTENT` as a permitted protected trade.

### P0: unknown behavior of Gerchik levels/signals on native LEAN data

Source tests cover pure feature contracts and synthetic deterministic
fixtures. They do not demonstrate that live D1 data has acceptable levels,
the three models choose correct scenarios, M5 confirm bars have correct
times, and minimum room >=4R vs the true next level is fulfilled.

### P1: 22 configured controls not consumed by the active runtime pipeline

A source-wide search (main and strategy modules, excluding config) found
the following config fields with **no code reference**:

- Risk/limits: `max_daily_loss_pct`, `max_weekly_loss_pct`,
  `max_monthly_loss_pct`, `max_daily_risk_pct`,
  `max_losing_trades_per_day`, `max_positions`,
  `max_trades_per_day`, `losing_days_break`, `break_days`.
- Execution/market safeguards: `max_spread_bps`,
  `max_entry_distance_atr`, `limit_order_timeout_min`,
  `max_attempts_per_level`, `reentry_cooldown_min`,
  `data_stale_after_min`.
- Session/exit/other: `timezone`, `session_open`,
  `session_close`, `scale_out`, `trailing_atr`,
  `giveback_pct`, `bsu_max_bars_back`.

Some are deliberately future execution constraints, not needed for the
signal-only runtime; others such as `max_entry_distance_atr` and
`max_spread_bps` must not silently be treated as active filters.
There are still separate hard-coded ET and market-calendar settings.
Source search alone cannot determine the desired implementation policy.

### P1: "familiar symbols only" is not enforced

The written Gerchik spec restricts trading to familiar instruments.
Current automatic top-liquidity fundamental universe has no explicit
approved-symbol list. Therefore the screener output is a **candidate list**,
not permission to trade those securities.

### P1: error diagnostics lose detail

`strategy/features.py::evaluate_all` catches a feature exception and
produces an unknown `FeatureResult`; the scenario scoring counts only
true features. Those per-feature errors do not necessarily appear as a
`Qwct errors` count. For score-below-threshold outcomes,
`ScenarioEvaluator` can return an empty `features` map.
An absent D1 scenario should never be labelled a no-opportunity
finding without examining these causes.

### P2: NaN ATR error was misleading

A source-level test generated a NumPy `Mean of empty slice` warning
while computing the level-cluster tolerance when native ATR was absent.
`detect_levels` now returns an empty list before median if no positive
finite native ATR is ready. It adds no substitute ATR or synthetic data.

### P2: log rate limits and unnecessary work

The old runtime printed large scanner/EOD messages on each day; LEAN
throttled browser logs. The latest branch reduced EOD log volume
and adds compact native charts/stats. Runtime performance of repeated
DataFrame reconstruction / level calculation on M5 has not yet
been profiled and must not be claimed solved.

## Changes made on the unmerged research branch

- Correctly iterate each `TradeBars.items()` item in batched typed D1 history.
- Hard-disable paid ObjectStore writes on Free; do not claim CSVs were saved.
- Add native charts / runtime statistics for D1 scenarios and signal intents.
- Count M5 bars separately from M5 checks, and count failed gate checks.
- Fix missing-ATR median warning; add source/pure-rule regression tests.
- Fix accidental stale-assertion GitHub CI failure introduced during the
  earlier diagnostics update.

Changes are **not merged**. No brokerage submissions were added or enabled.

## Required acceptance evidence before any broader claim

1. Actual Cloud LEAN source must be synchronized to the target commit.
   For a cheap run, set Jan 1 to Feb 5, 2024. Keep `_native_exit_enabled=False`.
2. **Compile and complete without any unexpected handled error**.
   Confirm actual date range/algorithm ID before comparing logs.
3. Verify native `Qwct Research` plots plus `Qwct M5 bars`,
   `Qwct M5 checks`, `Qwct D1 setups`, `Qwct rejects`,
   `Qwct errors`, `Qwct intents` counts. Distinguish
   no D1 setups vs M5 data missing vs failed M5 gates.
4. Validate selected days against the native LEAN historical
   price/ATR/volume snapshots. Preserve the prior-day/closed-bar boundary.
5. Hand-check examples of D1 swing level validity, score/provenance,
   model/side, M5 gate, entry/stop geometry and minimum 4R room.
6. Export a full auditable decision journal **using a supported method**.
   The Free Cloud organization currently rejects ObjectStore writes.
7. Do not merge, enable brokerage, or call the strategy profitable/
   protective without separate explicit authorization and native tests.

**Truth boundary:** GitHub CI passing means source/pure tests pass.
It is NOT proof that the unverified diagnostic modifications run in
LEAN or that a Gerchik signal would be executed safely at Schwab.
