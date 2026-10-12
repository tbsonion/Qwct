# External profitable-strategy study: ORB / Stocks in Play vs Qwct Gerchik

Prepared 2026-10-11 for the user-requested **education / design audit**.
**Do not merge ORB into Gerchik. Do not submit paper/live/broker orders.
No QuantConnect historical profitability backtest was performed by Qwct.**
The original Gerchik specification remains `docs/strategy_spec.md`.

## 1. Verified primary comparator and significant replication warning

Original research: Carlo Zarattini, Andrea Barbon, Andrew Aziz,
*A Profitable Day Trading Strategy For The U.S. Equity Market*,
written 2024-02-16, posted 2024-03-15; latest SSRN revision 2025-04-29.

- Paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284
- 2016–2023 sample; >7,000 historical US stocks; top-20 Stocks in Play
  5-minute opening-range-breakout portfolio; authors report
  **>1,600% cumulative net backtested return, 2.81 Sharpe,
  36% annualized alpha** after their specified transaction costs.
  These are the AUTHORS' historical estimates, not verified live
  trading and not reproduced in Qwct.

Independent implementation and exploration published by QuantConnect
research engineer Derek Melchin in December 2024:
https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/

- C# LEAN 5-minute ORB: 2016 one-year backtest, selected top 20
  first-5-minute abnormal-volume names from the 1,000 liquid-stock
  candidate pool; paper-style ATR stop + per-asset notional cap;
  **Sharpe 2.396 vs SPY 0.836 and beta -0.042** *in that one year*.
- Parameter sensitivity: 17/25 tested opening-duration and universe
  combinations exceeded the stated SPY Sharpe benchmark; changing
  volatility criterion to ATR >1% of price produced Sharpe 2.237.
  This does not certify untouched 2017-2026 out-of-sample return.
- **CRITICAL CONTRARY EVIDENCE**: the discussion's Python port
  returned ~-0.148 Sharpe rather than C# 2.396, and -0.189
  when the commentator constrained the period to 2016.
  Staff acknowledged the Python implementation was NOT functionally
  equivalent (different ATR filter / daily+minute data and indicator
  concerns). The code *name* or paper *name* is insufficient proof.
  The discussion also questions backtests on other years, slippage
  and actual fees.

QuantConnect publication is C# code and published analysis;
**not** an audited live brokerage execution track record.
Reported figures are incommensurate across the original 8-year study,
QC one-year C# recreation, and a differently implemented Python port.

## 2. Exact research idea: time-of-day relative opening volume

At precisely 09:35 ET, after the real completed [09:30,09:35] M5 candle:

    RVOL_5m_today = real_stock_M5_volume_09_30_to_09_35_today /
                    mean(real_stock_M5_volume_09_30_to_09_35_over_14_prior_sessions)

All fourteen reference volumes are observed *first-5-minute* volumes,
**not** 20-day DAILY average share volume, and they are not an
estimated 1/78th of daily turnover. The 14 sessions must be strictly
historical, distinct and backed by real native LEAN bars. Mixed
split-adjustment volume bases are UNKNOWN. A statement that RVOL>1
predicts Gerchik profitability would require a fresh independent test.

`strategy/opening_volume_research.py` and
`tests/test_opening_volume_research.py` implement/check a **standalone,
read-only comparator** which accepts externally supplied real native
M5 session openings and never generates orders. It does NOT fetch
history, select stocks, modify any Gerchik score, subscribe to SEC/TICK,
or certify true LEAN runtime data. History and clock validity are
fail-closed. Historical trading-day continuity must be checked by
LEAN's native exchange calendar, **not** reconstructed here.

## 3. What ORB had that Qwct currently lacks (priority-ranked)

