# Qwct — Full Gerchik Strategy: Daily Status & Open Questions
**Snapshot: 2026-10-09 (America/New_York)**

## Scope / release truth

Repo: https://github.com/tbsonion/Qwct
Draft PR: https://github.com/tbsonion/Qwct/pull/1
Feature branch: `feat/lean-native-gerchik-foundation-20261009`
Code snapshot before this report: `5e8668b5c3695c229681b181a9acf43f8b61e868`
CI at snapshot: https://github.com/tbsonion/Qwct/actions/runs/38000479003
Result: **8 Python tests passed**, compiled Python. These tests do **not** invoke the
actual LEAN runtime or Schwab; no authenticated brokerage test/backtest was run.
Main has NOT been merged with this PR. There is no trading-enabled path.

### The target

Automatically trade the user's *Gerchik Levels / LMS* intraday strategy on
US liquid equities, grounded in D1 levels, M5 confirmation, structured
pre-market scenarios, strict risk rules and limit entries, using the
**existing QuantConnect LEAN** and Schwab brokerage support where documented
and verified. No second OMS / gateway / exchange calendar / ATR engine.

The specification is `docs/strategy_spec.md`, and the cross-provider order
capabilities are `docs/SCHWAB_LEAN_COMPATIBILITY_2026-10-09.md`.
Never claim that feature-name similarity between the Schwab retail UI,
Schwab Trader API and LEAN's Schwab implementation proves identical behavior.

## Completed in repository today (code only unless explicitly noted)

- Started a **fresh Qwct** repo and draft PR #1, preserving `main`.
- Preserved the original `strategy/config.py` parameters, D1 price levels
  (`levels.py`), 14 feature groups g01–g14 (`features.py`), 3 scenario
  models (`scenarios.py`), 8 mandatory M5 trade gates (`signals.py`),
  Gerchik-specific entry windows (`sessions.py`) and the separate
  BSU/BPU1/BPU2/TVX observation detector (`patterns_bsu.py`).
- `main.py` uses LEAN `QCAlgorithm`, `add_equity`,
  `history[TradeBar]`, D1/M5 `consolidate`,
  `AverageTrueRange`, `SimpleMovingAverage`, `schedule.on`,
  and reads `portfolio.total_portfolio_value`. These calls were
  identified from the official LEAN docs but have **not** been run in LEAN.
- Deleted/avoided all old `orders.py` / `OrderManager` /
  `NativeBracketGateway`, fake brokerage, own NYSE calendar, duplicate
  position/balance ledger and fake market feed in the new repository.
- Explicitly fail closed when native ATR is unavailable. Stopped new M5
  signals when native LEAN market-close schedule reaches its pre-close
  cutoff; includes early-close dates by design (runtime still unverified).
- Cross-referenced the publicly documented **Schwab** and **QuantConnect
  LEAN** order types and partial-fill limits; wrote the compatibility
  evidence table.
- GitHub Actions pure unit checks: **8 passed**. NO LEAN integration
  run, no Schwab connection and no performance claim.

## Entire strategy requirements vs current implementation

Legend:
- `CODE / UNVERIFIED`: source code exists, but no real LEAN runtime evidence.
- `PARTIAL`: some logic exists, but full documented rule is absent.
- `ABSENT`: no implementation in current Qwct.
- `DOC ONLY`: official API read, but no runtime/broker evidence.

