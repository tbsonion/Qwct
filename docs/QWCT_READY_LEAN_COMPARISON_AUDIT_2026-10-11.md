# Qwct source audit against published and official native LEAN solutions

Date: 2026-10-11. Scope: `tbsonion/Qwct` open DRAFT PR #7 only.
This is a **source-level code audit and pure Python CI**, NOT a new
QuantConnect native backtest, third-party profitability replication,
paper/live trading authorization, or a complete Gerchik strategy.

## Independent ready implementation and official platform patterns

1. QuantConnect / Derek Melchin's published US-equity Opening Range
   Breakout for Stocks in Play (December 2024):
   https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/
   This is an independent ORB design, not Qwct's Gerchik strategy. It
   emphasizes 09:35 as-of current activity vs 14 *same-clock-time*
   historical observations, native ATR, diversified position caps,
   day-end exits, stop handling and run-to-run reproducibility.
   Community Python / C# replications expose serious indicator
   frequency and fill-timing divergence. Reported Sharpe is
   **backtested on particular samples; no proven transferable edge**.
2. QuantConnect official indicator-universe examples:
   https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/indicator-universes
   The examples rebuild indicators when splits/dividends occur and use
   SCALED_RAW history for correct adjusted basis. Qwct's fixed $1
   D1 ATR, $5 price and native tick/volume assumptions on SPLIT_ADJUSTED
   history still need independently verified native reconciliation.
3. QuantConnect native consolidators:
   https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
   and actual bar period semantics:
   https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods
   Bar EndTime is completed-bar information; no future bar or software
   backfill can validate BPU2 at 30s before M5 close.
4. QuantConnect official manual indicator updates for dynamic universes:
   https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/updating-indicators
   Qwct currently updates manual ATR/SMA *only from completed D1
   TradeBars*, which is directionally correct relative to a published
   faulty ORB Python port that accidentally fed minute-resolution
   bars to daily ATR. Native runtime confirmation is outstanding.

## Confirmed defects independently found and FIXED in this audit

**A. Mirror chronology; `strategy/levels.py::_mark_mirror`.**
Before: allowed two D1 bars just after the origin pivot, but
BEFORE the right-hand k-bar swing confirmation, to retrospectively
turn the level into a mirror; retained original `valid_from` even
after the mirror confirmation retest. This misstated when a mirrored
support/resistance is knowable. After: for native levels with
`valid_from`, a breach/retest can occur ONLY after the original
swing level has been confirmed. A mirror becomes valid on the
following day after its actual retest close; date metadata is
updated. Independent deterministic regressions cover support,
resistance and before/after confirmation:
`tests/test_signal_safety_regressions.py`.
This does not infer undocumented intraday mirror fills.

**B. Opposite-direction retest gap; `strategy/features.py::g03_near_retest`.**
Before: any large absolute open-vs-prior-close gap counted as a
`gap_retest` positive for a D1 level, even if price opened
**further away** from that level. This could add the weighted
g03 bonus to a breakout scenario without actual approach.
After: the overnight move must be >=0.5x already native D1 ATR
AND the opening price must be CLOSER to the selected level than
the real prior D1 close. Both real gap-toward and counterexample
gap-away regression tests reside in `tests/test_strategy_contract.py`.
This is a conservative causality clarification, not a claim that
the numeric gap threshold has been calibrated against original
manual course examples.

## Confirmed sound decisions (subject to native Cloud revalidation)

- Native/manual daily ATR(14), SMA(50), SMA daily share volume(20) are
  only fed historical/completed **daily** LEAN TradeBars; no own
  ATR or synthetic prices, and no minute bars directly into D1 ATR.
- M5 native callback rejects bad or untraded/fill-forward-tagged bars
  and duplicates/out-of-order timestamps BEFORE detecting BSU/BPU
  or provisional two-bar research candidates.
- Existing `TradeIntent.all_gates_passed` requires all eight known
  True gates; mandatory native `risk_approved` remains unknown.
  The native risk snapshot lacks proof of complete trade/portfolio
  ledger; this is an intentional fail-closed limitation.
- No native execution enabled. No invented stop protection,
  OMS, shadow portfolio, win rate or expected profitability.

## Priority findings NOT solved by comparing published backtests

| Priority | Difference / threat | Why not just copy another strategy? |
|---|---|---|
| P0 | Historical US equity corporate-action price basis, volume & native $0.01 tick mismatch | RAW/SPLIT_ADJUSTED/SCALED_RAW need actual as-of LEAN verification and coherent indicators; wrong fix can create more signals or false stop distances |
| P0 | Real LEAN Cloud runtime, typed History, end timestamps & partial Portfolio adapter API not run on latest branch | Python mocked source tests cannot validate .NET calls; native signal-only cloud run must be separately approved |
| P0 | Broker-native fills, fees, slippage, partial-stop protection, short borrow availability, EOD flatten | Qwct deliberately prohibits all orders; no credible profitable backtest or live execution until these exist |
| P0 | No true 30s-preclose SEC/TICK, no labeled human Gerchik BSU examples | ORB 09:35 candle is not the original BPU2 / TVX strategy; no substitution |
| P1 | 50-fundamental-candidate then 10-watchlist cap may discard today's active stocks | ORB 1000/20 universe is much wider; increasing to 1000 without data budget/native rerun is unsupported |
| P1 | Optional 14-session 09:35 relative volume not wired into ranked signals | 09:29 premarket decision must not use 09:35 data; read-only comparator exists, separate stage needs proven native history and corporate-action share basis |
| P1 | User's full Gerchik D1 sources & M5 staircase incomplete, false-breakout heuristics not annotated | Paper ORB’s simple breakout is a different strategy, not evidence the missing discretionary rules are solved |
| P1 | Original 3R target and later conditional 70/20/10 exit model not broker implemented | Risk sizing based on stop distance is not verified stop/target execution |
| P1 | No robust multi-year out-of-sample, turnover, survivorship/fees/regime comparison | Published historical Sharpe cannot be reused as Qwct performance |
| P1 | Price/volume/liquidity features exist, but no verified quote spread, earnings/news, index/regime as-of feed | Blindly inserting non-native or future data creates lookahead and costs bias |

## Minimal scope release checklist

- Existing draft PR #7 only. No merge into main until permission.
- CI green on EXACT head; Python file editor limit (<32000
  bytes) checked by repository CI.
- Every new signal-change is backed by a negative counterexample and
  a positive case where possible.
- D1 as-of level dates, 09:29 freeze, M5 09:35 or later time, no
  non-native price generation, no fake portfolio/partial fills.
- Actual LEAN Cloud signal-only regression must precede claims of
  native runtime success; run scoped split/baseline checks first.
- **No equity curve, Sharpe or order-execution claims from this audit.**
