# Qwct vs other real strategy source files: breakout/retest and native LEAN

Date: 2026-10-11. Requested source-level education and missing-files
audit. Scope: open DRAFT PR #7 only, all trading disabled.
No historical performance backtests, live order tests, profitable
strategy certification, or merge.

## Real inspected external source code (not vague performance claims)

**1. QuantConnect/LEAN official multi-symbol consolidator example**
https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/MultipleSymbolConsolidationAlgorithm.py

Actual code has per-symbol SymbolData, auto-updated TradeBarConsolidator,
period-bound data, indicator updates and a RollingWindow. Qwct has
per-native-Symbol `_symbols`, native dynamic-universe consolidators,
manually fed DAILY ATR/SMA, and bounded M5 rows. Not using RollingWindow
is not automatically incorrect, but Qwct must never accept an M1 candle
as M5 merely because its `EndTime` happens to be on a five-minute
boundary.

Official data contract:
https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods
In LEAN, actual bar `EndTime = Time + Period`, and consolidated M5
really must span five minutes. Source-level validation now requires
`bar.period`, `bar.time` and `bar.end_time` to all agree with a
300-second M5 interval. Python `timedelta.total_seconds()` and
pythonnet/.NET `System.TimeSpan.TotalSeconds` are both accepted.
`tests/test_native_m5_feed_validation.py` and extracted callback
fixtures prove 09:35 M1, 10-minute mislabeled bars, missing start,
inconsistent periods are rejected before any BPU or candidate signal.

**2. Another fully inspectable break-and-retest project, using Alpaca**
https://github.com/Smashthehedgehog/break-retest-daytrader

Read actual files:
- `strategy.py`: MARKING -> HUNTING -> AWAITING_TOUCH ->
  AWAITING_CONFIRMATION -> DONE_FOR_DAY, live tick-based retest, prior
  volume window, trade-day rollover.
- `data_stream.py`: subscriptions to market bars, trade ticks and
  order events; explicit event callbacks.
- `execution.py`: API request for broker bracket entries.
- `risk_manager.py`: testable per-share stop risk arithmetic.
- `db.py`, `dashboard.py`, `tests/test_strategy.py`:
  persistent trade records, monitoring and deterministic state tests.

**IMPORTANT: this repo is EDUCATIONAL, not a verified profitable
strategy. Do NOT copy its trading path.** Two concrete defects from
source inspection:
- `execution.submit_bracket_order` catches API exceptions and returns
  `None`, but `strategy._strike` **still records a trade and increments
  trades_taken_today even when there is no accepted broker order**.
- `data_stream.trade_updates_callback` processes only
  `update.event == "fill"`, ignores partial fills, computes realized
  P&L using the original proposed `entry_price` rather than verified
  weighted actual entry fills, and uses originally requested `qty`
  for closing P&L. Its state cannot prove fully reconciled execution.
  No native LEAN/Schwab order protection can be inferred from this.
Read-only signal QA is safe to learn from, not order mechanics.

**3. Published QuantConnect ORB Stocks in Play**
https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/

This published backtest uses genuine market-hour relative volume,
ATR and risk/capacity management. Its initially divergent Python vs
C# reproduction is a warning about different update frequency,
normalization, slippage and universe. Results are from the historical
samples stated by the authors and **cannot be transferred to Qwct**.
Separate earlier audit: `docs/ORB_STOCKS_IN_PLAY_EXTERNAL_BENCHMARK_2026-10-11.md`.

## Mapping genuine missing capabilities (not blindly missing filenames)

| External files / behavior | Qwct file / state | Audit |
|---|---|---|
| Event-based breakout -> touch -> confirmation state | `strategy/patterns_bsu.py`, `strategy/m5_runtime.py` | Original full Gerchik BPU2 TVX still needs AUTHENTIC SEC/TICK at ~30 sec before M5 close; M5 is only research proxy |
| Real native bar period & event provenance | `strategy/native_m5_validation.py` | **Fixed this turn**: period, time, endtime consistent; earlier Qwct tested only end-clock modulus |
| Native indicator readiness & finite numeric values | `main.py` D1 updates, `strategy/features.py`, `strategy/scenarios.py`, `strategy/signals.py`, `strategy/indicators.py` | **Fixed this turn**: +Inf/-Inf ATR cannot produce proximity/positive scores or stop, +Inf SMA/price cannot confirm trends |
| Native retained recent bars | `_symbols[Symbol].m5_rows` last 80, D1 last 240 | Exists in native Qwct pipeline; not a reason to copy third-party feed/cache |
| Historical first-five-minute volume | `strategy/opening_volume_research.py` read-only | Exists as unit-tested *standalone* comparison, NOT wired to real daily M5 history nor D1 selection; no lookahead permitted |
| Broker API order submission | NONE by design | **Correctly absent** per AGENTS: use native LEAN only after broker/partial-fill validation; never copy external Alpaca `execution.py` |
| Persistent SQLite trading DB | `strategy/runtime_reporting.py` + native `OnOrderEvent` reports; ObjectStore disabled in Free | Real durable lossless trading journal missing; must not invent shadow fills / balances |
| Risk sizing & gross concentration | `strategy/risk_research.py` and partial LEAN observer | 0.2% stop distance arithmetic exists; live portfolio ledger and broker protection UNKNOWN |
| Native order reconciliation, partial entry and exit fills | `main.on_order_event` reports only | **P0 missing**. Actual LEAN transactions/broker restrictions must be proved, not copied from Alpaca |
| Tested re-entry / trade caps | `strategy/config.py`, `strategy/sessions.py`, preview `strategy/risk_research.py` | Research policies are not executed entry/order guards |
| Multi-symbol management | `main.py` native `on_securities_changed` and per-symbol consolidators | Implemented; native LEAN runtime still unverified |
| Market-hour-aware early close | Native `schedule` and `security.exchange.hours` | Right architectural choice; validate native session timing |
| Test suite for state rejects | `tests/test_native_bpu_runtime_integration.py` + `tests/test_signal_safety_regressions.py` | Pure mock-shaped callback tests exist, no native LEAN certification |

## Release hold

- PR #7 remains draft; main unchanged, no broker order path.
- Native 09:30->09:35 US equity real M5 `time/period/end_time`
  compatibility is **still to be run in QuantConnect Cloud**.
  Failing closed on unexpected pythonnet wrappers is safer than
  fabricating bars; investigate native error counters.
- Native historical split basis/tick price, real market conditions,
  SEC/TICK availability, cashflow/period risk baselines, protected
  partial fills and multi-year OOS profitability remain unresolved.
- No third-party strategy is a drop-in Gerchik replacement. No
  actual P&L, fill rate or win rate is implied by a green pytest.
