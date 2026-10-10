# QuantConnect public-code comparison vs Qwct — 2026-10-10

Research-only audit. No strategy code changes, trades, cloud tests, or merge.

## Concrete inspected implementations

1. QuantConnect/Lean official Apache-2.0 Python per-symbol example:
   https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/MultipleSymbolConsolidationAlgorithm.py
   Uses independent SymbolData, indicator readiness, RollingWindow and
   was_just_updated checks on the latest completed symbol bar.
2. Official native Fundamental selection:
   https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/FundamentalUniverseSelectionAlgorithm.py
   Selects through Fundamentals, keeps changes separate from signal events.
3. Official typed/history demonstration:
   https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/HistoryAlgorithm.py
   Distinguishes daily vs minute history when priming indicators.
4. Official consolidator removal:
   https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/ManuallyRemovedConsolidatorsAlgorithm.py
   Shows native subscription-manager cleanup for dynamic symbols.
5. Official chronological consolidator-window test:
   https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/ConsolidatorRollingWindowRegressionAlgorithm.py
6. Staff QuantConnect research with executable C# model:
   https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/p1
   Implements fundamental-universe selection, first-five-minute
   relative volume vs past 14 same-session samples, an opening
   range/trigger distinction, risk-based sizing and native
   CalculateOrderQuantity cap. ORB is NOT Gerchik. In its discussion,
   a Python adaptation was found to update ATR using minute rather
   than daily data, leading to large discrepancies. That is a
   caution about timeframe mixing, not proof of the same Qwct bug.
7. QC community reversal/level clustering source:
   https://www.quantconnect.com/forum/discussion/12132/how-do-i-identify-relevant-support-and-resitance-level/
   Uses separately identified support vs resistance swing clusters.
8. QC community intraday example:
   https://www.quantconnect.com/forum/discussion/799/strategy-opening-range-breakout/p1
   Demonstrates session scheduling and historical indicator warmup,
   but execution code and stop behavior must NOT be transplanted.
9. Gerchik concrete M5 example:
   https://gerchik.com/journal/instrukczii/provoi-urovnya-i-otvoi-vtb/
   Requires repeated approach and at least 2 M5 consolidation
   bars for its particular setup (not a universal Gerchik requirement).

## High confidence Qwct missing or misleading logic

**P0-A: no M5 breakout event.** strategy/signals.py, _check_m5:
a breakout passes merely when the last M5 close is ABOVE a level for
long (or below for short). Two consecutive completed M5 bars above
resistance may be tagged a new breakout on the second despite no
fresh cross or impulse. Missing previous-side/cross provenance.
The ORB example distinguishes an established range and crossing.

**P0-B: inadequate M5 bounce evidence.** _check_m5:
one M5 high/low straddle and closing back on one side is sufficient
without validating prior approach, rejection/structure, or BPU.
Gerchik's published illustrative setup required multiple M5 bars.
A specific owner-authorized model definition is needed; copying
ORB confirmation rules verbatim would be a different strategy.

**P0-C: false mirror labels.** strategy/levels.py, _mark_mirror:
two candle ranges containing a level mark it as mirror even if no
support->resistance or resistance->support role reversal happened.
A price-range overlap is not proof of historical role reversal.

**P0-D: risk_approved is not approval.** strategy/signals.py,
evaluate_gates and main.py pass risk_mgr=None. A provisional
stop-size/cash check can mark this gate true with zero enforcement
of max portfolio positions, trade/day, losses/day, weekly/monthly
limits or native buying power. Official QC ORB also uses native
CalculateOrderQuantity for concentration caps. Signals remain
research-only; do not enable orders.

**P0-E: actual BSU/BPU2 detector unused.** Corrected
strategy/patterns_bsu.py is an isolated pure model; current LEAN
main.py does not call it or capture native BSU timestamp,
tick-size provenance, or second/tick preclose evidence.

**P1-F: top dollar-volume ranking is not stocks in play.**
Qwct selects 50 liquid assets then picks first 10 of those passing
price, daily ATR and 20-day daily volume. The ORB paper uses a
different first-five-minute relative-volume ranking, unknown at
the 09:29 Qwct screen time. It could be an OPTIONAL second-stage
research screen, not an automatic modification to Gerchik.

**P1-G: no-chase & spread settings are unused.**
max_entry_distance_atr and max_spread_bps are configured but
unused by main M5 signal decision. Breakout limit equals last
M5 close; this is not proof of a realistic tick-aligned executable
entry. Native EquityFillModel distinguishes quote and trade prices.

**P1-H: native daily history and consolidation parity unproven.**
Qwct DOES correctly keep a native ATR/SMA/volume per symbol and
updates those only with a completed D1 TradeBar; do not claim it
has the same minute-ATR bug as the community ORB version. However,
there is no bar-for-bar native history vs D1 consolidator oracle
fixture, especially for split adjustment and symbol re-entry.

**P1-I: no replayable complete decision journal.**
Qwct has internal counters but ObjectStore writing was denied on
the Free organization. These summaries don't establish which
timestamped D1 level, model, M5 candle, gate and rejection drove
each decision. Need auditable records via a supported method.

**P1-J: repeated calculation vs native RollingWindow.**
Qwct repeatedly rebuilds pandas frames and recalculates fixed
D1 session levels during M5 checks. The official per-symbol
RollingWindow example is an efficiency and provenance reference;
an optimized version must preserve the original as-of semantics.

## Additional source-only gap: two nominal mandatory gates are tautologies

**P0-K: stop_behind_d1_level and target_at_least_3r do not
independently validate trade geometry.**
In strategy/signals.py evaluate_gates, the stop is always generated
as level minus directional positive native-ATR buffer. Its
stop_behind_d1_level gate then merely tests that the generated
stop is behind that same level. With positive ATR, this is a
constructed tautology, not independent proof that the stop is on
the LOSS side of the actual entry. The target_at_least_3r gate
simply tests fixed config.tp_r >= config.min_rr, both 3.0 by
default, and does not check an actual achievable target price.
The separate room_at_least_4r gate tries to enforce a known
next-level distance, but does not prove stop direction, quote
spreads, tick alignment, or execution viability. This is
material because user-facing text calls all eight gates passed
an "ideal trade". Require explicit side-relative
(entry,stop,target) geometry and cost-aware feasibility evidence
before upgrading the signal classification; keep all orders off.

## Existing correct Qwct choices to preserve

- native per-symbol ATR(14)/SMA(50)/SMA(volume,20);
- synchronous Universe settings (rank state mutation);
- typed TradeBars inner items iteration;
- split-adjusted D1 history & subscriptions;
- fill_forward=False for universe minute candles;
- native exchange-aware scheduling;
- native consolidator cleanup; and
- ALL ORDERS DISABLED with no fake OMS, fill or P&L.

## Evidence boundary and next action

The source comparisons are real code, not hypothetical functionality.
The classification defects are demonstrable by reading existing
conditions. They have NOT been reproduced with Qwct unit fixtures or
with LEAN for this audit. Do not claim a certified or profitable Gerchik
algorithm, and do not ask the user to retest while these known source
gaps remain. Write targeted red-first fixtures before rewriting any
strategy decision rule. No executable files changed here.
