# QWCT 2.5 — Six-case native D1 → M5 Gerchik proxy research

**Status: source and pure regression tests committed; QuantConnect native Cloud run NOT YET PERFORMED.** Read-only study. This is a **new fourth Cloud project**, not a modification of `Qwct-LEAN-Test`, `Qwct-BSU-Research`, or `Qwct-Universe-Research`. Do not place orders.

## Why a fourth project

Native QWCT 2.4 completed REAL LEAN research over April 8–19, 2024. It observed `BASIS match=6 rebased=8` in 14 Shadow stock-day rows. This is a **fixed six-case retrospective experiment** on its six distinct RAW/SCALED MATCH candidates; **not a new screener, new strategy, manual BSU certification, or a trade backtest**.

The existing `strategy/patterns_bsu.py` **`BsuDetector`** and `strategy/native_m5_validation.py` already implement closed-M5 BPU rules and native-bar admission; **we reuse both without changes**. The repo's `strategy/bsu_bridge.py` was also reviewed. Its `create_bsu_research_observer` explicitly requires an **actually accepted canonical `ScenarioDecision(model="bounce")`**. QWCT 2.4's Shadow D1 shortlist was NOT proven to have such a canonical accepted decision, so this study does **not** invent one merely to invoke the bridge. Instead it applies the same traced native D1 origin/cluster safeguards, creates a **separately labeled proxy observer** with the existing `BsuDetector`, and leaves canonical acceptance **UNKNOWN**.

## Fixed, genuinely observed prior cases

| Session (ET) | Ticker | Side | Original native RAW D1 origin date | RAW origin extreme | D1 cluster median |
| --- | --- | --- | --- | ---: | ---: |
| 2024-04-10 | TSLA | Short | 2024-03-11 | 182.87 | 183.56 |
| 2024-04-11 | TXN | Long | 2024-03-26 | 167.51 | 167.325 |
| 2024-04-16 | AAPL | Short | 2024-03-11 | 174.38 | 173.99 |
| 2024-04-16 | AMAT | Long | 2024-03-28 | 202.71 | 202.19 |
| 2024-04-18 | META | Long | 2024-03-15 | 481.34 | 481.57 |
| 2024-04-19 | NFLX | Long | 2024-03-28 | 601.57 | 602.785 |

These prices and dates are **immutable source-identification references**, not manufactured BSU labels, not placement prices and not future-selection guidance. WMT's subpenny pivot and other REBASED origins are intentionally outside this test. Do not infer the April 15 selection that original QWCT 2.4 didn't scan.

## New QuantConnect Cloud project: create these EXACT seven files

**Project name:** `Qwct-M5-SixCase-Research` (new Python LEAN Cloud project; do not reuse any prior QC project).

| New Cloud path | Copy directly from existing GitHub main path |
| --- | --- |
| `main.py` | [`research/m5_cloud/main.py`](../../research/m5_cloud/main.py) |
| `strategy/__init__.py` | [`research/m5_cloud/strategy_init_cloud.py`](./strategy_init_cloud.py) — intentionally empty of runtime imports |
| `strategy/config.py` | [`strategy/config.py`](../../strategy/config.py) |
| `strategy/indicators.py` | [`strategy/indicators.py`](../../strategy/indicators.py) |
| `strategy/levels.py` | [`strategy/levels.py`](../../strategy/levels.py) |
| `strategy/patterns_bsu.py` | [`strategy/patterns_bsu.py`](../../strategy/patterns_bsu.py) |
| `strategy/native_m5_validation.py` | [`strategy/native_m5_validation.py`](../../strategy/native_m5_validation.py) |

Important: **do not** substitute the full repo `strategy/__init__.py` for the special Cloud `strategy/__init__.py`. There are **no other imports** in this isolated project. Do not copy or edit `strategy/bsu_bridge.py`, the old BSU project, or the original strategy.

**Dates (defaults in new `main.py`)**: `scan_start=2024-04-10`, `scan_end=2024-04-19`. Saved project parameters override defaults. Ensure startup log `QWCT M5 SIX CASE ACTIVE 2024-04-10..2024-04-19`.

## What the code actually checks

- Subscribes to native **six equities × Resolution.MINUTE RAW**, **no fill forward**, regular session only. Official LEAN **`self.consolidate(symbol, timedelta(minutes=5), self._on_m5)`** produces native 5-minute `TradeBar` data; `validate_m5_tradebar` rejects non-native-period/fill-forward/zero-volume/inconsistent candles.
- At **09:29 ET** of each target session, requests **180 actual native closed RAW D1 and 180 closed SCALED_RAW D1** bars for **only that day's target symbol(s)**, using existing LEAN History API and native LEAN `AverageTrueRange` + SMA (not homemade indicators).
- Computes the existing original `levels_for_session` swing clusters. Requires the same **observed pivot day, exact RAW extreme (no rounding), level median, support/long or resistance/short, valid_from, original left/right swing confirmations and native tick**. Rechecks GLOBAL and LOCAL SMA trend agreement as in the original Shadow ranking.
- Verifies both original native RAW and SCALED_RAW **pivot high/low and most recent completed D1 close** agree within half the current native tick, and their original native `EndTime` timestamps match; **REBASED / missing / future / invalid = reject**, not silently corrected or relabeled.
- Only after these **algorithmic BSU proxy** checks can the unchanged `BsuDetector` observe actual **CLOSED** consolidated M5 candles for BPU1 exact native-tick touch, immediate-next-bar BPU2, breach/luft invalidation. Separately counts **strict** BPU1 (same tick without half-tick tolerance), **strict BPU2**, and whether **-30s preclose nominal clock** falls in configured 12:00–13:30 bounce window. **No SEC/TICK or preclose observations are made.**
- Emits per-session `QWCT M5 READY/REJECT`, final `QWCT M5 SUMMARY`, six `QWCT M5 CASE` rows and up to 16 BPU event lines. The historical `QWCT BASIS` baseline cannot be replaced or "improved" by this fixed-case retrospective test. **Zero orders, theoretical fills, win-rate/PNL or auto execution.**

## Expected next evidence — NOT an expected outcome

Run **one native Cloud Backtest** for Apr 10–19. Return **the entire log**, especially `QWCT M5 SUMMARY`, all `QWCT M5 CASE` rows, `QWCT M5 READY/REJECT`, and any `QWCT M5 BPU1/BPU2` events.

**Do not assume all six will pass the new independent D1 provenance/trend checks**. E.g. the original D1 Shadow qualified them, but native closed daily history fetched under their new minute subscriptions must reproduce it. Any `REJECT` requires debugging with actual logs; it is not proof of invalid trading setups. If no closed M5 BPU is observed, report zero genuine **research observations** without inventing a BPU2 or a missing data row.

Before calling anything a **Gerchik-valid BSU**, independently manually inspect actual D1 bars and label original pivot geometry. Before actual TVX-entry research, use SEC/TICK evidence at exactly **30 seconds before the BPU2 close**, with explicit fill data limitations. There is **NO permission to modify the original algorithm** from a D1/M5-only observation.

Background official QuantConnect docs: https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/getting-started and https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators .
