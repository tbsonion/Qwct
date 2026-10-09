# Schwab × QuantConnect LEAN: official capability check
Reviewed: 2026-10-09. Scope: US equities, Qwct Gerchik Levels.
Research/documentation verification ONLY; not a broker integration test.

## Evidence levels — do not conflate them

- **Both document a feature**: Schwab official public education/product guidance
  and QuantConnect's Schwab brokerage integration documentation.
- **LEAN API documented**: an official QuantConnect Python method/signature
  appears in the algorithm docs.
- **Runtime verified**: the exact Qwct program was run successfully inside
  a matching LEAN engine version. **NOT ACHIEVED**.
- **Broker verified**: the exact order behavior was independently validated
  on the connected Schwab integration. **NOT ACHIEVED**.

Schwab's developer portal advertises trading API products but the public
landing page is **not** a full authenticated Trader API order-schema contract.
The official Schwab product/articles describe terminal trading platforms.
They **do not** prove the same functionality is exposed identically via API.
Use QuantConnect's Schwab integration docs as the published integration
contract, not assumptions based on thinkorswim/StreetSmart UI.

## Trading order matrix (no Qwct execution implemented)

| Capability | Schwab official / QC Schwab integration | LEAN algorithm API | Qwct decision |
| --- | --- | --- | --- |
| Equity Market, Limit | Supported | Native market/limit orders | Documented, not submitted |
| Equity Stop Market | Supported | Native stop-market order | Documented, not submitted |
| Entry + one TP + one stop (Bracket) | Schwab integration lists Bracket | `self.bracket_order` | Do not enable until partial-fill behavior proven |
| OCO | Schwab integration lists One Cancels Other | `self.one_cancels_other_order` | No use until integration proof |
| OTO | Schwab integration lists One Triggers Other | `self.one_triggers_other_order` | No use until integration proof |
| OUO | **Not supported** by Schwab integration | LEAN `self.one_updates_other_order` exists | **DO NOT USE** |
| Contingent set update | **Not supported** by Schwab integration (cancel and replace is allowed in docs, but unsafe as a general workaround) | Order tickets have update APIs | **DO NOT WRITE RECONCILIATION / WORKAROUND** |
| One entry with scaled TP 70/20/10 and protected stop | No verified Schwab-native structure | LEAN has order compositions, but OUO unsupported on Schwab | **UNVERIFIED; no implementation** |
| Protection during partial entry fill | Schwab legacy *StreetSmart Edge UI* guide describes progressive bracket coverage; NOT a Trader API guarantee | LEAN documented Bracket/OTO children wait for FULL entry fill | **UNSAFE TO ASSUME; block execution** |
| Exact $50 maximum loss | Stop market order does not guarantee stop price in gaps or thin markets | LEAN's backtest fill behavior differs from live | Size intended risk at $50, but never guarantee realized maximum |

Relevant official references:
- Schwab Developer Portal: https://developer.schwab.com/
- Schwab product explainer on OCO and bracket: https://www.schwab.com/learn/story/how-to-use-advanced-stock-order-types
- Schwab legacy manual (not Trader API): https://help.streetsmart.schwab.com/edge/printablemanuals/edgemanual.pdf
- QC's **Charles Schwab brokerage integration** (order types, contingencies,
  update restrictions and rate limits):
  https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab
- LEAN brackets, including full-entry trigger and Python API:
  https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders
- LEAN OUO (exists in LEAN, but not in Schwab):
  https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/one-updates-other-orders
- LEAN OTO:
  https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/one-triggers-other-orders

## Native market-data and clock matrix (safe for signal-only mode)

| Qwct method | Official LEAN Python documentation | Status |
| --- | --- | --- |
| `self.history[TradeBar](symbol, 180, Resolution.DAILY)` | Algorithm Performance; typed iterable history supported | API documented; not runtime tested |
| `self.consolidate(symbol, Resolution.DAILY, handler)` | Time Period Consolidators | API documented; not runtime tested |
| `self.consolidate(symbol, timedelta(minutes=5), handler)` | Time Period Consolidators | API documented; not runtime tested |
| `AverageTrueRange(period, MovingAverageType.WILDERS).update(TradeBar)` | Average True Range, Manual Indicators | API documented; not runtime tested |
| `SimpleMovingAverage(period).update(bar.end_time, bar.close)` | Simple Moving Average | API documented; not runtime tested |
| `schedule.on(date_rules.every_day(symbol), time_rules.before_market_open(...), ...)` | Scheduled Events | API documented; not runtime tested |
| `schedule.on(..., time_rules.before_market_close(symbol, 5), ...)` | Scheduled Events; exchange-dependent close | API documented; cutoff implemented |
| `portfolio.total_portfolio_value` | Portfolio / buying-power docs | Native data source; no parallel account ledger |

Native references:
- https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-performance
- https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests
- https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
- https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/average-true-range
- https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/simple-moving-average
- https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events
- https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power

## Changes that ARE authorized based on these docs

- Keep Qwct **signal-only** and compile/test original strategy rules.
- Use LEAN's native D1/M5 candle data, native indicators, exchange schedule,
  buying-power readouts. Never approximate missing indicators.
- Stop *signals* in `_on_m5` after LEAN's `before_market_close(symbol, 5)`
  callback, including early-close sessions. No order action added.
- Keep intended initial equity in `StrategyConfig.starting_equity`;
  `main.py` reads that rather than a second literal.

## Preconditions before claiming anything more

1. Run Qwct `main.py` in **actual LEAN** and verify Python signatures,
   market hours, history timestamps, ATR/SMA snapshots and M5 callbacks.
2. Reconcile original Gerchik signal policy and research-only risk constraints.
3. Verify a brokerage-supported native protection scheme for partial fills
   without relying on OUO, editing a contingent set, or new custom order code.
4. Only with owner's explicit direction, enable even paper trading or backtests.
5. Log empirical evidence separately; do not upgrade an unverified item to
   "works" because a mocked/statically checked Python test passed.

**If no documented/verified native mechanism exists, do not build a substitute.**
