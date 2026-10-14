# Qwct-BSU-Research — separate empty QuantConnect Cloud Python project

**Status:** code prepared / GitHub pure tests only. **Native LEAN Cloud has NOT been run for this new project.** Preserve the existing `Qwct-LEAN-Test` unchanged.

## What to do in the empty project

In the new **Qwct-BSU-Research** project, replace the default `main.py` and create the `strategy` folder with the following six **unchanged, canonical Qwct** modules (7 Python files total):

| Cloud path to create/replace | Ready-to-copy GitHub link | Why |
|---|---|---|
| `main.py` | [research/bsu_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/bsu_cloud/main.py) | New read-only LEAN orchestrator |
| `strategy/__init__.py` | [strategy/__init__.py](https://github.com/tbsonion/Qwct/blob/main/strategy/__init__.py) | Python package |
| `strategy/config.py` | [strategy/config.py](https://github.com/tbsonion/Qwct/blob/main/strategy/config.py) | Original frozen config |
| `strategy/indicators.py` | [strategy/indicators.py](https://github.com/tbsonion/Qwct/blob/main/strategy/indicators.py) | Native ATR series reader |
| `strategy/levels.py` | [strategy/levels.py](https://github.com/tbsonion/Qwct/blob/main/strategy/levels.py) | Same confirmed as-of D1 swing/cluster detector |
| `strategy/patterns_bsu.py` | [strategy/patterns_bsu.py](https://github.com/tbsonion/Qwct/blob/main/strategy/patterns_bsu.py) | **Same** exact-native-tick BPU1, immediate BPU2 and 20%-stop luft |
| `strategy/native_m5_validation.py` | [strategy/native_m5_validation.py](https://github.com/tbsonion/Qwct/blob/main/strategy/native_m5_validation.py) | Verify actual LEAN consolidated M5, timestamps and observed volume |

**Do not paste the old 24-file Cloud bundle into this new project**; it would run a different algorithm and consume unnecessary Free quota. New project uses only 7 files plus the editor's optional template `research.ipynb`.

Once the seven paths are saved, run `Build → Backtest`. Default dates are **2024-03-16 through 2024-04-26**, three explicit symbols **MSFT / AMZN / AAPL**, no configuration UI needed. That initial small sample makes it possible to compare historical MSFT April 11 $427.83 pivot near-miss, but this scanner will also test **other** structural levels rather than just the chosen D1 bounce winner.

## Research mechanics

1. Subscribe to real US Equity **RAW** minute bars with `fill_forward=False`.
2. At **09:29 ET**, request already closed **RAW daily TradeBars** for each subscribed symbol; compute each day's ATR14 through LEAN's built-in `AverageTrueRange` updated exclusively from historical daily TradeBars (no homemade ATR).
3. Reuse Qwct `levels_for_session` and `native_cluster_tolerance` to select **all confirmed as-of support/resistance swing clusters** (`swing_cluster`, at least 2 touches, minimum level strength). **No model selector and no Bounce Score ≥4 requirement.**
4. Use each swing cluster's **original RAW bar high/low** as BSU origin, **never** the potentially fractional-price median; fail closed on missing origin, tick-grid misalignment and origin/cluster provenance.
5. Use LEAN's native `consolidate(symbol, timedelta(minutes=5), handler)` and Qwct's existing `validate_m5_tradebar` to process only completed, observed-volume, regular-session M5 TradeBars. Pass these bars to the *unchanged* `BsuDetector`.
6. Print capped `BSU RESEARCH BPU1`, `BSU RESEARCH BPU2`, `BSU RESEARCH NEAREST` and `BSU RESEARCH SUMMARY` rows. This independent research project's BPU2 is **close-of-bar evidence only**: no pre-close -30s TVX validation, no risk approval or order execution.

Native split events invalidate current day's observers. Historical price normalization/corporate actions are **not fully certified** by this first scan; cross-split cases require separate as-of factor-file validation. BPU1/BPU2 must not be treated as production signals or backtest trades.

## What success looks like

Start of logs: `BSU RESEARCH ACTIVE 2024-03-16..2024-04-26 MSFT,AMZN,AAPL; ALL ORDERS DISABLED`.

End of logs: `BSU RESEARCH SUMMARY symbols_warmed=... candidate_level_days=... M5=... checks=... BPU1=... BPU2_closed=... rejects=...; NO ORDERS`.

An `exact` touch is only when the actual M5 high (resistance) or low (support) equals the **original RAW swing price** within half the security's native tick. A gap of $0.04 on a $0.01-tick stock is **not exact**. A `BPU2_closed` result is not proof the price met TVX **30 seconds before BPU2 closed**.

If a result is blocked by RAW D1 history or data quality, bring the actual LEAN Cloud logs back for debugging. **GitHub CI does not verify QuantConnect API binding/runtime here.**

## Readiness and reproducibility

- Research source: `research/bsu_cloud/main.py`.
- Original Qwct detector and levels are **imported**, not rewritten.
- Pure source tests: `tests/test_separate_bsu_cloud_research.py`.
- Official LEAN API references:
  - [Time-period TradeBar consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators)
  - [Typed History with normalization modes](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests)
  - [Native ATR indicator](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/average-true-range)
  - [US equity corporate actions](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)
