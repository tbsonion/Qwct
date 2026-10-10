# First actual Qwct QuantConnect cloud LEAN smoke run

Date reviewed: 2026-10-09. User-provided QuantConnect log excerpt from
LEAN Engine v2.5.0.0.18178; the excerpt covers 2024-01-01 through
at least 2024-04-26 (end of backtest is NOT visible).

## Observed runtime evidence (not inferred from Python tests)

- `initialize` ran and printed
  `Qwct: multi-symbol Gerchik signal-only; ALL ORDERS DISABLED`.
- LEAN's equity calendar scheduled the pre-market `SCREEN` callback
  at **09:29 ET** and pre-close `EOD SIGNAL-ONLY` at **15:55 ET**.
  These are observed timestamps for the shown dates; do not claim
  all early-close and live cases have been verified.
- From 2024-01-31, the scanner returned 10 symbols on many dates,
  with nonzero `ATR` and `V20`, but scanner completeness/accuracy
  and Gerchik scenario correctness have NOT been verified.
- **Real defect:** repeated
  `Native typed history failed for N symbols: 'TradeBars' object has no attribute 'symbol'`.
  This is NOT an API failure: Qwct treated each outer element of
  batched typed multi-symbol History as a TradeBar, when it is a
  **TradeBars collection keyed by Symbol for each time slice**.
  Official QuantConnect docs demonstrate iterating each `trade_bars.items()`.
- Log throttling occurred (`Your algorithm messaging has been rate limited`).
  No completed-backtest report or end-of-algorithm ObjectStore success
  is shown; signal-intent absence in the visible logs is not proof of
  absent signals because decisions are primarily collected internally.

## Fix applied

`main.py::_warm_symbols`: for each outer `TradeBars` time slice,
iterate `for symbol, bar in bars.items()` before passing a `TradeBar`
to `_append_daily`. Use `bar.end_time` to exclude candles that
are not closed at the current algorithm time. Keep LEAN native typed
History, batch requests, native indicators, and **all execution disabled**.

Regression unit test checks correct outer/inner iteration shape.
This is a source-level regression guard; it cannot replace rerunning
the cloud LEAN engine.

### Official API reference

- https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-responses
  (List[TradeBars], `for symbol, trade_bar in trade_bars.items()`)
- https://www.quantconnect.com/docs/v2/writing-algorithms/universes/key-concepts
  (iterate batched history bars in a dynamic universe)
- https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-performance
  (batch native History rather than 50 individual requests).

## Next free-cloud test: short, no orders

1. Copy the patched `main.py` into the existing cloud Qwct-LEAN-Test.
2. Temporarily set `self.set_end_date(2024, 2, 5)` to shorten the
   historical interval, without changing start date, account funding or
   algorithm trading mode.
3. Re-run in actual LEAN and confirm:
   - **zero** `Native typed history failed` messages;
   - 09:29 ET `SCREEN` has qualified symbols early in January;
   - ATR, V20, and D1 bars are based only on closed daily data;
   - no submitted orders;
   - any scenario exceptions or report-save failures investigated
     separately, not silently omitted.
4. Keep PR draft; do not merge or enable broker orders from a successful
   source-only Python CI test.

**As of writing, the patched cloud re-run has not been observed.**
