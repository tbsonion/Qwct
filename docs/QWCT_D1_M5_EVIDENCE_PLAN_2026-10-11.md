# Qwct: evidence-first implementation and LEAN acceptance contract

Date: 2026-10-11. Branch `fix/qwct-research-chart-diagnostics-20261010`,
draft PR #6. **Research-only / ALL ORDERS DISABLED**.

## Why the earlier process failed

A green compile/pytest result answers only "did the pure code handle the
fixtures we wrote?" The QuantConnect run with 6 accepted D1 scenarios,
456 M5 checks, and no reported BSU or research candidates exposed a
critical evidence gap: the original runtime data were not preserved in
a trace that tied the exact D1 decision to the M5 gate rejections.

The run does NOT establish whether valid trades were missed. In particular:
- only a bounce model is eligible for the current BSU/BPU observer;
- other models cannot be counted as missing BSU patterns;
- all eight gates include an intentionally UNKNOWN native risk gate;
- bounce research candidates are deliberately blocked from claiming TVX
  because M5 bars cannot observe 30 seconds before BPU2 closes.

The previous logs and screenshot cannot reconstruct all six setups
independently, and cannot prove the strategy is correct or profitable.

## Concrete code changes in this branch

### Per-accepted-D1 bounded evidence ledger

`strategy/research_trace.py` is pure Python with NO LEAN dependency.
`SetupTrace` captures one accepted scenario's:
- symbol, session, 09:29 decision timestamp, D1 model and direction;
- exact selected level price, strength score, count of frozen D1 levels;
- D1 native ATR and close as-of decision;
- features that contributed to the winning D1 model;
- original level kind/source, swing formation/valid_from dates and
  first/last source swing indices;
- eligibility/provenance of the independent swing-proxy BSU observer;
  distinguishes source swing pivot from cluster-median level;
- first/last actual M5 gate timestamps and number of evaluated M5 bars;
- TRUE / FALSE / UNKNOWN gate state, last gate reasons and bounded
  failure totals for each named gate;
- the last two **native already-seen consolidated M5 OHLCV** observations
  with their native timestamps; rejects fabricated/future observations;
  Cloud logs show their real OHLC values in a separate short M5 line;
- BPU1/BPU2 observation counts and exact native BPU invalidation reasons;
- preliminary research-candidate yes/no, never broker authorization.

On the LEAN side `main.py` constructs this only when a D1 decision is
accepted; attaches the same per-symbol trace to the existing actual M5
callback, and retains the first 30 accepted setups across universe
subscription removals. End-of-run logging emits up to 20 setups,
with FOUR separate <=190-character lines for each (D1 source, M5
native OHLC, gate rejection and BSU/BPU evidence). This prevents the
Cloud log viewer from truncating the most useful field off a long
single-line report. An explicit omitted count appears if limits apply.
It never fetches history during M5 decisions or synthesizes candles.

No trading rules were relaxed, no bracket/broker orders added, and no
paper trading, fake fills or return calculations introduced.

### No more missing BPU rejection cause

Before this branch, `BsuDetector` reset after BPU2 invalidation;
its specific wick/luft reason could be overwritten. The native callback
now counts these invalidations before reset and attaches them to the
selected setup's trace. Invalidations are not successful TVX signals.

### Existing PR #6 source fixes retained

- LEAN `Qwct Focus` one-stock M5 candlestick chart, D1 level overlay,
  BSU-proxy BPU1/BPU2 research markers; unchanged equity must remain flat.
- Original native swing pivot and median D1 swing-cluster level kept as
  **different** prices, with same historical ready-ATR median tolerance.
- Separate accepted D1 model counts and named BSU rejection counts.
- Per-symbol native M5 charts bounded by LEAN Free series/point quota.

## Deterministic validation, and evidence grades

1. **Rule tests**: tests/test_setup_trace.py supplies positive and
   rejection examples, verifies tri-state gate accounting, native OHLCV
   ordering, score/origin provenance, and bounded lossless summaries.
2. **Integration-level pure tests**: same test file feeds actual
   `build_intent/evaluate_gates` output into `SetupTrace`, verifying
   that risk approval remains UNKNOWN even with an M5 level crossing.
3. **Entrypoint contract tests**: tests/test_multisymbol_eod_reporting.py
   checks `main.py` uses the actual received native M5 bar buffer
   and maintains hard-disabled execution.
4. **GitHub CI**: compiles all Python and runs deterministic tests
   without QuantConnect data subscriptions. **This cannot establish
   native LEAN chart render correctness**. Record actual final CI
   URL/count after it finishes.
5. **QuantConnect native integration**: not available to the GitHub
   connector; cannot be marked successful without a separate real
   LEAN run. The previous user-run backtest predates these changes.

## Single-run acceptance plan (do not ask for repetitive blind tests)

After the user approves testing the branch in QuantConnect, copy the
branch's Python files, preserve the prior one-month Jan 1–Feb 5 2024
window, then run ONE native Cloud LEAN backtest. Explicit checks:

1. No initialization/runtime errors; native D1 history and M5
   consolidate; ALL ORDERS DISABLED, no filled orders/positions.
2. Select **Qwct Focus**: native M5 candles appear for the fixed
   `Qwct chart focus` ticker (rather than flat Strategy Equity).
3. **Qwct Research**: screener/D1 scenario/candidate counters plot.
4. End stats agree with bounded `QWCT TRACE` lines: model mix,
   per-level provenance, first/last M5 time, and failure counts.
5. For every accepted D1 scenario in the short run, verify its real
   last-two M5 OHLCV and last gate outcomes agree with native
   candlestick data; no lookahead, reused D1 frozen levels.
6. If zero BPU2 observations remain, distinguish:
   **no accepted bounce** vs **BSU-origin blocked** vs
   **no native BPU1** vs **BPU2 invalidated**, with exact reason.
7. A nonzero trade/candidate count is NOT an acceptance criterion.
   Rejecting invalid setups is correct behavior. Native risk still
   UNKNOWN and TVX-30-second feed still absent.

If the run passes all technical items, classify the research pipeline
as *observationally integrated for that historical window only*.
Do NOT classify it as a complete/canonical Gerchik system.
A curated independently labeled historical D1/BSU/BPU example and
separate native second/tick access validation are still required.

## Invariant: no trade execution

Keep the compile-level kill switch
`self._native_exit_enabled = False`, and no native order methods
`self.market_order`, `self.limit_order`, or custom broker adapters.
Signals, annotated OHLC charts and research-only traces are not
trade placements or broker fill simulations. Draft PR #6 stays
unmerged until user instructs otherwise.
