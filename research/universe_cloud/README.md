# Qwct Universe D1 Research — a new, separate QuantConnect LEAN Cloud project

## LATEST native LEAN 5-day outcome: dynamic screen CONFIRMED; BSU role mismatch next

**Actual QuantConnect LEAN v2.5.0.0.18179**, run `247db2a140c2ae2a6790fbee82ffb1a4`, April 1–5 2024, completed in 34.11s. Native typed `History[TradeBar]` with `list(symbols)` is **confirmed fixed in real Cloud**; the prior tuple overload problem is resolved. Orders off.

| Measurement | Real value | Proper interpretation |
|---|---:|---|
| Native Fundamental stage1 | 50 candidates × 5 sessions = **250 candidate-symbol-days** | Historical dynamic universe, not 250 separate tickers |
| Native D1 histories ready | **246 / 250** | Four rejected: `insufficient closed RAW D1` (historical factor/start-date warnings, no synthetic fallback) |
| Original Qwct stage2 pass | **227 / 246** | Candidate-symbol-day count across the full 50, not 227 independent setups |
| Original 10-stock watchlist | **50 symbol-days** | Up to 10 per day; not 50 unique tickers |
| Has a two-touch D1 level (any distance) | **50 / 50** | Such a level can be far away |
| Has D1 level within 1×ATR | **3 / 50** | **AMZN Apr 1**, **AMZN Apr 2**, **AMD Apr 5** |
| Close-relative Scenario bounce direction agrees with native SMA trend | **2 / 50** | **Same AMZN resistance 179.835 on TWO adjacent days**, **NOT two independent opportunities**, and still no BPU or model scoring |
| AMD 2024-04-05 | D1 near, trend neutral `G=0,L=0` | Not aligned |

**Important methodological issue in actual log:** the apparent two AMZN `trend_aligned` results are tagged **`resistance` at 179.835**, **below** prior-day closes **180.38** and **180.97**, and the earlier D1-only code calls the hypothetical bounce side `long` because it mirrors Qwct `ScenarioEvaluator` (position relative to close). But original independent `BsuDetector` maps **resistance → short** and **support → long**. A `resistance` below price may be a *role-reversal* hypothesis, but the existing `levels_for_session` had **not** labeled this level `mirror` (and D1 study expressly excludes confirmed mirrors). Therefore **those two counts cannot be presented as two candidate long BSU bounces without further source/role reconciliation**.

**NEXT code is already prepared — one-file diagnostic, no rule change:** [research/universe_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) still computes the exact **old** `watch_aligned` and `aligned_level_days`, and **adds** `BSU_ROLE_OK / BSU_ROLE_MISMATCH` to `EXAMPLE` rows. It additionally reports `watch_bsu_role_aligned`, `bsu_role_aligned_level_days`, `bsu_role_conflict_level_days`, **unique ticker** counts separately from ticker-day counts. `BSU_ROLE_OK` requires original `support+long` or `resistance+short` **and** the already required sided SMA alignment. `BSU_ROLE_MISMATCH` is a diagnostic, **not a new trade filter or rewritten canonical Qwct algorithm**.

**Action:** in the SAME existing `Qwct-Universe-Research`, replace **ONLY Cloud `main.py`** from [GitHub](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py), leave the other four files and other QuantConnect projects unchanged, rerun **2024-04-01..2024-04-05**. Paste `QWCT UNIVERSE SUMMARY` and `QWCT UNIVERSE EXAMPLE` (DAY lines optional). **This additional read-only role branch has passed pure GitHub tests but has not yet been verified in native Cloud**. Avoid adding M5 until we know whether there are any role-consistent premarket D1 candidates. The 4 insufficient-history rejections remain legitimate unknown data, not losing trades.


## 2026-10-15: REAL native LEAN first run — tuple-to-list typed History fix prepared

Actual LEAN Engine **v2.5.0.0.18179**, run `c9fdcf0711e0f00dd55768003c71ac2e`, 2024-04-01..2024-04-05, **successfully produced five daily Fundamental selections of 50 stocks each (250 candidate-days)**. However, `d1_ready=0`, `stage2_pass=0`, `watchlist_days=0` because **ALL FIVE** native batched D1 `History[TradeBar]` calls raised `No method matches given arguments for history: (<class 'tuple'>, ...)`. Thus **ZERO watchlist counts are a HISTORY OVERLOAD ERROR, NOT evidence that no historical stocks qualified**. No trades/orders were submitted.

**Root cause shown in source:** the project stored original top-50 picks as `tuple(selected)` and subsequently passed that Python **tuple** into LEAN's *typed* `self.history[TradeBar](symbols, 180, Resolution.DAILY, ...)`. The earlier successfully verified BSU project passes a **Python list** of Symbols (`[symbol]`) to the same typed API. LEAN overload binding rejected the tuple, before any D1 values could be examined.

**Minimal targeted patch committed:** the standalone [research/universe_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) now calls `self.history[TradeBar](list(symbols), 180, Resolution.DAILY, ...)`. Retains original selected *membership*, Fundamental ranking, 50/10 constraints, unchanged screener/levels/trend, RAW histories, date window, and **no orders**. New regression checks verify typed-history receives an actual list, not a tuple; **now native Cloud-verified by run 247db2a140c2ae2a6790fbee82ffb1a4 (see top)**.

**Historical instructions for the already verified tuple fix (superseded by the role-audit rerun above):** Previously the only Cloud change was `main.py`. Keep `strategy/__init__.py`, `strategy/config.py`, `strategy/indicators.py`, `strategy/levels.py` exactly as they are. Run Save → Build → Backtest with SAME April 1–5, 2024 dates. Paste `QWCT UNIVERSE DAY`, `QWCT UNIVERSE SUMMARY`, and any `QWCT UNIVERSE EXAMPLE`. If errors remain, examine the exact LEAN log rather than loosening screening gates or introducing an alternate API.


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