| Strategy area | Status | Actual missing work / open question |
| --- | --- | --- |
| LEAN project/runtime | CODE / UNVERIFIED | Run algorithm in matching actual LEAN Python, confirm imports, history indicator updates, consolidation handlers, date rules |
| Real D1/M5 bars | CODE / UNVERIFIED | Bar end times, ET timezone, warmup, session-roll, as-of/no-lookahead, opening and half-day boundaries |
| Scanner / trade universe | PARTIAL | Single configured symbol AAPL by default; no dynamic 500k avg daily volume, ATR>=1, price>$5 **multi-stock selection**, nor 'familiar symbols' policy |
| Pre-market written scenario | PARTIAL | Levels/scenarios generated and debug logged, but original fields and persistent per-symbol preopen planning record are absent |
| Daily level detection | CODE / UNVERIFIED | Compare automated clustered swings/mirror behavior to actual annotated charts; source `level_sources.py` (gap/round/prev close/5d extremes etc.) intentionally not moved; decide which sources are required |
| 14 feature groups | CODE / UNVERIFIED | Each ATR threshold/proxy must be checked against original course examples; distinguish true/false/unavailable correctly |
| Three models: bounce, breakout, false-breakout | PARTIAL | Rule scoring exists; complex false breakouts expressly not defined by the source and should not be invented |
| D1 global/local trend | CODE / UNVERIFIED | LEAN SMA snapshots; check trend calculation, timing, lookback and available indicator state |
| Eight mandatory gates | CODE / UNVERIFIED | Evaluate against real M5, ensure no fake `room=999`; risk gate currently preliminary only |
| BSU/BPU1/BPU2/TVX | PARTIAL | Detector exists but is NOT integrated into `main.py`; ~30-second TVX needs SEC/TICK data; M1/M5 approximations must be labeled, not treated as exact |
| Entry windows | CODE / UNVERIFIED | Gerchik-specific 10:30–15:00 model windows (not NYSE hours); check with LEAN time and real close |
| Screening for spread / entry chase / freshness | PARTIAL | Config thresholds exist; live quote spread, stale-data/no-chase and attempt/cooldown gates are not enforced in main.py |
| Earnings / news / relative-strength context | ABSENT | Source docs mention broader context; no connected reliable earnings/news/sector market context provider yet; decide mandatory vs optional |
| Signal sizing $50/trade | PARTIAL | Nominal 0.2% of $25k is represented; no final native buying-power, stock lot-size, minimum price increment, portfolio constraints |
| Risk daily/week/month and behavioral stops | ABSENT | Implement **strategy** caps using authoritative LEAN Portfolio / transactions: max 3 positions, 5 daily entries, 3 losses stop, 2 losses + 1 win stop, 3 losing days -> 3-day pause, 3% day/week, 10% month, stop never loosened |
| Native entry limit order | DOC ONLY | Never submits an order; verify documented LEAN-Schwab path (do not add another adapter) |
| Protected initial stop | DOC ONLY | Native bracket children only after FULL entry fill; partial limit fill may be unprotected. **No confirmed safe Schwab mechanism** |
| First-month one fixed TP 3R | ABSENT | Native Bracket/OTO/OCO docs are not proof of safe partial-fill execution; verification required |
| Later 70% TP3R, 20% next technical level, 10% trail | ABSENT | User-desired. Official spec makes it conditional after month one; confirm phase vs immediate intent; no verified native 3-target safe Schwab order graph |
| Move stop after first 70% TP | ABSENT | Need precise '1:1 (break-even)' semantics and confirm Schwab allows required contingent-order changes (current integration docs say updates restricted) |
| EOD cancellation and exit | ABSENT | LEAN schedule stops signals 5min before actual close; **does not liquidate holdings or cancel orders** |
| Position/fill/error journal + Excel | PARTIAL | Signals appear via Debug/Log only; native filled orders and durable decision explanations/export/report not implemented |
| ORB / Stocks in Play / hybrid | ABSENT | Old source had unmerged separate research branch; not part of current Qwct algorithm |
| Multiple tickers and simultaneous risk | ABSENT | main.py accepts one `symbol`; max 3 concurrent holdings policy not enforced |
| Backtest, slippage/fees, walk-forward evaluation | ABSENT | No strategy-performance run or profitability evidence |
| Broker ops: authentication, disconnects, trading sessions | ABSENT | Schwab integration never connected or runtime tested; no real money authorization |

