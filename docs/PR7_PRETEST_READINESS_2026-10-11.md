# PR #7 — preparation completed BEFORE another native LEAN backtest

Date 2026-10-11. Scope: existing draft PR #7 only. No execution enablement.
Source of truth: `docs/strategy_spec.md`; implementation risk audit:
`docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md`.

## What documentation actually supports

1. **US-equity price normalization.** QuantConnect `SPLIT_ADJUSTED`
   modifies historical prices using the **complete split history**, even
   events after the day of the historical signal.
   `RAW` preserves actual as-traded prices, while historical
   `SCALED_RAW` helps prime indicators against the current-as-of split
   scale. Neither a one-line RAW migration nor pretending a historical
   split-adjusted $0.01 tick equals an as-traded native $0.01 tick is
   justified:
   https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
   https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions
2. **Fundamental universe** uses a different daily data stream with
   `f.price`, `f.volume`, `f.dollar_volume`, and
   `f.price_scale_factor`; current subscription uses
   `SPLIT_ADJUSTED` for minute/M5 and typed D1 history. Absolute Gerchik
   thresholds $5 and $1 ATR and tick tolerance therefore require a
   **verified historical price/volume scale** before validation.
   Native universe docs explicitly reset/warm indicators after
   price-scale-factor changes and use `SCALED_RAW` history:
   https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes
3. **Minute / second / tick data** are distinct equity subscriptions.
   Minute-only universe cannot prove 30-second-before-BPU2 close. Seconds
   may be missing when no trades; fill_forward disabled is necessary but
   still not cryptographic provenance. A full 270 positive-volume
   second-chain requirement is intentionally **overstrict** and not a
   canonical Gerchik condition:
   https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
4. **Time.** Market-hours API `security.exchange.hours.get_next_market_close`
   accounts for native closures/half days. LEAN consolidator outputs are
   completed aggregated bars with actual EndTime; do not create artificial
   BPU2 preclose timestamps from M5:
   https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours
   https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators

## Added before a Cloud test in this update

- `strategy/native_m5_validation.py` validates already-delivered
  native M5 OHLCV (positive traded volume, valid finite OHLC, native
  end time on 5-minute boundary, explicit no-fill-forward flag).
  This is a **conservative research admission requirement**, not an
  invented data provider. A rejected source candle is never used by
  the level-touch observer or M5 signal checker.
- `strategy/m5_runtime.py` rejects malformed/zero-volume M5 before
  updating native pattern and candidate state.
- `main.py` + `strategy/runtime_reporting.py` aggregate bounded
  `Qwct M5 feed rejected` counters instead of logging per candle.
- `tests/test_native_m5_feed_validation.py` and
  `tests/test_native_bpu_runtime_integration.py` cover both pure
  validation and actual extracted callback: a zero-volume wick CANNOT
  be elevated to observed BPU1.
- `tests/test_order_execution_stays_disabled.py` parses EVERY Python
  module under main and strategy, disallows order-submission methods,
  restricts native liquidation to main, and verifies false EOD guards.
- `strategy/features.py` `g03_near_retest` now includes the latest
  already-closed D1 session, rather than incorrectly treating yesterday
  as an unclosed current bar; fixes gap-from-previous-close index.
  `tests/test_strategy_contract.py` covers late D1 touch and actual
  gap reference.
- This branch was tested through GitHub Actions Python compile and
  deterministic tests. **Not** LEAN Cloud, historical fills or broker.

## Problems deliberately not papered over

- **Pre-2024/June NVDA split**: do not use adjusted $50 vs raw ~$500
  to validate an exact historical $0.01 tick, $5 minimum, $1 ATR, position
  size or 0.2% risk. Need native as-of normalization reconciled for every
  price, level, ATR, price increment and share count. **NO price model
  migration is committed.**
- `BsuDetector` still uses D1 native confirmed swing as a research
  BSU proxy, and an ATR-derived stop/20% luft convention. Neither is
  verified canonical. There are no annotated independent true/false
  pattern labels.
- A 5-minute two-bar confirmation is not a complete Gerchik model.
- No proof of native historical SEC/TICK subscription access, price
  provenance, quote spread, borrow/short availability or any TVX fill.
- No authoritative LEAN closed-trade risk ledger / day/week/month
  portfolio-equity anchors / protected partial-fill solution.
- `RiskSnapshot.mechanical_pass` is NOT broker approval and
  `RiskPreflight.can_submit=False`; native risk gate stays
  UNKNOWN or FALSE; no trades.

## Acceptance contract for the NEXT deliberate native Cloud run

Before execution, upload the **entire branch** (Cloud editor does NOT
automatically sync with GitHub), including:
`main.py`, all current `strategy/*.py` imports, especially
`native_m5_validation.py`, `m5_runtime.py`,
`lean_risk_observer.py`, `risk_research.py`, `bsu_bridge.py`,
`patterns_bsu.py`, `signals.py` and `features.py`.

A single controlled 2024-01-01—2024-02-05 minute-only smoke must
be evaluated against these falsifiable checks (not against an expected
count of profitable or approved trades):

1. Compile/initialize with native LEAN 2.5, no runtime errors and no
   missing new Python modules. **Orders 0, positions 0, trades 0.**
2. Confirm universe-selected US stocks have **native** D1/ATR snapshots,
   a frozen 09:29 scenario and valid current-session M5 TradeBar candles.
3. Check `Qwct M5 feed rejected` counter and rejection causes. If large,
   inspect provider fill-forward/zero-volume semantics; NEVER replace
   missing real trades with fabricated bars.
4. Compare exact D1 price, ATR and minimum tick for an actual 2024
   pre-split stock (NVDA 2024-01-02) **on both contemporaneous raw
   and configured adjusted scales** before claiming Gerchik filters.
   The old 2024 backtest does NOT establish equivalence.
5. Verify per-symbol levels/BSU proxy source bars, timestamp and
   observed native BPU1/BPU2 vs exact bar OHLC. A clean zero BPU2
   count is acceptable if no legitimate two-candle pattern occurs.
6. Native partial risk adapter must report UNKNOWN (or FALSE when
   blocked) and must not place orders; record any method-not-found,
   unaligned time, short-margin or availability rejection as a bug.
7. Check Qwct Focus chart has one ticker's real candles, D1 level
   at that price scale, research chart stays within series cap,
   bounded trace logs stay within Free Cloud budget.

**Additional later targeted research** (ONLY if warranted by an
unresolved data-basis issue): native split boundary around NVIDIA
2024-06-10, and native exchange half-day 2024-07-03. Do not expand
the next smoke to huge date ranges merely to create "signals".

## Release

Keep this PR open/draft until native integration defects (if any)
are resolved. A green GitHub CI does not certify LEAN. No paper,
live or Schwab orders, no invented fills, no merge as fully complete.
