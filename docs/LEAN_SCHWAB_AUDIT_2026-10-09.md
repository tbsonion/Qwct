# Native LEAN / Schwab documentation audit — Qwct PR #2 and PR #3
Date: 2026-10-09. Audit branch `fix/native-lean-audit-20261009`
Stacked on PR #3; this is an UNMERGED review, not an engine test.

## Source hierarchy
- Official [QuantConnect Schwab integration](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab)
  including `Position_Sys_0001`: cancel live resting stops, wait for
  broker confirmation (~1 minute), then liquidate; don't trust immediate
  asynchronous cancellation/closing.
- Official [LEAN Trade Statistics](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/trade-statistics):
  default TradeBuilder `FillToFill`, optionally `FlatToFlat`.
- **Actual upstream LEAN Trade.cs source**:
  https://github.com/QuantConnect/Lean/blob/master/Common/Statistics/Trade.cs
  documents `ProfitLoss` as **gross** and `TotalFees` as separate
  positive amount. `Fees` is **not** a `Trade` property.
- Official [LEAN ObjectStore](https://www.quantconnect.com/docs/v2/writing-algorithms/object-store):
  `self.project_id`, `self.algorithm_id`, `save` documented.
- Official [LEAN Scheduled Events](https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events):
  `time_rules.before_market_close` and `after_market_close` are
  tied to the exchange calendar.
- Official [LEAN Market-Data Consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators):
  `consolidate` returns a consolidator and
  `subscription_manager.remove_consolidator` is REQUIRED for
  dynamic universes.
- Official [LEAN Fundamental Universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes):
  `add_universe(filter)` automatically subscribes to returned symbols,
  with significant memory consumption per symbol; excludes ETFs/ADRs
  in the Morningstar fundamental universe.

## Confirmed code defects corrected on this branch

**A1 / Incorrect commission field (major reporting defect):**
Prior reporting used `getattr(trade, "fees", "")`, which silently
produced a blank field on actual QuantConnect `Trade` objects.
Changed to direct documented `trade.total_fees` — missing native field
now raises, rather than faking zero or silently losing fees.

**A2 / Profit before fees incorrectly treated as realized net P&L:**
LEAN `Trade.ProfitLoss` is GROSS. Former `summary_json` summed it as
realized profit and counted winning trades without commission. Now
reports `closed_trade_gross_profit_loss`,
`closed_trade_total_fees`,
`closed_trade_net_profit_loss` and net winning count separately.
All inputs from LEAN TradeBuilder; no custom fill/P&L simulation.

**A3 / TradeBuilder grouping mismatch (analytics semantics):**
Previous comments promised closed round-trip positions, while LEAN
defaults to `FILL_TO_FILL`. Set native
`TradeBuilder(FillGroupingMethod.FLAT_TO_FLAT, FillMatchingMethod.FIFO)`
in `initialize`. This is an official LEAN option, not a custom
trading state machine.

**A4 / Daily checkpoint timing ambiguity:**
`on_end_of_day(symbol)` is a per-security LEAN event and not a
documented guarantee that all scheduled broker cancellations, fills
and after-close operations are finished. Replaced live checkpoint with
explicit native `Schedule.On(EveryDay(clock), AfterMarketClose(clock,1))`.
In backtest, save at end of algorithm. This still DOES NOT create
crash-proof persistence; in live scheduled events occur on a separate
thread. No UI/report claim of verified runtime behavior.

## Open issues / incorrect prior confidence — NOT solved by documentation

**B1 / EOD FLAT isn't guaranteed (P0):**
`_native_exit_enabled = False` so no cancel or liquidation is currently
active. The disabled code cancels at T-8, liquidates at T-5 IF no
open/cancel-pending orders, and checks at T-1. Schwab can reject,
partially fill or delay liquidation. If cancellation still pending,
code returns with an open position — the FAIL-SAFE path avoids
duplicate orders but **does not satisfy** the promise 'always flat'.
This cannot be called operational until actual LEAN/Schwab verification
and a broker-supported contingency procedure. Do not invent retries,
synthetic OCO, order shadow state or expose a runtime toggle.

**B2 / No real LEAN Python runtime test (P0):**
19/19 existing CI tests verify pure logic, CSV formatting and source-code
strings. NONE loads `AlgorithmImports` or instantiates a genuine
`QCAlgorithm`. Confirm exact overloads and chronological behavior for
`history[TradeBar]`, `on_securities_changed`, `consolidate`,
`ObjectStore`, and Schwab `Transactions` in real LEAN. Do not use
mock broker tests as a substitute.

**B3 / Existing scanner excludes valid stocks (P1):**
The scanner's first pass requires previous ONE-DAY volume >=500k, before
it checks SMA20 volume >=500k. Stocks with one low-volume day but valid
20-day average are excluded. Universe is limited to 50 top dollar-volume
stocks and Morningstar fundamental data excludes ETFs/ADRs. This is a
deliberate resource-limited prefilter, not a full-market Gerchik scan.
Do not say the full original filter is implemented.

**B4 / Historical data timing, corporate events, subscriptions (P1):**
Need evidence per ticker that daily bars/ATR/SMA use only closed days,
minute subscribers emit complete M5 data, market-close and half days
work, and split-adjusted historical data aligns with live prices.
Check 50-symbol resource requirements; LEAN docs estimate ~5MB per
fundamental security and dynamic consolidators require cleanup.

**B5 / Report durability and native events (P1):**
End-of-run and live-after-close ObjectStore reports remain an in-memory
accumulation until checkpoint. Abnormal shutdown loses new events;
restart changes AlgorithmId/key and does not restore earlier entries.
Native OrderEvent is authoritative when connected, but this code
isn't live-connected; empty order/trade CSVs are expected. Needs real
ObjectStore permission/version verification.

**B6 / Multi-symbol feature is signal-only (P1):**
Separate D1/M5 state exists for up to 10 qualified tickers, but portfolio
position limits (max 3), risk-per-trade/buying power, order lifecycle,
multi-ticker execution and durable real fills are not implemented.

**B7 / Prior PR #3 assumed strategy risks were fully solved (P1):**
EOD scheduler does not implement stop-loss/TP order cancellation behavior,
and `self.liquidate` alone cannot guarantee broker flat. Intraday
portfolio risk/position rules remain unimplemented. Retain explicit
blockers rather than writing a second OMS.

## Acceptance and safety rules

- Only official LEAN/Schwab supported operations. No custom brokerage
  adapter, order manager, synthetic fills, market calendar or ATR engine.
- Avoid changing old PR #2 / PR #3 retrospectively without review;
  this audit is a stacked Draft PR.
- Do not enable real/paper trading or merge on behalf of the user here.
- Verify accounting with fees-inclusive tests and actual LEAN trade model.
- A passing GitHub Actions Python CI check is **not** a LEAN integration test.

Summary: Two verifiable reporting bugs fixed, default round-trip
grouping corrected, and EOD journal checkpoint scheduled after close.
EOD liquidation, order partial fills, actual LEAN compatibility,
and Schwab-specific behavior remain blocked and explicitly unverified.
