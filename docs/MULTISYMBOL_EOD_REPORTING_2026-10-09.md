# Native multi-stock analysis, end-of-day exits, and trade reports
Date: 2026-10-09. **Stacked on PR #2 (unmerged screener). No trading enabled.**

## Evidence: official QuantConnect + Schwab documentation (read FIRST)

### Multi-stock analysis

- [LEAN Fundamental Universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes): native daily constituent selection
- [LEAN Universe Settings](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings): `Resolution.MINUTE` for selected US equities, allowing M5
- [LEAN Universe Events](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/key-concepts): `on_securities_changed` for dynamic membership
- [LEAN Consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators): native D1 and five-minute candles, remove consolidators on universe removal

`main.py` now creates separate native LEAN indicator snapshots, daily
bars, M5 bars, pre-open scenario and one-day qualified flag for each
selected liquid stock. It evaluates the original Gerchik conditions
across up to `screener_watchlist_limit` stocks **simultaneously**. The
underlying universe's maximum is `screener_candidate_limit` (50) minute
subscriptions, not just daily candles, because a real M5 path requires
minute data for each. No extra API client or fake market data.

When a security leaves the universe, the associated LEAN consolidators
are unregistered so old subscriptions don't leak. A security that still
has a position/open LEAN order is **not silently forgotten**. The code
does **not** send orders or enforce actual portfolio `max_positions`.

### EOD — critical Schwab cancellation issue

- [Schwab broker integration](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab), **Position_Sys_0001**: canceling stops while
  also sending a liquidation market order can be rejected as overbought/
  oversold; first cancel all open orders and give Schwab about **one
  minute** to confirm, THEN call `liquidate()`.
- [LEAN Transaction Manager](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-management/transaction-manager):
  `transactions.cancel_open_orders()`, `get_open_orders()`.
- [LEAN Liquidating Positions](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/liquidating-positions):
  `liquidate()` submits native market orders across the whole portfolio;
  it tries to cancel pending orders itself but broker confirmation can lag.
- [LEAN Scheduled Events](https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events):
  `before_market_close(symbol, minutes)` uses actual exchange close
  and early close, not a homemade 16:00 assumption.

Three LEAN scheduled callbacks use the clock ticker's US-equity calendar:
1. **T-8 minutes** (config EOD T-5 + 3) stop signals and cancel all
   outstanding open orders **via LEAN**.
2. **T-5 minutes** check that `transactions.get_open_orders()` is empty;
   if not, log **EOD CRITICAL, NOT FLAT** and block overlapping liquidation
   requests. If none are open, `self.liquidate(tag="GERCHIK EOD FLAT")`
   closes *all* LEAN portfolio positions, not only the watchlist.
3. **T-1 minute** verify again via LEAN Portfolio and Transactions and
   log **EOD CRITICAL, NOT FLAT** if any holdings/orders remain.

**All three exit actions are HARD DISABLED** by
`self._native_exit_enabled = False`, a non-configurable code constant.
No live, paper or backtest orders are submitted. Even when later
authorized, the above is **not proof of guaranteed flat**: Schwab
cancel acknowledgements, partial market fills, broker failures,
frozen symbols and market closures can leave exposure, so real
brokerage testing and user-approved failure response are required.
A documentation-backed 'fail closed' guard is not a substitute for
operational liquidation assurance.

### Full journal + reports: use LEAN as the source of truth

- [LEAN OnOrderEvent](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-events) supplies genuine order statuses and fill events.
- [LEAN TradeBuilder](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/trade-statistics) supplies completed round-trip trades and P&L.
- [LEAN Object Store](https://www.quantconnect.com/docs/v2/writing-algorithms/object-store): store CSV and JSON once at algorithm end, or daily in live, in a unique `project_id/algorithm_id` namespace.
- [LEAN event handlers](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/event-handlers): `on_end_of_day(symbol)` and `on_end_of_algorithm()`.

`main.py` exports on `on_end_of_algorithm`, or daily in LEAN `on_end_of_day` during live operation:
- `signal_decisions.csv` — premarket scenarios, declines/errors and
  accepted signal intents for **every** watchlist ticker
- `native_order_events.csv` — *actual* LEAN `OnOrderEvent` events only;
  no invented fills or second order state machine
- `native_closed_trades.csv` — directly from
  `self.trade_builder.closed_trades`
- `summary.json` — signal count, native event count, closed-trade count,
  winning-trade count and closed-trade P&L from LEAN TradeBuilder

Since Qwct cannot place any order, order/trade CSVs will currently contain
headers and **zero trade rows**. That's correct, not an error.

Limits: This is **not yet a crash-proof cross-restart live journal**.
Native `on_end_of_day` checkpoints the reports for the clock ticker once
per live trading day; `on_end_of_algorithm` saves once at backtest end.
Unexpected crashes between daily checkpoints can lose recent events.
`on_end_of_day` timing and ObjectStore permissions require a LEAN test. ObjectStore may require
specific cloud write permissions, so failed saves are logged. It is not
an Excel/Google Sheets integration or an audited broker reconciliation.

## Known hard blockers / required LEAN runtime verification

1. Real LEAN loading and Python interop for
   `on_securities_changed`, `history[TradeBar]`, dynamic
   `self.consolidate`, callback timing and
   `subscription_manager.remove_consolidator`.
2. Single manually added clock ticker can overlap selected universe
   constituents; validate such a case and no duplicated minute streams.
3. Universe may remove a currently invested holding; verify LEAN
   subscriptions remain valid until brokerage positions are closed.
4. All per-symbol D1 SMA/ATR state as-of just **closed** bars, no future
   leak. Check corporate action split normalization and early close.
5. Actual Schwab cancel->ack->liquidate status behavior, including
   contingent stops, partial fills and position flat check. Do not
   claim reliability from static tests.
6. Real `OrderEvent`, `TradeBuilder.Trade` attributes and ObjectStore
   permission in the selected runtime.
7. Real LEAN runs and Schwab broker order submissions require separate
   user authorization. No custom OMS/OCO/fake fills.

### Definition of current status

- Multi-stock analysis: **CODE IMPLEMENTED, RUNTIME NOT VERIFIED**.
- EOD liquidation: **NATIVE API PATH WRITTEN, HARD DISABLED / BROKER NOT VERIFIED**.
- Trade journal/report export: **CODE IMPLEMENTED, LEAN IO NOT VERIFIED**.
- No independent implementation of account/fills/calendar is allowed.
