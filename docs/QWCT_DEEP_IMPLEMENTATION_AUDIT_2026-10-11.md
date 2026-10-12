# Qwct — deep source-vs-Gerchik-vs-LEAN audit (2026-10-11)

Scope: `tbsonion/Qwct`, existing draft PR #7, no order paths enabled.
This document distinguishes confirmed defects (now fixed in PR #7) from
architectural gaps or implementation assumptions that **cannot** be certified
by GitHub Python CI. No claim of trading profitability or native LEAN runtime
success. Original owner-provided reference: `docs/strategy_spec.md` and
`docs/BSU_BPU_TVX_RESEARCH_CONTRACT_2026-10-10.md`.

## Confirmed source defects and remediations

| Priority | Before fix | Failure mode | Fix / proof |
| --- | --- | --- | --- |
| P0 | `strategy/signals.py` legacy arbitrary `risk_mgr.can_open()` and `position_size()` could mark `risk_approved=True` | Custom unverified manager could pass a mandatory native broker gate, contrary to LEAN-only design | Replace with UNKNOWN for external risk managers; test permissive bogus manager still fails eight-gate approval |
| P0 | `allow_countertrend=True` returned mandatory `trend_aligned=True` unconditionally | Experiment flag bypassed canonical Gerchik trend matching | Leave experiment status UNKNOWN; test it cannot promote full approval |
| P0 | `strategy/m5_runtime.py` treated native risk read exceptions as UNKNOWN and `RESEARCH_CANDIDATE` accepted UNKNOWN | An API error could be mislabeled as usable preliminary signal | Require a fully completed partial native-risk observation before any preliminary candidate; extracted callback tests cover exception, partial UNKNOWN, hard blocker |
| P1 | `strategy/screener.py` filtered out stocks with last daily volume below 500k, before checking native 20-day SMA | False negatives even when the design's average-volume criterion was satisfied | Keep positive valid volume/dollar volume in stage 1; enforce min 20-day SMA in stage 2; deterministic regression |
| P1 | `strategy/features.py` `g09` treated no-pullback motion AWAY as a strong bounce approach; big-bar approach also lacked distance convergence | Inflated evidence for reversal setup | Require decreasing level distance and correct approach direction |
| P1 | `g09.clean_zone` picked the candidate level itself as next barrier; no barrier was assumed `True` | False evidence for empty space and wrong reported room | Search beyond selected level; UNKNOWN if next D1 level not mapped |
| P1 | `g07` rated a bar closing near its LOW as a bullish upper-level close; `g08` counted small-bar movement away from level | Wrong bullish/bearish breakout feature points | Require directional high/low close and approaching small-bar distances; regression counterexamples |
| P1 | Manually added `clock_symbol` equity used default fill-forward, though universe had `fill_forward=False` | When a manually subscribed anchor stock is also in stock universe, stale M5 observations are possible | Explicit `add_equity(..., fill_forward=False, data_normalization_mode=SPLIT_ADJUSTED)` plus static contract |
| P1 | LEAN portfolio was read without checking clock synchronization to consolidated M5 `end_time` | Late-emitted M5 could use account data from a later time | Require native algorithm `time` to match completed M5 as-of timestamp; deterministic mismatch test |

These are logic and source-contract fixes only; do not confuse them with
historical performance improvements.

## Release blockers not fixed by source-only research

### P0 — Historical price basis / corporate actions

Main currently uses `DataNormalizationMode.SPLIT_ADJUSTED` for minute
universe, manual anchor, and daily history. The Gerchik fixed absolute
thresholds (`min_price=$5`, `min_atr=$1`) and native stock tick grid
are **not invariant** under future split-adjustment. Fundamental `price`
for universe pre-selection may be in a different raw/adjusted price basis.
For example NVIDIA traded before its June 2024 10-for-1 split during
the Jan–Feb 2024 smoke window; a split-adjusted $50 level corresponds
to about $500 on that pre-split share basis. An original $0.01 price
increment can become fractional in split-adjusted historical data.
Neither the current dollar-price/ATR screen nor a half-native-tick
`BsuDetector` equality should be labeled canonical until same-date
raw/split-scaled price basis and actual tick grid are reconciled.

Official documentation:
- https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
- https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions
- https://investor.nvidia.com/news/press-release-details/2024/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2025/

Do not globally swap RAW vs SPLIT_ADJUSTED without a reviewed native
split-event/warmup regression: LEAN docs specifically warn that indicators
require reset/warmup around splits. Changing the historic price basis
would invalidate comparability to the previous Cloud smoke numbers.

### P0 — True Gerchik pattern not yet equivalent

- Swing pivot is D1 algorithmic BSU **proxy**, not independent human-reviewed
  canonical BSU. Cluster median and native source extreme differ.
- Full BPU1 exact touch / immediate BPU2 wick-and-luft logic is researched
  but only bounce setups use the native M5 BSU observer. No valid second
  TVX observer is plugged into an authenticated SEC/TICK historical feed.
- Stop distance `stop_buffer_atr*D1 ATR` and luft `20%*that distance`
  are **implementation assumptions**, not an exact course stop formula.
- `g06` M5-staircase is TODO. False-breakout research is simplified,
  complex false breakouts undefined in supplied source. Qualitative
  discretionary level strength, infection zones, distribution and
  post-false-break context are ATR/ohlc heuristics, not labeled equivalence.
- Only one best-scoring scenario is selected per stock/day, potentially
  missing other valid independent levels/models. No independently
  annotated valid/invalid examples have certified recall/precision.

### P0 — Risk and execution correctness

- Native `lean_risk_observer` collects equity, directional buying
  power, holdings, open-order presence, exchange close **only**. It
  cannot assert period-start NAV, external cashflows, native net realized
  trade history, number of losers/winners, 3-day break, pending entry
  classification, reserved risk across positions, verified protective
  stop or fill behavior; all remain UNKNOWN.
- Source-only `risk_research.py` uses explicit anchors for marked-to-market
  3% daily / 3% weekly / 10% monthly drawdown and 0.2% per trade. No
  actual LEAN end-to-end risk gate can return `True`.
- Shorts: gross notional versus LEAN buying-power is a conservative
  proxy, not proof of borrow, short sale approval or true required margin.
- 4R room and 3R target are provisional analytic intent gates, not
  proven trade opportunity or protected entry. Stop is ATR-derived.
- No stop/trailing policy, first-month exit, later 70/20/10 exits or
  Schwab partial-fill-safe protection implemented.
- EOD *entry restriction* exists; actual EOD liquidation is behind
  an explicitly false source kill-switch. No trading orders are enabled.
- No native order/event-driven closed-trade enforcement or reconciled
  durable trading journal. ObjectStore export is disabled on Free project.

### P1 — Screener, market context and observability

- Current fundamental universe is top 50 by prior-session dollar volume,
  then up to 10 D1-qualified watchlist names. The candidate cap and
  Morningstar `has_fundamental_data` filter exclude some US stocks.
  No user-approved "familiar stocks only" allowlist exists.
- D1 thresholds and score weights are heuristics rather than calibrated
  evidence. No independent ground-truth precision/recall evaluation.
- Quote-based spread check, borrow availability, earnings/news events,
  market regime, fresh quotes, true stop/target price alignment and
  slippage/fee reliability remain unverified.
- Reporting is bounded for Cloud Free logs and not a complete lossless
  decision journal across all stock/day/bar combinations.
- Existing historical Cloud LEAN observations predate all fixes in this
  deep audit; GitHub tests only certify pure Python fixtures and
  static contracts. The revised multi-symbol native Cloud pipeline
  remains UNVERIFIED.

## LEAN API evidence used in the audit

- Timebar `EndTime` / no lookahead:
  https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods
- Exchange hours and native early close:
  https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours
- Portfolio `values()`, per-direction buying power:
  https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/key-concepts
- Order retrieval native transaction manager:
  https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-management/transaction-manager
- Fundamental universe selection:
  https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes
- Time-period bar consolidators:
  https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators

## Mandatory release boundary

1. Final PR head passes GitHub compile/test CI and Python files stay under
   Cloud 32,000-character editor limit.
2. Confirm NO code path ever submits orders or creates fake broker/portfolio.
3. Before claiming native LEAN success: isolated NO-ORDERS Cloud smoke on
   changed modules and representative sessions, including corporate actions,
   strict M5 timestamps and native portfolio reads.
4. Historical SEC/TICK observation must be verified on a real subscription.
   Never synthesize a :30-preclose TVX from M5 data.
5. Resolve tick/price basis, true Gerchik annotated patterns and native
   portfolio ledger before any merger presented as "full strategy complete".
6. Keep PR #7 DRAFT; do not enable paper, live, Schwab order execution.
