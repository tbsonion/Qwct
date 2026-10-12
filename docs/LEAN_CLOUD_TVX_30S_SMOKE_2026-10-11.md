# Exact native QuantConnect Cloud smoke — Qwct SEC Gerchik -30s

**Status: NOT RUN.** GitHub pytest is not LEAN and does not prove
market data delivery, matching M5 bars, broker protection, or profit.
Run this only after syncing the entire Qwct PR #7 `strategy/`
package and `main.py` into a dedicated QuantConnect Cloud
**backtest** project. NEVER switch on live/paper trading or remove
`self._native_exit_enabled = False`.

Primary references:
- [US Equities requesting data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data)
- [Corporate actions / native SplitOccurred](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)
- [LEAN Scheduled → Consolidator → OnData ordering](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/getting-started)
- [Cloud create backtest (compile ID/project ID/auth required)](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/create-backtest)
- [Native LEAN Bracket: child stop only after FULL parent fill](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders)
- [Schwab brokerage support and order restrictions](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab)

## How to run

1. Create/refresh an isolated QuantConnect Cloud Python project from
   this PR branch; sync its full `strategy/*.py` tree, not just the
   old `main.py`. Do NOT merge research to main.
2. Verify `_native_exit_enabled = False`, and no broker credentials
   or live deployment in project configuration.
3. Set project backtest parameter `tvx_seconds=true`.
   SEC mode uses official `Resolution.SECOND` + `RAW` data for
   eligible stock subscriptions, with as-of `SCALED_RAW` D1
   history warmup. It restricts the original 50-stock candidate
   universe to the 10 most liquid candidates *before* D1 screening:
   this changes the experiment's symbol selection.
4. First choose a short backtest date range (e.g. a known normal
   trading week) by changing `set_start_date` and `set_end_date`
   in your isolated Cloud smoke copy. The committed original uses
   2024-01-01 through 2024-02-05 and may be too expensive for
   Cloud Free SECOND data. Match dates to available US equity data.
   Do NOT simultaneously change Gerchik thresholds to chase signals.
5. Compile and start **backtest only**. Review job log as well as
   runtime statistics in QuantConnect Results. If Cloud rejects
   SEC entitlement, CPU, quota, source files, or a PythonNet
   signature, capture the exact native exception — no mocked pass.
6. After the normal short test, use a separate narrow test
   interval containing a confirmed equity stock split if data
   is available. Compare native `SplitOccurred` event, D1
   history and M5/SEC prices around that specific event.

## Acceptance criteria

* `Qwct native SEC feed bars > 0` for a session with subscribed,
  watched equities. If zero, the SEC experiment **did not prove any
  second source** even if no exception occurred.
* `Qwct M5 bars > 0` and `Qwct M5 feed rejected` reasons
  examined. Complete M5 must have 300-second native Period and
  native price/volume, not a fabricated 5-minute bar.
* For any available `TVX_SEC_PRE_CLOSE`, inspect its real native
  SECOND bars: `bar.EndTime` must equal `algorithm.Time` and be
  exactly 30 seconds before the prospective BPU2 M5 close.
  The source must have nonzero trade volume and not be fill forward;
  bounded trade-free gaps are logged, never synthesized.
* `TVX_PRECLOSE_REVIEW` must be timestamped at the true -30s
  instant and include only frozen prior-day D1, the *previously
  closed* BPU1 M5, traded SEC OHLC to the cutoff, native-tick
  limit/stop and preliminary 3R/4R/trend/session checks.
  `broker_protection` must always be `UNKNOWN` and
  `can_submit=False` — even if `OBSERVABLE_READY`.
* BPU2 postclose must appear only 30 seconds later as a
  **separate** reconciliation or invalidation. The final 30s OHLC
  must NOT influence the recorded preclose review.
* In split tests, verify `SPLIT_RESEARCH_BLOCKED`,
  `SPLIT_REWARMED_BLOCKED`, zero allowed TVX that session,
  native replacement of D1/M5 consolidators and SCALED_RAW
  history. Check that daily ATR/volume/BSU levels use the same
  point-in-time current-tradable RAW price scale after rewarm.
* No real `OrderEvent` entries, market/limit orders, fills,
  portfolio investments, or live Schwab side effects.

A backtest with zero completed BPU1/BPU2/TVX patterns can validate
SEC subscriptions, M5 construction and no-order safety, but NOT
pattern correctness. Use actual candidate dates when available,
without editing the business rules to fabricate a pass.

## Schwab order-safety gate (separate test, not included)

LEAN documents contingent Brackets on Schwab, but OTO children
activate only after the **complete** parent fill. Ordinary OCO can
cancel the sibling on partial profit fills, while Schwab's
OUO contingency cannot be assumed. An unfilled/partially filled
entry could therefore be unprotected in real execution.
Before any future live/paper entry enabling, separately validate
native brokerage cash/margin model, symbol buying power,
short-sale/locate eligibility, partial-fill/child stop activation,
OCO resize/cancel behavior, order acknowledgments, split-day open
tickets, stop-market slippage, order cancellation before EOD
and actual confirmation that all positions are flat. Never
replace these tests with an invented fill simulator or homebuilt OCO.

**No native QuantConnect Cloud connection or project credentials
are accessible through the available GitHub-only connection.**
This document is a reproducible acceptance specification, not
a claimed execution result.
