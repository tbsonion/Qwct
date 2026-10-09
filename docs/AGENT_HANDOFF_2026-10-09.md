# HANDOFF — Qwct (2026-10-09)

## READ THIS FIRST — user intent and non-negotiable constraints

The owner rejected repeated attempts to build a bespoke order management system
in `tbsonion/QuantConnectTest`. The old `OrderManager` accumulated ~1,900
lines, custom order states, cancel/resize/reconcile races, repeated fixes and
misleading mock-only green tests. Even the later `NativeBracketGateway` was
another home-grown wrapper and was removed. **Do not reproduce those mistakes.**

The owner explicitly selected a NEW repository:
https://github.com/tbsonion/Qwct

**Build the original Gerchik Levels strategy on the official QuantConnect
LEAN Python infrastructure.** Reuse LEAN market data, indicator engines,
exchange calendar, native order tickets/events, buying-power and liquidation.
Maintain only genuinely strategy-specific rules. Do not claim a codebase is
production-safe because synthetic unit tests pass.

**STRICTLY NO:** `OrderManager`, `BrokerAdapter`, `NativeGateway`, software
OCO/OTO/bracket/OUO, mirrored order/position ledger, handmade NYSE calendar,
fake broker, custom ATR/SMA calculator, unauthorized brokerage connection,
credentials, paper/live orders, merges or strategy-profit backtests. Work in
feature branches; keep main stable. This task is an implementation/refactoring
phase, not a performance evaluation.

## Current verified state

- Repo: `tbsonion/Qwct`, default branch `main`. Main only received initial
  README. **Actual implementation is on branch
  `feat/lean-native-gerchik-foundation-20261009`**.
- Last reviewed commit before this handoff: `20d91654aa2ea20996d204f98cf614b86bc1b26b`.
- GitHub Actions "Pure Strategy Checks" passed at that commit; **8/8
  pure Python tests passed** in an earlier run.
- No LEAN engine execution, no QuantConnect runtime API validation, no Schwab
  compatibility test, no backtest, no paper/live order, no broker connection.
- Ported from old `tbsonion/QuantConnectTest` branch
  `fix/native-lean-orders-no-custom-oms-20261009`, commit
  `20101293ca797344de4399227ddd97ad3c49e1f8`.
- Old QuantConnectTest PR #5 was repeatedly patched; old draft PR #7 isolated
  its execution path but still does not represent validated brokerage code.
  **Do not merge it into Qwct.**

## Qwct architecture — what was actually copied

- `main.py`: ONE `QCAlgorithm` entrypoint, research/signal-only. Calls
  LEAN `add_equity`, native `history[TradeBar]`, daily/M5 `consolidate`,
  `schedule.on`, `AverageTrueRange`, `SimpleMovingAverage`, and reads
  `portfolio.total_portfolio_value`. No submission methods.
- `strategy/config.py`: user configuration ($25,000 baseline, 0.2% /
  $50 per trade; D1/M5; 3R first target; future 70/20/10).
- `strategy/levels.py`: original Gerchik D1 price levels, touch strength,
  mirror levels, valid-from/no-lookahead semantics.
- `strategy/features.py`: all 14 original feature groups g01...g14 and
  their subconditions, retaining true/false/unavailable with provenance.
- `strategy/scenarios.py`: three original models (bounce, breakout,
  simple false breakout); no AI-trading decision substitution.
- `strategy/signals.py`: original 8 mandatory gates, including actual
  completed M5 confirmation, >=4R room and >=3R TP.
- `strategy/sessions.py`: **strategy-specific entry windows** from Gerchik.
  This is NOT an exchange calendar; retain this business rule.
- `strategy/patterns_bsu.py`: original BSU/BPU1/BPU2/TVX detector.
  It was preserved but **is not connected to entry activation** in main.py.
- `strategy/indicators.py`: only reads `atr14` and `sma50` snapshots
  emitted by native LEAN; does not calculate indicators in pandas.
- `strategy/data.py`: narrow completed-bar/as-of DataFrame view of LEAN
  data; not a data-provider, exchange calendar or simulator.
