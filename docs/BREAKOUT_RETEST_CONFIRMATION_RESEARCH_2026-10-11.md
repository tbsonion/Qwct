# Qwct: completed-M5 breakout → retest → confirmation (read only)

**Status 2026-10-11: coded and unit-tested in DRAFT PR #7; no trades,
no native QuantConnect Cloud integration verification, no profitability
claim, no broker protections or fills.** Not merged.

## Source inspiration, not copied library

Examined `SilunaDev/TraderWolfy/research/engine/setups.py`,
`BreakoutRetestSetup` in source:
https://github.com/SilunaDev/TraderWolfy/blob/main/research/engine/setups.py

Its research state machine arms on a range/Donchian breakout, waits
at most eight bars for return to boundary within 0.2 ATR, rejects a
0.5 ATR close below the boundary, restricts extension, and tracks
trigger/expiry/invalidation. Code is not licensed for reuse and was
NOT copied. Qwct's module is an independent implementation for a
different strategy. Qwct must NOT introduce external range/Donchian
levels: only its **preselected premarket D1 Gerchik level**, immutable
during the session, is allowed.

Earlier comparison includes public Python breakout/retest volume
confirmation patterns:
https://github.com/Smashthehedgehog/break-retest-daytrader/blob/master/strategy.py
https://github.com/ascendro-ca/break-and-retest/blob/main/break_and_retest_strategy.py
Those strategies have no independently validated returns; no
Alpaca strategy, OMS, fill assumptions or unlicensed code was imported.

## What was actually implemented

**New** `strategy/breakout_retest.py` contains a per-stock,
per-session read-only M5 observer and immutable `BreakoutRetestEvidence`.
It is armed by `main.py::_prepare_session` **only** when the morning
D1 evaluator selects the `breakout` model and genuine native D1
ATR is finite. It runs on `strategy/m5_runtime.py::process_m5`,
after native LEAN TradeBar period/volume/OHLC validations and before
candidate scoring. The evidence is passed via
`strategy/data.py::MarketData.breakout_retest` and validated in
`strategy/signals.py::evaluate_gates` against exact symbol, date,
side, level and confirmation candle close time.

State sequence, one D1 scenario / stock / day:

1. `WATCH_BREAKOUT`: observe a real completed M5 crossover.
   Must have an actual previous contiguous M5 close on old side.
   One bar's wick or being already across level does not arm.
2. `WAIT_RETEST`: the breakout M5 can never count as its own
   retest. For long, later completed M5 low must be within
   `level + 0.2 * native D1 ATR` and close at/above level;
   inverted for short. At most **8 later observed M5 candles**
   may be considered; close too far on losing side (0.5 ATR)
   invalidates. Gaps, duplicates and out-of-order candles fail
   closed instead of masking missing market data.
3. `WAIT_CONFIRMATION`: exactly the NEXT completed, consecutive
   M5 candle must close through the previous retest candle's high
   for long (low for short) and have directional body. If that
   candle fails, setup becomes `INVALIDATED` (no retrospective
   confirmation from any later bar).
4. `CONFIRMED`: confirmation cannot be extended beyond the
   original Gerchik `max_entry_distance_atr=0.3` chase threshold.
   No signals use fabricated intra-M5 price updates, fill prices
   or paper orders. `BreakoutRetestEvidence.can_submit` is ALWAYS
   False. An observed completion is a *research-only* confirmation
   of the three-stage M5 proxy, NOT proven profitable Gerchik TVX.

The state is terminal after `CONFIRMED`, `EXPIRED` or
`INVALIDATED`, and reinitializes only on the next session's
native _prepare_session for each symbol. No second market-entry
attempt is inferred. Built-in `SessionPolicy`, all 8 mandatory
gates, native risk observer and no-trading source kill switch remain.

**Config:** `StrategyConfig.breakout_retest_max_bars=8`,
`breakout_retest_touch_atr=0.2`,
`breakout_retest_invalid_atr=0.5`.
Those are provisional comparator-inspired parameters and MUST NOT
be described as canonical Gerchik course thresholds.

## Important intentional divergences vs TraderWolfy

- Its trigger can be on the retest candle itself; Qwct requires
  one *separate subsequent M5* as confirmation, reducing intrabar
  chronology ambiguity.
- TraderWolfy is long/range focused; Qwct tests symmetric US-equity
  breakout up and breakdown short against D1 resistance/support.
- Qwct enforces stricter Gerchik 0.3x D1 ATR closing no-chase
  instead of importing another system's 1.5x ATR criterion.
- No automatic imports of TraderWolfy's Donchian ranges, squeeze
  indicators, risk or execution; those would overwrite Gerchik rules.
- This is NOT the BPU1/BPU2/TVX bounce model. Authentic preclose TVX
  still requires real subminute SEC/TICK observation.

## Critical known constraints

- Even a positive `m5_confirmed` does NOT grant broker approval:
  `risk_approved` stays UNKNOWN until true native risk,
  stop-protection and Schwab partial-entry behavior are verified.
- Native LEAN cloud evidence for how its consolidators actually
  deliver `TradeBar.Time/EndTime/Period` remains pending.
- Normalization of historical split-adjusted D1 ATR and native
  tick size is unresolved. No P&L or backtest was run here.
- One selected scenario per symbol, no auto-rescreen or re-entry.
  A failed 8-bar setup is terminal for the day, as a conservative
  initial implementation, **not** evidence of the optimal policy.

## Source regression coverage

`tests/test_breakout_retest_research.py`: clean long/short,
wick-only/noncross, separate stages, no same-bar retest,
eight-bar timeout and configurable windows, directional loss
invalidation, failed next-bar confirmation, 0.3 ATR no-chase,
missing/late/duplicate bar, wrong session, missing ATR, no
cross-symbol/replayed evidence and disabled execution.

`tests/test_breakout_retest_runtime_integration.py`:
actual extracted Qwct `process_m5` handler advances long/short
phase evidence exactly once on native-shaped M5 bars; invalid
zero-volume intermediate or duplicate and mislabeled M1 fail closed.

`tests/test_setup_trace.py`: existing full
`build_intent`/`evaluate_gates` regression updated; raw two-bar
breakout no longer passes `m5_confirmed`, the three distinct stages
now do, while native risk remains UNKNOWN.

`strategy/runtime_reporting.py`: research stats split between
`WAIT_RETEST`, `WAIT_CONFIRMATION`, `CONFIRMED`,
`INVALIDATED`, `EXPIRED`. They are not trades or earnings.

**Next gate:** after user explicitly authorizes separate native
Cloud validation, observe true real-feed signal-only cases and
review false-breakout, split-adjusted data and historical price
tolerances. Do NOT activate orders or merge this as a finished
trading algorithm.
