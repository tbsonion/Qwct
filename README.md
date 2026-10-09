# Qwct — Gerchik Levels on QuantConnect LEAN

**Current stage: research code, signal-only.** This code does **not** place
orders, connect Schwab, simulate fills, claim profitability, or maintain a
second broker ledger. The 2024–2025 dates in `main.py` are placeholder
algorithm initialization dates, not a completed backtest.

## Full strategy status (October 9, 2026)

The feature-by-feature completion matrix and unanswered trading-strategy
questions are in **[docs/STRATEGY_STATUS_2026-10-09.md](docs/STRATEGY_STATUS_2026-10-09.md)**.
The eight standalone tests are not LEAN/runtime/broker validation. Risk policy,
partial entry protection and broker compatibility must be investigated
alongside the strategy logic, not deferred behind new homemade wrappers.

## Architecture: use LEAN instead of writing a second LEAN

| Concern | Owner |
| --- | --- |
| Market data and US exchange trading sessions | LEAN `add_equity`, `History`, consolidators, scheduled events |
| Daily ATR and SMA | LEAN `AverageTrueRange`, `SimpleMovingAverage` |
| Holdings, available buying power and eventual fills | LEAN `Portfolio`, buying-power model, `OrderTicket`, `OnOrderEvent` |
| Eventual bracket / OCO orders and EOD liquidation | **Native LEAN APIs only**, subject to brokerage capabilities |
| D1 Gerchik levels / 14 feature groups / three models | `strategy/levels.py`, `features.py`, `scenarios.py` |
| Eight mandatory M5 gates + Gerchik entry windows | `strategy/signals.py`, `sessions.py` |
| BSU/BPU1/BPU2/TVX research logic | `strategy/patterns_bsu.py` (preserved; not wired into live signals yet) |
| Configuration | `strategy/config.py` — $25,000 baseline, 0.2%/$50 risk |

The `strategy/indicators.py` module **does not calculate** ATR or SMA:
it reads daily snapshot columns populated by the native LEAN indicators.
The small `strategy/data.py` is just an *as-of view* of completed candles,
not a market feed, calendar, or custom execution system.

## What's working in code

`main.py` subscribes to US stock minute bars, seeds D1 history,
updates native D1 ATR/SMA, receives M5 and D1 consolidations,
prepares a pre-open scenario from closed D1 bars, evaluates the 14 groups
and 8 mandatory gates, filters by Gerchik time windows, and logs
qualified intents. **No order submission is implemented.**

These rules were **ported** from `tbsonion/QuantConnectTest` rather than
invented anew. The original strategy specification is preserved at
`docs/strategy_spec.md`. Review the proxy assumptions in that source;
it is not proof of strategy accuracy or expected returns.

### Run the pure tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

Those checks run without `AlgorithmImports`, brokerage credentials, or
market data. GitHub Actions runs the same checks and Python syntax compilation.
They **cannot validate** a QuantConnect LEAN runtime or Charles Schwab.

### Use inside the official LEAN environment

Use an existing QuantConnect **Python** algorithm project or create one
with the official [LEAN CLI](https://www.quantconnect.com/docs/v2/lean-cli).
Copy `main.py` and the `strategy/` package into the LEAN Python algorithm
project, and install/enable the project's Python dependencies in that environment.
Do not assume ordinary `python main.py` works outside LEAN: the
`AlgorithmImports` module comes from LEAN.

Do not enable live or paper trading. The first approved trading milestone is a
**single 3R target**, not three scaled targets. LEAN's native Bracket API
activates child exits only when the **entry completely fills**, so a partially
filled limit entry can have no active stop. Schwab does not support OUO and
restricts updating contingent orders. These require genuine LEAN/broker
compatibility tests before enabling any execution; never implement a homemade
OMS or a software OCO to hide the gap.

## Explicitly not migrated

- `orders.py` (~1,900 lines), `LeanBrokerAdapter`,
  `NativeBracketGateway`, `MockBroker`, broker simulations
- Custom NYSE holiday calculator, fake session lifecycle, simulated fills
- Shadow cash/portfolio/position balances and independent order reconciliation
- D1 synthetic market data generator, extra CSV feed, backtest/profit dashboards
- ORB/hybrid wiring from an unmerged research branch (not falsely marked ready)

## Status / remaining work

Pure Python unit tests have passed in GitHub CI. **No actual LEAN integration
run, historical trading backtest, Schwab verification or broker order tests
have been performed.** The original BSU signal activation, complete ORB/hybrid
integration, broker-native 3R exit safety, and final buying-power/portfolio
checks before entry remain open.

Native references:
- [LEAN Bracket Orders](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders)
- [LEAN History](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests)
- [LEAN consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators)
- [LEAN scheduled events](https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events)
- [Charles Schwab brokerage limitations](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab)
