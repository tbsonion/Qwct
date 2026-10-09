# Qwct native-first migration map (2026-10-09)

Source: `tbsonion/QuantConnectTest` commit `20101293ca797344de4399227ddd97ad3c49e1f8`
(PR #7 branch; old repo untouched).

| Source module | Qwct destination / decision |
| --- | --- |
| `config.py` | `strategy/config.py` copied |
| `levels.py` | `strategy/levels.py` copied; ATR references are now from native LEAN |
| `features.py` | `strategy/features.py` copied 14 groups; missing ATR -> unavailable |
| `scenarios.py` | `strategy/scenarios.py` copied |
| `signals.py` | `strategy/signals.py` copied 8 gates; native indicator data required |
| `patterns_bsu.py` | `strategy/patterns_bsu.py` preserved but not wired |
| `sessions.py` | `strategy/sessions.py` preserved as strategy-specific entry windows |
| `indicators.py` | **Not copied**. LEAN AverageTrueRange/SimpleMovingAverage feed snapshots |
| `calendar.py` / `events.py` | **Not copied**. LEAN schedules and exchange hours |
| `orders.py` / `legacy_adapter.py` | **Not copied**. No OMS or broker adapter |
| `risk.py` | **Not copied**. Virtual portfolio ledger removed; strategy $50 sizing remains a signal-only proposal |
| `journal.py` | **Not copied**. Log intents now; future fills from LEAN OnOrderEvent |
| `lean/engine.py` | **Not copied**. Single official QCAlgorithm entry point |
| `data.py` | Custom CSV/synthetic generator **not copied**. Minimal completed-bar view only |
| ORB / Hybrid | **Not copied**; prior branch not yet integrated |

## Preconditions for sending even one real/paper order

1. Prove actual Python `main.py` compatibility inside supported LEAN runtime
   and review the resulting order behavior.
2. Select a broker-supported, native stop/TP mechanism where partial limit
   entries remain protected; Bracket's complete-fill trigger is NOT enough.
3. Validate real LEAN Portfolio/BuyingPower limits and the original $50
   per-trade risk, daily stops and max positions without a shadow ledger.
4. Verify EOD liquidation behavior during partial fills/cancel races.
5. Obtain explicit approval to enable order submission; no brokerage credentials
   in this repository.

No trading-enabled function has been included in this PR.