| Finding | ORB evidence | Qwct actual state | Decision |
|---|---|---|---|
| A1: Stock in Play | 14 previous same-time opening 5m traded volumes; top-20 by ratio | Prior-day dollar volume top-50; 20-D1-day average daily volume; top-10 frozen at 09:29 ET | **High**: useful candidate-rank study ONLY. Cannot rank at 09:29 using future 09:35 M5. Separate 09:35 as-of observational stage, not retroactive premarket data |
| A2: Universe breadth | Paper >7k stocks; QC 1k at stage 1 | Top 50 then 10; may miss today's catalytic moves | **High**: test selection/recall, data & Cloud Free constraints; no blind 1k universe import |
| A3: Volatility normalized to price | QC sensitivity test ATR/price >1%, Sharpe 2.237 | Fixed $1 ATR and price >$5; plus unresolved historical split normalization | **High**: record ATR/price for sensitivity only. Don't replace Gerchik mandatory min ATR unilaterally |
| A4: Risk across portfolio | QC per-position risk and equal-weight notional cap | Provisional $50 risk from signal; no fully broker-native simultaneous risk, leverage, pending orders, concentration | **P0 for execution**: native portfolio caps/ledger before orders |
| A5: Real exits | QC stop during day and exit at close | EOD methods exist, source kill-switch false; exits not active | **P0 for execution**, safety-first native LEAN/Schwab fills/cancels |
| A6: Realistic friction | QC discussion highlights trading costs / slippage differences; LEAN fee/slippage/fill models exist | No broker fill / fee / slippage measured; pure signal checks only | **P0 for performance claims**, make explicit cost/stress matrix |
| A7: Short borrow reality | Native LEAN has ShortableProvider and borrow rate modeling | Research accepts short models without verified borrow availability/rates | **P0 for executing short signals**, license / broker data dependent |
| A8: Robust out-of-sample | QC presents 2016 plus parameter grid; commenter questions 2016–2024 returns | Qwct historical Jan–Feb 2024 was only a *signal-only smoke*; no trade P&L | **P0 before claiming profits**: walk-forward splits, unchanged parameters, 2016–2026 if feed supports, adjust splits/fees |
| A9: Component equivalence | C# and Python reports diverged dramatically | LEAN native Python test still pending; unit tests test pure code & mock-shaped adapters | **P0**: native engine time/data parity, as-of evidence and actual logs before claims |
| A10: Market context | ORB implicitly captures event-driven relative activity | 14 D1 heuristic features but no true earnings/catalyst, index/sector relative strength | **Optional research only**; event/market signal is NOT a user-approved Gerchik mandatory rule |

## 4. Confirmed false claims to avoid

- `strategy/config.py` and `strategy/sessions.py` had old comments
  referring to an `orb_stocks_in_play` or `hybrid.py` module.
  Qwct's actual branch does **NOT** include the original ORB/hybrid
  trading system (see `docs/migration_map.md`).
- The research-only RVOL comparator implemented here does not change
  that. It is *not* another strategy, does not trade and cannot
  produce a verified Sharpe ratio.
- A missing opening 5m traded bar is UNKNOWN. Filling forward creates
  optimistic data leakage.
- 09:35 relative-volume selection cannot legally influence a 09:29
  D1 decision in the same trading session. If eventually researched,
  compute D1 candidate eligibility at 09:29; attach RVOL observations
  only when the actual 09:35 bar is observed.
- The 5-minute ORB opening range is **not** Gerchik's D1 level,
  BSU/BPU1/BPU2 30-second TVX entry; do not substitute one for the other.
- Even two backtests on the 'same' ORB paper can differ by
  Python vs C# implementation, data normalization, warm-up,
  risk caps, fill handling and transaction cost assumptions.

## 5. Checklist for future separate experimental comparison

- Freeze and version each paper replication and Gerchik change.
- Confirm RAW vs SPLIT_ADJUSTED price/ATR/volume consistency across
  stock splits and survivorship-free universe membership.
- For each day record all candidate stocks (selected and excluded),
  09:29 D1 attributes, only THEN 09:35 opening RVOL; separately
  preserve original discretionary level explanations.
- Intraday gaps, earnings/catalysts and news MUST have known publication
  timestamp; unavailable is UNKNOWN, not guessed.
- Run ORB separately as a control only if approved, with genuine
  separate code/project and comparable data entitlements/time range,
  **not** via Qwct's Gerchik risk-manager abstraction.
- Use QuantConnect's native backtest / fee / slippage, volume-share
  price-impact, exchange calendar, ShortableProvider when accessible;
  keep missing entitlements explicit.
- Compare OOS Sharpe, CAGR, maximum drawdown, hit rate, expectancy
  in net R/trade, turnover, capacity, gross vs net costs, tail losses,
  losses around earnings and split dates, no-trade/session rates and
  stability across several untouched market regimes.
- Run fee/spread/slippage stress and statistical uncertainty; avoid
  selecting the best outcome from repeated searches. Walk-forward
  documentation:
  https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization
- Study broker-supported protective stop behavior and partial fill
  reconciliation before permitting ANY paper/live orders.

Official execution feasibility and realism references:

- Native LEAN volume-share slippage:
  https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models
- Native LEAN short availability/borrow:
  https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/shorting
- LEAN reporting statistics:
  https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/report
- QuantConnect overfitting research guide:
  https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide

**Release:** PR #7 remains draft and unchanged Gerchik rules, no
new cloud native backtests, no broker orders, no merge. More profitable
looking past studies are useful *independent comparators*, not a
permission to relax eight mandatory Gerchik signal and risk gates.
