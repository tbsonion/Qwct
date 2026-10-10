# Qwct — signal safety fixes after public QuantConnect code audit
Date: 2026-10-10

This is SOURCE-LEVEL RESEARCH, not a certified Gerchik strategy or
a real QuantConnect LEAN backtest. Branch is intentionally unmerged,
draft PR #5. No brokerage orders enabled.

## Evidence: failing old tests and passing fixed tests

Red-first deterministic tests were written against the prior branch
implementation, before changing strategy files. CI showed **9 failed /
69 passed**: false M5 breakout continuations, unsupported one-candle
bounce, missing M5 continuity, false mirror classification,
risk-approved without a native risk manager, an invalid long stop,
and a nonsensical negative-price short 3R target.

The initial corrections in strategy/signals.py and strategy/levels.py
then passed all old and new tests (green CI commit 8450aabb).
Separate red-first tests covered empty/incomplete gate dicts and
entry >0.3x native ATR away from the D1 level; the fixed code passed.

## Precise changes

- M5 breakout: requires **two actual contiguous CLOSED M5 bars** and a
  prior close on the origin side followed by a close beyond the
  level. Merely remaining above or below the level is not classified
  as a NEW breakout.
- M5 bounce: requires two contiguous closed bars, the prior close
  on the original/return side, and a later level touch plus close
  on the return side. **This is a conservative partial approximation**.
  It does not claim BSU/BPU1/BPU2/TVX fidelity.
- Simple M5 false-breakout: tests preceding-side close and an actual
  level piercing/return; cannot infer missing intermediate bars.
- M5 prices: reject non-finite/ill-formed OHLC, naive timestamps,
  out-of-order and noncontiguous 5-minute sample gaps; no
  fabricated market calendar or homemade feeds.
- Mirror D1: require a **separate later CLOSE beyond original level**
  and then a distinct reversal retest of the former
  support/resistance. Candle wick overlaps alone no longer count.
  All comparisons remain on previously closed D1 data.
- Stop gate: checks loss-side entry-to-stop geometry as well as the
  source D1 level; a generated stop beyond a level is not an
  independent check that a delayed entry has a valid stop.
- Target 3R gate: validates the derived target's real positivity,
  finiteness, direction, risk-per-share and configured R multiple,
  rather than accepting the tautology 3>=3.
- Research risk gate: without actual risk manager, buying-power,
  portfolio exposures, daily/weekly/monthly limits and Schwab
  protection proof, `risk_approved` returns **UNKNOWN**, never
  TRUE. Shares remain explicitly preliminary.
- All 8 gates must be present with an explicit TRUE; an empty
  dictionary no longer satisfies `all_gates_passed`.
- No chase: distance of actual last M5 close from the D1 level must
  be <= `max_entry_distance_atr * native_daily_ATR` (0.3 ATR
  by default) or M5 confirmation fails.
- `main.py`: when all other 7 gates passed and the trade window
  and preliminary cash-fit check pass, the setup is recorded as
  `RESEARCH_CANDIDATE` with explicit NO ORDERS / native risk
  NOT APPROVED. It is **never** an approved `INTENT`.
  Separate LEAN runtime statistics and chart lines distinguish
  research candidates from approved intents. Same one-session
  daily single-candidate behavior is preserved.

## Deliberate limitations (do not misrepresent)

1. The standalone BSU/BPU/TVX detector is **not wired** into
   `main.py` because actual source BSU-bar attribution,
   security tick-size and a 30-second-before-BPU2-close
   native feed are not yet proved. The simplified M5 checks
   are NOT equivalent to complete Gerchik pattern validation.
2. No runtime risk manager is present. The signal-only algorithm
   therefore emits **zero risk-approved intents** by design.
   It can record research candidates but they are not executable
   trades, fills or profitability samples.
3. Real split-adjusted D1 indicator agreement vs chart,
   exchange closed-bar timing, native buying power, spread/queue
   and 30-second TVX, broker stops, cancellation and position
   lifecycle require separate LEAN/Schwab tests and are not
   demonstrated by synthetic unit fixtures.
4. The unchanged strategy retains an isolated scenario evaluator
   with heuristic D1 feature weights. No performance claims.
5. No Cloud LEAN execution has been run from these exact changes,
   and the user was not asked to run one. Do not merge or
   enable orders until separate approval and verification.

## Sources cross-checked

- https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
- https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/MultipleSymbolConsolidationAlgorithm.py
- https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/ConsolidatorRollingWindowRegressionAlgorithm.py
- https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/p1
- docs/QUANTCONNECT_COMMUNITY_CODE_COMPARISON_2026-10-10.md
