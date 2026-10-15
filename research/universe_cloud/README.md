# Qwct Universe D1 Research — a new, separate QuantConnect LEAN Cloud project

**Purpose:** Test how much wider dynamic universe screening increases the number of **original Qwct-compliant premarket D1 level + sided-trend opportunities**, without selecting retrospectively hand-picked mega caps or weakening any thresholds. **RESEARCH ONLY / ALL ORDERS DISABLED**. This does NOT search M5 BSU/BPU, place quotes, confirm TVX, simulate fills or calculate P&L.

## Ready-to-copy complete 5-file Cloud setup

In QuantConnect create a **new Python Algorithm** project named `Qwct-Universe-Research`. The existing `Qwct-BSU-Research` and original `Qwct-LEAN-Test` remain untouched. Create/reuse an actual `strategy/` folder for the following files (do NOT paste all source into one huge main.py).

| QuantConnect project path | Use exact GitHub source | Action |
|---|---|---|
| `main.py` | [Cloud main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) | Replace starter file |
| `strategy/__init__.py` | [Cloud-ready package init](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/strategy_init_cloud.py) | Create as **`strategy/__init__.py`**, not `strategy_init_cloud.py` |
| `strategy/config.py` | [Existing canonical config](https://github.com/tbsonion/Qwct/blob/main/strategy/config.py) | Add |
| `strategy/indicators.py` | [Existing canonical indicators](https://github.com/tbsonion/Qwct/blob/main/strategy/indicators.py) | Add |
| `strategy/levels.py` | [Existing canonical levels](https://github.com/tbsonion/Qwct/blob/main/strategy/levels.py) | Add |

`strategy/screener.py` **is NOT a sixth Cloud file**: its **unchanged original canonical functions** are already bundled inside the Cloud-ready `strategy/__init__.py`, matching the tested main Qwct Free-packager's reuse pattern. The repository's canonical `strategy/__init__.py` is **not identical** to this Cloud-ready file; **do not use the tiny upstream original for this project** or it will fail to import the screener. No additional imported `strategy/` modules are needed.

### Controlled smoke test

- Defaults **2024-04-01 through 2024-04-05**, **five US trading days**. QuantConnect parameter `scan_start` / `scan_end` if explicitly set will override defaults. Hard-coded `<=14 calendar days` horizon prevents expensive accidental sweeps in the Free instance.
- Read-only native LEAN **Fundamental Universe** using Qwct's **unchanged** `select_liquid_fundamentals(fundamentals, cfg)`: price >$5, positive daily volume/fundamental data, highest native historical dollar volume, at most **50**. It records the historical selected ticker list by algorithm-local day; no survivorship-biased modern static symbol list.
- At **09:29 ET** each equity session, fetch ONE batched native **RAW D1 History[TradeBar]** for that day's actual selected symbols and exclude bars of the current or future session. Recompute **native LEAN ATR(14), SMA(50), volume-SMA(20)** from those D1 TradeBar objects as-of last closed market day, **not** custom indicator math. Missing or inconsistent history does not pass screening.
- Stage 2 calls the unchanged original `passes_gerchik_screener` using the native D1 close, ATR and 20-day average share volume, then takes the top **10** by original 50-candidate liquidity rank.
- For those actual 10-or-fewer watchlist symbols, call original Qwct `levels_for_session` with true historical D1 swing confirmation, minimum 2 touches, strength, mirror exclusion, and source-valid-from. Find original levels no farther than 1×ATR from yesterday's close. Derive bounce direction exactly as in canonical `ScenarioEvaluator` relative to the prior daily close; `global_trend` and `trend_direction` must BOTH match that direction under unchanged original `allow_countertrend=False`. The tool logs **how many symbol-days** meet these **D1-only** conditions, **not** completed BPU or profitable trades.
- Fundamental universe selection and D1 checks intentionally happen on the same historical trading day. Do **not** treat the final universe membership table as investable if an event or a future bar appears: `missing_same_day_universe` or `same-day/future or invalid D1` must be diagnosed first.
- **Different price basis caveat:** This diagnostic intentionally uses RAW D1. The primary Qwct warmup uses SCALED_RAW indicator history; around corporate events they may diverge. Before promoting findings into the main system compare normalization and as-of split handling.
- The script does not import original `Qwct-LEAN-Test/main.py`, register a broker, subscribe to M5/second data, place orders, or alter prior BSU data. The engine's **five-day screen** is a ***measurement of opportunity coverage***, not a fully validated Gerchik backtest.

### Expected initial native Cloud logs

```text
QWCT UNIVERSE RESEARCH ACTIVE 2024-04-01..2024-04-05 ... NO ORDERS
QWCT UNIVERSE DAY 2024-04-01 candidates=... d1_qualified=... watchlist=... watch_near=... watch_aligned=...; NO M5 / NO ORDERS
...
QWCT UNIVERSE SUMMARY days=... candidate_days=... d1_ready=... stage2_pass=... watchlist_days=... watch_with_two_touch=... watch_with_near_level=... watch_with_trend_aligned_bounce=... unique_aligned_symbol_days=... rejects=...; NO M5 / NO SEC / NO ORDERS
QWCT UNIVERSE EXAMPLE ... (only examples with near D1 levels, up to 16)
```

**Important:** This is a **new research branch and is not yet native QuantConnect-verified**. GitHub CI tests prove standalone Python syntax, original gate reuse and no order method references, **not** that the Cloud Fundamental Universe callbacks/data quotas execute successfully. If the Cloud returns `missing_same_day_universe`, `native_history_error`, Python import failures, backtest timeout or insufficient data, submit exact logs and adjust the research-only harness, not canonical filters.

## Why this comes after the prior failed candidates

The previous **three** native PPHL-only strict+time events were **countertrend under the current Qwct two-SMA mandatory rule** and not original Qwct two-touch levels. Instead of weakening two separate gates to force those three cases into apparent trading signals, this research counts naturally occurring **point-in-time, canonical D1+trend-eligible** ticker-days across a broader universe. Whether any actual BPU1/BPU2/TVX triggers is a separate subsequent experiment.

Primary materials and remaining unverified expert labels: [Gerchik rule/source audit](https://github.com/tbsonion/Qwct/blob/main/docs/research/gerchik_rules_ground_truth_20261015.md). Official LEAN documentation: [Fundamental Universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes), [Liquidity Universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/liquidity-universes).

## Audit safety

No trades, no portfolio or paper execution, no 30-second TVX, no claim of 3R/4R actually filled, no strategy rule change. Stop and review the Cloud native outcome before enlarging the date range or attaching M5.