## Key questions to answer from the strategy, not by inventing code

1. **Level labeling**: which level sources are mandatory (D1 swing/mirror,
   prev close, gap, round numbers, 5-day high/low), and how to score/
   invalidate zones versus lines? The original method includes subjectivity.
2. **Rule equivalence**: do the 14 parametrized ATR heuristics match
   annotated Gerchik examples? Are thresholds accepted or provisional?
3. **Complex false breakout**: original training notes do NOT define it;
   exclude unless a specific, verifiable rule is supplied.
4. **TVX precision**: exact ~30sec before BPU2 end requires a supported
   resolution that can actually observe :30 without future-bar leakage.
5. **Session/stock selection**: approve instrument universe, data coverage,
   unknown-market/familiar-ticker policy, market context and news filters.
6. **Entry risk**: native LEAN/Schwab mechanism for safe stop on **partial
   fills** of a limit entry is not established. This is not a reason to
   build a custom software OMS.
7. **TP staging**: original spec says a single 3R target in first month and
   later 70/20/10 conditional on results; make sure actual owner intent is
   reflected before enabling any execution.
8. **Stop/target adjustments**: exact stop to "1:1", 20% level target, 10%
   trailing, 25% max profit giveback, and broker-supported modifications.
9. **Native risk sources**: count fills/open orders/positions and realized
   drawdowns from LEAN broker-authoritative state, without maintaining
   fictitious cash/reservations.
10. **Acceptance**: run in actual LEAN and demonstrate decisions against
    annotated known examples, no future data, market hours and zero orders
    in signal-only mode. Further broker execution requires explicit
    authorization and actual supported API behavior.

## Prioritized next work, performed with parallel architecture checks

**Track A — platform evidence (P0, no trading):**
- Confirm exact LEAN Python API signatures and runtime load for Qwct main.py.
- Verify D1/M5 bar timestamps, warmup and daily technical indicator values.
- Native exchange schedule incl. early closes; no homemade calendar.
- Add reproducible LEAN smoke test and record actual output.

**Track B — strategy completeness (P0/P1, no brokerage):**
- Compare levels/scenario thresholds/14 features and 8 gates to annotated
  spec/examples; fix discrepancies, not invent new assumptions.
- Decide source instruments/screens, level sources and false-breakout scope.
- Attach BSU/BPU timing only where matching data resolution is supported.
- Add durable decision provenance for a full daily premarket plan.

**Track C — native risk/Schwab feasibility (P0/P1 research only):**
- Map every Gerchik risk rule to native LEAN Portfolio/order data.
- Read both official Schwab developer docs/quantconnect Schwab support for
  native Market/Limit/Stop/Bracket/OCO/OTO and documented restrictions.
- Investigate the native partially-filled-entry protection gap and safe TP
  graph *as documentation/runtime compatibility research only*; keep no
  trading flow enabled and do not write substitute OCO/OUO logic.
- Make every unresolved native order behavior a recorded blocker, not
  an invented feature.

**Track D — tests/release:**
- Distinguish pure Python logic tests from actual LEAN integration tests,
  broker connectivity tests, and performance studies.
- Draft PR only, no merge without permission, no paper/live order,
  credentials or strategy-profit run without explicit user direction.
- Update this status matrix when *evidence*, not an assertion, changes.

## Official documentation already captured

- `docs/SCHWAB_LEAN_COMPATIBILITY_2026-10-09.md`
- `docs/AGENT_HANDOFF_2026-10-09.md`
- QuantConnect Schwab:
  https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab
- Native LEAN Bracket:
  https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders
- Schwab API entry point:
  https://developer.schwab.com/

**DO NOT STATE THAT THIS STRATEGY IS RUNNING, CORRECT OR PROFITABLE
BASED ON THE EIGHT UNIT TESTS.** The existing Qwct release is an unmerged
signal-only foundation and the compatibility documentation is not a
broker execution test.
