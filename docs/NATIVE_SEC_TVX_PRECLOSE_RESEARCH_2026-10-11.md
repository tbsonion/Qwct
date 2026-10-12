# Gerchik BSU → BPU1 → BPU2 → −30s TVX: LEAN SECOND research

**PR #7, 2026-10-11. Research code only.** No trades, no mock orders,
no backtested performance, and no native Cloud backtest claimed.

## Verified existing components before implementation

Original Gerchik BPU rules: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
- Exact tick-level BPU1 hit; BPU2 immediate next M5 does not
  pierce BPU1 extreme; BPU2 allowable luft 20% of stop.
- **TVX is evaluated 30 seconds before BPU2 CLOSE.**
- D1 swing proxy is not identical to a discretionary original BSU.

Official LEAN APIs (not custom feed/consolidators):
- https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
  — US Equity supports `Resolution.SECOND` TradeBars, default fill-forward.
- https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
  — native 5-minute Consolidate from a SECOND source.
- https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events
  — Scheduled Events execute **before** consolidators and on_data;
  a scheduled 09:34:30 callback cannot read that second's new bar.
  This code observes the actual completed SEC bar in on_data instead.
- https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings
  — `UniverseSettings.Resolution` applies to members of Fundamental Universe.

External ready-made Gerchik code inspected as reference only, NOT
copied or presented as a verified intrabar TVX:
- Apache 2.0 levels https://github.com/BulatNS31/SwingTraderAI/blob/main/swingtraderai/indicators/bsu_bpu_levels.py
  — ATR-tolerant historical BSU/BPU touch counts, no preclose TVX;
  it cannot replace native original-pivot/tick-level precision.
- https://github.com/jhnbek/botArtjahan/blob/main/knowledge_bot/scn003_bsu_bpu_m5_backtest.py
  — D1/M5 level selection, BPU1+BPU2, 20% luft, but **simulates
  fills** after reviewing complete M5 and cannot prove original TVX
  30 seconds early. Its trade simulator was NOT imported.
- https://github.com/LeonidCharikov/MyTradingBot/blob/master/analyzer.py
  — BPU2 **postclose** detection, no exact intrabar TVX.

## Native Qwct approach

Default runs use existing `Resolution.MINUTE` Fundamental Universe,
the same previously tested LEAN native M5/D1 consolidators, and
**do not claim** any 30-second TVX observation.

**Opt-in for dense one-second research backtest:** add a QuantConnect
project parameter `tvx_seconds=true` before starting a Cloud backtest.
Then the **native universe** uses `Resolution.SECOND` for its existing
members; **existing native** `self.consolidate(symbol, timedelta(minutes=5), ...)`
produces completed M5 bars and `self.consolidate(symbol, Resolution.DAILY, ...)`
produces D1. No second subscription for an already-subscribed symbol.

**Cost warning:** this changes up to 50 universe equities to *second*
resolution, not just the 10 selected after the 09:29 screening. That may
be too many subscriptions/data points for a free Cloud backtest;
reduce scope *explicitly* for research before increasing dates or
running a full month. This is not yet measured. Never claim opt-in
sec mode worked in Cloud without actual LEAN runtime validation.
The manually subscribed clock ticker may retain its minute
resolution even if separately selected by the universe; treat missing
second provenance as UNKNOWN, not a passed TVX.

The `main.py::on_data(Slice)` handler calls
`strategy/second_runtime.py::process_second_slice`. Only symbols
selected for the day's D1 watchlist with a native BSU proxy
(and BPU1 already closed) are inspected. For other symbols no
intrabar price signal is fabricated.

`strategy/m5_runtime.py::process_m5` after a native-validated M5 BPU1
arms one `NativeSecondTvxWindow`, ending at `BPU1_end + 5min - 30s`.
`strategy/native_second_tvx.py` is a **strict observation window**,
not a feed or consolidator. It accepts exactly consecutive completed
native 1-second bars with `Time`, `EndTime`, `Period=1s`, positive
traded volume and sound OHLC. It aggregates only the real observed
high/low/last price; never interpolates missing ticks, never uses
end-of-M5 high/low in the preclose check and never guesses a future
close. **If even one of 270 seconds is missing or invalid, the TVX
candidate remains blocked** (more conservative than a human who
watches sparse trading). Duplicate/late, fill-forward, wrong-symbol,
minute bars all fail closed. Current implementation requires a
continuous traded-second sequence; it may reject many illiquid stocks.

At the completed SECOND bar ending exactly at `HH:MM:30`,
`BsuDetector.observe_preclose(...source="SEC", observed_since=BPU1_end)`
runs immediately. It evaluates the existing tick-level BPU1 extreme,
the 20% luft rule, and records `TVX_SEC_PRE_CLOSE` ONLY as
**provisional evidence**, with `can_submit=False`.

On the subsequent completed native M5 BPU2, the existing
`BsuDetector.on_bar` checks the final high and low also contain
the previously observed partial SEC extremes, and that final M5
has not pierced BPU1 or missed allowable luft. Only then are both
`TVX_SEC_PRE_CLOSE` and `BSU_PROXY_BPU2_CLOSED` counted as
reconciled. A violating closed M5 invalidates prior preliminary
research evidence. If SEC mode was off/unavailable, it produces
a closed BPU2 PROXY record but explicitly says no verified −30s TVX.

**Critical:** a native SEC −30s sample is NOT an order, limit fill,
proof of actual entry price or complete Gerchik BSU. The existing
D1 swing proxy, missing Schwab protective-stop and partial-fill
guarantees, full trade risk gates and split normalization remain
separate validation blockers.

All native orders remain source-level disabled; nothing changed in
native EOD cancellation, liquidation or ticket state management.

## Tests / validation

`tests/test_native_second_tvx_integration.py` drives **the same
extracted M5 and SECOND Slice handlers used by main.py**, with
deterministic native-shaped 270 SEC observations. It checks exact
preclose timestamp (only on the 270th traded second), no future
M5 data, later M5 consistency, disabled mode, one missing second,
zero-volume/fill-forward/wrong-period, other-symbol contamination,
duplicate and early input, mid-BPU2 price penetration and invalidation
surviving the next completed M5. Reports count provisional and
reconciled research events separately.

GitHub Python tests are deterministic fixtures, NOT a native LEAN
Cloud run; a real SEC historical backtest on an explicitly limited
universe/period is still required to validate data availability,
timestamp conversions, BPU2 time, calendar and normalization.
