# PR #7 — evidence-bound audit (2026-10-11, research only)

## Scope and observed baseline

- Branch: `feat/qwct-native-tvx-risk-observer-20261011`, PR #7 against `main`.
- Source: `docs/strategy_spec.md`; original pattern: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
- The 2024-01-01 to 2024-02-05 Cloud M5 smoke (provided by the owner) has **NO native SEC/TICK TVX observation**. The 456 M5 evaluations / 6 two-bar M5 confirmations / 0 orders are not performance results.
- No trading, order execution, brokerage, paper positions, simulated fills or P&L were added.
- This branch is not a native LEAN run or a broker risk certification.

## Native API contract checked against QuantConnect documentation

- US-equity data: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
  - SECOND and TICK are **distinct subscriptions**. Default US-equity prices are historically adjusted; Qwct main uses SPLIT_ADJUSTED for D1/history and its MINUTE universe. A SEC window is not available from that MINUTE subscription.
  - Existing M5 consolidators consume minute data, with fill_forward disabled in the universe. No BPU2 preclose observation can be reconstructed from completed M5.
- LEAN portfolio: https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/key-concepts
  - `portfolio.total_portfolio_value`, `portfolio.get_buying_power(symbol, direction)`, and individual native holdings are possible evidence, not a separate portfolio ledger.
- Native market close/early close: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours
  - `securities[symbol].exchange.hours.get_next_market_close(time, extended_market_hours=False)` is required for the session close passed into `RiskSnapshot`. Never infer a fixed 16:00 ET close.
- Open orders: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-management/transaction-manager
  - LEAN `transactions.get_open_orders()` exists; a total count is **not** proof of entry-only pending exposure.

## Deterministic changes made in PR #7

1. `strategy/risk_research.py`: read-only mechanical preview. Missing evidence yields UNKNOWN. In addition to 0.2% per-trade stop risk, max positions, pending orders, 5 entries/day and 3 losing trades/day, require **period-start native-equity anchors** and explicit cashflow adjustment verification for 3% day / 3% week / 10% month marked-to-market drawdown checks. Added the course's 2 losing + 1 winning daily halt. Compare realized P&L to the corresponding anchored period equity, not today's fluctuating equity. Require a native aware exchange close and reject new entries at the EOD cutoff, including half days. Normalize .NET Decimal monetary inputs.
2. `strategy/tvx_observation.py`: only consumes caller-supplied complete consecutive completed `SEC` 1-second candles. No interpolation from minute bars, no assumptions of tick/second access. Reject a window if the BPU1 state has since invalidated. Requiring 270 consecutive positive-volume seconds is deliberately stricter than normal market activity and **may exclude legitimate setups**; it is not a canonical Gerchik rule.
3. `strategy/patterns_bsu.py`: a later completed M5 BPU2 must contain the previously recorded native SEC preclose extrema or the research observation is INVALIDATED. This prevents contradictory SEC-vs-M5 sources from being advertised as confirmed.
4. Added deterministic regression cases for missing anchors, drawdown thresholds, mixed win/loss halt, DST-aware timestamps, early-close cutoff, decimal values, SEC/M5 range disagreement and invalidated BPU1.

## Contract mismatches that remain deliberately unimplemented

| Requirement | Current evidence and blocker |
| --- | --- |
| Historical BSU | D1 confirmed native swing pivot **proxy**, not separately labeled canonical Gerchik BSU. Cluster median is distinct from originating pivot. |
| BPU1 exact touch | Native M5 extrema and tick tolerance are observed; can't prove full discretionary model from proxy. |
| BPU2 next candle/wick/luft | Pure detector validates chronological next completed M5 and price logic; 20%-of-stop distance currently uses ATR-based estimated stop: **implementation assumption**. Native exchange session and corporate-action normalizations require runtime review. |
| TVX 30s before BPU2 closes | SEC observer is **not wired** to a validated second-level LEAN data subscription. Missing seconds and fill-forward/source provenance remain blockers. TVX is UNVERIFIED. |
| Risk lifecycle | Preview accepts explicitly provided evidence only. There is **no wired authoritative native period-baseline/realized trade-history/exposure collector**, so `risk_approved` in `signals.py` remains UNKNOWN. No separate portfolio has been built. |
| Exact stop/TP / 4R room | Separate `signals.py` gates have mechanical proxies; exact Gerchik stop placement and next daily-level completeness are not yet proven. |
| First-month 3R / later 70/20/10 | Neither is implemented for orders. Native Schwab partial-fill stop coverage remains unverified. |
| Multiple positions / EOD | Main's native universe supports multiple symbols; **broker-enforced** max 3/EOD flat are not verified. EOD order logic remains behind the false source kill switch. |
| Complete 8-gate research signal | M5 proxy not full Gerchik. No canonical TVX / native risk approval. Zero orders is intentional. |

## Release gate

Pure CI (compile + pytest) must be green **on the final PR head**. That does not establish actual LEAN behavior. Before claiming native integration, inspect exact imported Python versions, SEC availability/subscription permissions, SEC timestamps/ff/volume provenance, M5 aggregation consistency, half-session boundaries, D1 corporate-action normalization and portfolio API behavior in an actual isolated no-orders QuantConnect run. **Do not merge on a pure green CI alone if the expected release definition includes native integration.**

No new PR. No order paths enabled. No brokerage adapter, fake fills or profit calculations.
