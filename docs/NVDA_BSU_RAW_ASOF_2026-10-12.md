# D1/M5 as-of price normalization — 2026-10-12

Status: committed to `main` as research-only. No broker orders or fill claims.

## Reproduced issue

User's completed QuantConnect Cloud smoke (2024-01-01–2024-02-05)
reported NVDA accepted D1 bounce/short `50.2660` on 2024-01-02,
then `BSU historical origin off native tick grid; normalization unsafe`.
Six accepted D1 setups, 456 M5 checks, 0 research candidates/intent and
0 exceptions. The chart displayed historical NVDA around $50, i.e.
post-2024-split historical scale rather than the actual early-2024
trade-price level.

## Independent ready/native solution (official LEAN docs)

- US equity **requesting data**:
  https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
  `SPLIT_ADJUSTED` uses *all future* split history for historical
  bars; this is not the 2024 native price basis. `RAW` provides
  contemporaneous trade prices for algorithm subscriptions.
  `SCALED_RAW` is history-only and adjusts bars using only actions
  known before the current algorithm time.
- US equity **corporate actions**:
  https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions
  Official LEAN uses `SCALED_RAW` for rewarming indicators after
  split/dividend events. Existing split quarantine is retained.
- Historical **history requests**:
  https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests
  Supports per-call `data_normalization_mode`; typed TradeBar History
  and live subscriptions can be on different, explicit bases.
- Historical **common errors**:
  https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/common-errors
  Factor-file numerical precision may cause date truncation; the
  native warning is not a reason to fabricate missing data.

## Implemented minimal change

In `main.py`:
1. Both the MINUTE (default) and SECOND (TVX opt-in) universe and
   anchor subscribe in `DataNormalizationMode.RAW`.
2. Typed daily `history[TradeBar]` warmup uses
   `DataNormalizationMode.SCALED_RAW` in **both** modes.
3. Retain already-present native `SplitOccurred` invalidation and
   rewarm; no price multipliers, synthetic OHLC, threshold changes,
   opening a trading gate, or enabling entries/exits.
4. Source regression checks ensure package output preserves this mode.

## Required separate Cloud verification

1. Rebuild exact 24-Python-file Free bundle from current main; in
   QuantConnect Cloud keep `research.ipynb` as file 25. Only `main.py`
   should need replacement if the rest of the Cloud Python files
   already match the prior tested 24-file bundle.
2. Backtest default **2024-01-01–2024-02-05**, `tvx_seconds` unset.
   Confirm launch line says `RAW as-of/SCALED_RAW D1`, no exceptions,
   and orders disabled. Verify native NVDA Jan 2 raw price
   approximately 10x previous split-adjusted plot (actual print
   must come from Cloud, not an invented reference number).
3. Compare D1 scenarios, tick-grid BSU reasons, ATR, M5 count and
   8-gate blockers with the frozen preceding Cloud logs.
   A different scenario count is expected with RAW+SCALED_RAW;
   **do not assert** that NVDA will still pass the D1 screen or BSU.
4. Separately evaluate a split crossing the session / warmup range,
   including `SplitOccurred` quarantines. Always fail closed when
   historical dividend/split re-scaling still yields fractional
   historical pivots; do not round levels to manufacture BPU1 touches.
5. Later test SEC TVX opt-in with actual historical SECOND availability,
   costs and exact -30 second receipt. Trading approval remains false.

**Not claimed:** native Cloud retest, removal of *all* historical tick
mismatches, exact discretionary Gerchik BSU, or positive expectancy.