- `docs/strategy_spec.md`: original source specification, authoritative
  for Gerchik business behavior (subject to owner's newer instructions).
- `tests/test_strategy_contract.py`: 8 pure unit checks. No Lean or Schwab.

Not copied: old `orders.py`, old `risk.py` virtual ledger,
`lean/engine.py` custom execution engine, `calendar.py`,
`events.py`, `journal.py` duplicate fill ledger, mock broker,
CSV/synthetic feed, and half-implemented ORB/hybrid.

## Important known technical gaps — **do not conceal or mark green**

### P0 — first: prove it runs in real supported LEAN Python
1. Check supported QuantConnect Python naming/signatures (e.g.
   `set_time_zone`, typed `self.history[TradeBar]`,
   `self.consolidate(..., timedelta(minutes=5), ...)`,
   `AverageTrueRange.update(bar)`, `SimpleMovingAverage.update`,
   native schedule callbacks) against the actual current LEAN version.
   Existing CI only compiles `main.py` and does NOT import
   `AlgorithmImports`; runtime API compatibility is UNVERIFIED.
2. Verify `TradeBar.time` and `end_time` indexing in ET for daily
   history and consolidators. Guard against inserting a still-forming
   current D1 candle, duplicate daily bars, future leakage and timezone
   mistakes. Do not assume pandas and LEAN bar timestamps are identical.
3. Verify native ATR(14) Wilder and SMA(50) warmup: `_append_daily`
   seeds 180 D1 candles and daily consolidation updates afterward.
   Match native values and ensure enough history for the lookback windows.
4. Verify LEAN's NYSE early closes and scheduled pre-open/pre-close.
   No custom holiday calculator may be added. Avoid trading after a
   13:00 half-day market close.
5. Use the *official* LEAN CLI/project convention where available;
   test imports/dependency packaging in a real LEAN algorithm context.
   Local mock/pytest tests alone are NOT acceptance.

Acceptance: actual LEAN runtime loads `QwctGerchikAlgorithm`, consumes
daily and closed M5 bars, logs signal/no-signal decisions without exceptions,
and **submits zero orders**. Do not run strategy-performance backtests without
the owner's separate approval.

### P1 — make the original strategy functional without changing its rules
6. Validate all original g01-g14 feature subconditions against the source
   specification. Avoid fake feature availability. Audit empty/nan histories.
7. Validate D1 level freeze **before** session and as-of swing confirmation,
   plus an M5 signal from *closed* M5 bars only.
8. Retain all 8 mandatory gates. Risk gate is currently only a PRELIMINARY
   estimate; proper account checks are not wired.
9. Wire `BSU/BPU1/BPU2/TVX` into model confirmation ONLY if required by
   the original spec and backed by available time resolution; M1 only
   approximates 30-second timing. Do not claim exact tick-based timing.
10. Keep entry sessions per model (separate from LEAN exchange hours).
11. Confirm support for multiple symbols only after the one-symbol
    algorithm works: main.py currently takes one `symbol` parameter.
12. `orb` and `hybrid` modes were not migrated; their historical code
    was on a separate unmerged PR #1 in the old repo. Do not falsely
    advertise them as implemented.

Acceptance: deterministic rule tests cover the 14 groups, eight gates,
3 models, as-of data and time windows. No brokerage logic added.

### P2 — built-in account, risk & safe execution PREPARATION
13. Keep Gerchik-specific limits: risk <= $50/trade (0.2% of $25k),
    daily/weekly/monthly loss cutoffs, max 3 positions, max 5 new
    trades/day, 3 losing trades stop, losing-days pause, stop behind
    level, 4R room. Implement as policy checks over native LEAN
    `portfolio`, native buying-power/order data and current equity.
    **Do not copy old `RiskManager` with virtual cash/positions/reserves.**
14. Native order behavior must be independently VERIFIED before any
    paper/live order is enabled. First milestone in original spec is
    ONE take-profit at 3R. Later 70%/20%/10% TP structure remains
    a separate unsolved milestone.
15. Official LEAN native Bracket children are held until the entry
    COMPLETELY fills, so a partial limit-entry fill can be without a
    protective active stop. The Charles Schwab integration supports
    contingent Bracket/OCO/OTO but does not support OUO or updating
    orders within a contingent set. Never imply these shortcomings are
    automatically solved by splitting into three brackets.
16. Native `OrderTicket`, `OnOrderEvent`, `Transactions`, `Portfolio`
    and `Liquidate` own the order/position lifecycle. No parallel
    broker state machine, synthetic fills, independent stop resizing or
    cancellation-race compensator. If the exact native trade structure
    is unsupported, reject trading instead of writing a workaround.
17. End-of-day flat and broker cancellations require native behavior
    validation (especially partial fills, half-days and interrupted
    connections) and user authorization before any live orders.
18. If needed, preserve **strategy decision logs** only; native
    `OnOrderEvent` is source of truth for real fills, not the old
    `journal.py` fabricated independent fill ledger.

Acceptance: verified supported/native broker behavior, native risk
checks and explicit owner approval **before** enabling execution.
A clean standalone signal-only repo is a correct intermediate result.

### P3 — hygiene, testing and release
19. Add documented LEAN-runtime smoke/contract tests in addition to
    current pure unit CI; do not confuse them with execution testing.
20. Update `README.md` and `AGENTS.md` to reflect actual code
    and clearly label unfinished ORB/hybrid, BSU and broker features.
21. Keep source lineage and decisions in a single concise document,
    not a new abstraction layer.
22. Open a DRAFT PR from feature branch to main for review; do not merge
    or enable brokerage on behalf of the owner.

## Red flags found during Qwct handoff audit

- `main.py` has NOT been executed inside actual LEAN, though syntax and
  separate strategy modules passed pure GitHub CI.
- Native `ATR/SMA` snapshots are appended to DataFrames; timestamps
  and history warmup need genuine LEAN checks.
- Single-symbol only, though the old system discussed several symbols.
- Daily trading limits / max portfolio positions / buying power not yet
  applied at order decision (signal gate is a research-only estimate).
- `pattern_bsu` preserved but not integrated into the M5 signal.
- `g01`...`g14` inherited heuristic proxies; their thresholds are NOT
  empirically validated and are not trading performance claims.
- `main.py` currently uses 2024-01-01 to 2025-01-01 placeholders;
  no historical strategy run was performed.
- Built-in LEAN native Bracket and Schwab order compatibility require
  actual runtime/API checks; **no order calls** exist in current Qwct.
- Qwct PR must not be merged before owner's approval.

## Relevant links

Qwct: https://github.com/tbsonion/Qwct
Old repo: https://github.com/tbsonion/QuantConnectTest
Old stacked PR #7 (NOT production ready):
https://github.com/tbsonion/QuantConnectTest/pull/7

Official docs:
- https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders
- https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab
- https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators
- https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events
- https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators

## Instruction to next agent

**Begin with P0: inspect current Qwct branch and the official LEAN Python
API, verify actual runtime integration, and fix only reproducible
compatibility issues. Preserve the original Gerchik decision logic.
Do not author another OMS/adapter/calendar/indicator implementation.
Document clear test evidence. Stay signal-only until explicit approval.**
