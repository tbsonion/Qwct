# Focus / BPU1 / M5 gate investigation — 2026-10-11

Status: research only; PR #6 remains draft, not merged. Orders remain
hard-disabled in `main.py`. No market data invented, no thresholds relaxed.

## Observed from actual user Cloud LEAN run (not a test fixture)

- 2024-01-01 to 2024-02-05, LEAN 2.5.0.0.18178,
  1,241,044 processed market points.
- 10 screened stocks/day; 6 accepted D1 setups:
  NVDA 2024-01-02 bounce/short, 5 false breakout setups.
- NVDA morning resistance **cluster=50.2660, original swing=50.2660**,
  swing source 2023-08-24. Actual level in SPLIT_ADJUSTED price space.
- 76 native completed M5 evaluated for this scenario,
  no BPU1 exact native-tick-level touch detected, no BPU2.
- 456 total evaluated M5 gates, 450 `m5_confirmed=False`,
  **at most 6 true M5 two-bar passes**. Without individual positive
  event snapshots cannot assign the six passes to tickers or timestamps.
- Risk gate UNKNOWN for all 456 (correct: no native broker approval).
  Trend misalignment on 228 and missing 4R room on 228 observations.
- `Qwct Focus` chart froze to TSLA because it was first in initial
  liquidity watchlist, not because TSLA had a valid D1 scenario.
- The user-provided log contained only the final **two** NVDA M5
  candles. This is NOT enough to reconstruct the full series of 76
  highs. Do not make up an historical nearest high or claim BPU1 bug.

## Verified source/documentation

Official QuantConnect charting:
https://www.quantconnect.com/docs/v2/writing-algorithms/charting

Official LEAN USA equities normalization:
https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data

Official LEAN US equity data preparation:
https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/data-preparation

- SPLIT_ADJUSTED means the entire split history transforms historical
  prices. The current native security tick size and the historical
  split-adjusted bar-price lattice are NOT automatically proven
  identical. Consequently this audit REPORTS both source pivot
  and LEAN `symbol_properties.minimum_price_variation`, but does
  **not** adjust the BSU pattern touch threshold or certify canonical
  tick-precision without independently verified normalization evidence.
- LEAN native consolidated completed TradeBar bars are used for
  OHLC. No history is requested from inside the M5 callback.
- Free chart quota is 10 series; `Qwct Focus` has 4,
  `Qwct Research` has 5; one fixed ticker per run.

## Implemented fixes in this PR

1. `strategy/focus.py::choose_focus` selects the first accepted D1
   **bounce** in the first session with setups; if no bounce that day,
   the first accepted other model. Optional `focus_symbol` parameter
   selects a requested ticker if it has an accepted D1 setup.
   The focus never switches once selected, preventing mixed price axes.
   For the known historical Jan 2 case the focus is NVDA, not TSLA.
   The frozen accepted D1 level is overlaid on NVDA M5 candles.
2. `strategy/research_trace.py::BpuTouchAudit` observes every ALREADY
   CONSOLIDATED real M5 bar in the bounce session. Short/resistance
   uses **M5 HIGH**, long/support uses **M5 LOW**. Report contains
   bar count, native reference tick/tolerance, nearest M5 extreme,
   signed gap to the actual BSU *swing pivot* (not level median),
   timestamp, count of exact touches vs undershoots/overshoots,
   and session maximum high/minimum low. This is a descriptive
   audit, not a new BPU1 decision/approval.
3. `strategy/m5_runtime.py` preserves the existing
   `BsuDetector.on_bar` and all risk gates. Its same native TradeBar
   drives BPU touch audit. If absent BPU1, report will now say how
   close price got and whether it overshot the exact level.
4. M5 gate `_check_m5` source was inspected. It is a
   **minimal two-bar proxy**, not canonical Gerchik BSU/BPU/TVX.
   The reported 450/456 failures alone are NOT an implementation
   defect: a one-bar false breakout/bounce pattern can appear for
   1/76 bars, then disappear. Synthetic verified tests exercise
   short false breakout, bounce two-bar test, and BPU exact-tick
   mismatch. Tests do NOT substitute for historical NVDA evidence.
5. Positive M5 gate events are now captured explicitly via
   `SetupTrace.m5_passes`, timestamp of first pass, and its entire
   8-gate status snapshot. Runtime summary reports pass counts
   grouped by model and which OTHER gates blocked those passes.
   `risk_approved=None` stays fail-closed.
6. Default backtest window remains short Jan 1–Feb 5 2024;
   main.py must stay <32,000 characters. Cloud Free log-budget
   protection remains in place.

## Release gating and single-run native LEAN checklist

Source tests, synthetic runtime callback tests, compilation and 32k
limit check are distinct from actual LEAN Cloud. GitHub CI results
must be verified for the latest commit; do not claim native historical
results have changed until user's ONE new backtest.

Copy from the current PR #6 feature branch, preserving folders:
`main.py`, `strategy/focus.py` (NEW),
`strategy/research_trace.py`, `strategy/m5_runtime.py`,
`strategy/runtime_reporting.py`.
Previously updated `strategy/bsu_bridge.py` and `strategy/levels.py`
do not change in this focused task.

Check these outputs in that one backtest:

- `Qwct Focus locked to accepted D1 setup: NVDA bounce/short...`
  and actual native NVDA candles plus $50.2660 frozen D1 level.
- `QWCT TOUCH NVDA 2024-01-02` including `n=76`, closest
  M5 HIGH and signed gap; do not call undershoot an exact touch.
- `QWCT M5 PASS` line and `Qwct M5 two-bar passes` statistic:
  identify when/how the rare gate passes happened, then why the other
  independent gates prevented research candidates.
- No `ERROR`, no `Orders`, flat simulated portfolio required.
- Native hist adjustments may still require price-normalization
  sensitivity research before canonical BPU1 tick-rule approval.

Not implemented: native SEC/TICK 30-second-before-BPU2 TVX, native
portfolio risk approval, fills/orders, discretionary Gerchik
ground-truth labels, profitability or live brokerage integration.
