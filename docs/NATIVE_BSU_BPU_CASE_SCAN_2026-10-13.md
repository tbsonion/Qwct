# Qwct native LEAN BPU1/BPU2 historical case scan (2026-10-13)

## Why this scan exists

2024-01-02 NVDA native Cloud evidence: accepted bounce, verified RAW BSU pivot 502.66, cluster 502.57439794, 76 native M5 checks, M5 maximum high 493.00 (**$9.66 below pivot**) and no exact touches, thus no BPU1/BPU2. This is **not** a bug to solve by moving or rounding the pivot.

We explicitly reuse the existing native LEAN universe, as-of D1 History, real RAW M5 consolidator, `BpuTouchAudit`, `BsuDetector`, `_signal_rows`, and end-of-run reporting. We **did not** introduce an alternative signal engine, market feed, a simulated fill, an OMS, or any trades.

## What is now implemented on GitHub main

**Project parameters:**

| Parameter | Format | Meaning |
| --- | --- | --- |
| `scan_start` | `YYYY-MM-DD` | First LEAN backtest day; default `2024-02-06` |
| `scan_end` | `YYYY-MM-DD` | Last LEAN backtest day; default `2024-03-15` |
| `tvx_seconds` | `false` | Keep SECOND data **disabled** while searching first for native M5 touches |

A single run is limited to **45 calendar days** to protect Cloud Free backtest cost/log limits. `scan_start > scan_end`, invalid dates and larger periods fail at initialization; the **Feb 6–Mar 15, 2024 scan runs automatically** when parameters are absent; the verified Jan–Feb 2024 smoke can still be run by specifying both old dates explicitly.

**Default next batch (no date parameters needed):** `2024-02-06` → `2024-03-15` with `tvx_seconds=false`. Confirm startup log `QWCT SCAN ACTIVE 2024-02-06..2024-03-15`. If the log still shows Jan–Feb 2024, Cloud has an older `main.py` or overrides these dates with saved project parameters.

Optional subsequent batches, only after examining each previous native run:
- `2024-03-16` → `2024-04-26`
- `2024-04-27` → `2024-06-07`
- `2024-06-08` → `2024-07-19`

These are exploratory **time windows**, not known positive BPU cases. No backtest beyond the prior verified Jan–Feb 2024 run has been executed by this GitHub change.

## Cloud Free deployment — IMPORTANT

**Do not paste canonical `strategy/runtime_reporting.py` into Cloud `strategy/reporting.py`.** The 25-file Free bundle inlines `runtime_reporting.py` into `reporting.py`. Do not paste canonical `strategy/focus.py` or `strategy/screener.py` as extra files either.

Use the successful **[QuantConnect Free 24 Python + notebook quota workflow](https://github.com/tbsonion/Qwct/actions/workflows/quantconnect-free-package.yml)**, download the latest successful `Qwct-QuantConnect-Free-24py` artifact ZIP, then take the *inner* `Qwct-QuantConnect-Free-24py.zip` (24 Python files), extract it, and **update the corresponding Cloud paths**. Preserve the existing `research.ipynb` as the 25th file. Do not add any other Cloud files.

Cloud changes for this scan (extract the bundled ZIP, not raw GitHub sources):
1. `main.py`: bounded optional dates and counters
2. `strategy/m5_runtime.py`: retain 5 nearest actual completed RAW M5 observations
3. `strategy/reporting.py`: brief summary and exact first BPU1/BPU2 events

Other 21 bundled source files can remain unchanged *only if* they are from the last working Cloud package and match the current GitHub strategy dependencies.

## Native evidence to read in the LEAN log

- `QWCT SCAN ACTIVE START..END`: actual selected run window; prints during algorithm initialize so missing or overridden parameters are immediately visible.
- `QWCT SCAN completed: nearest=N BPU1=N BPU2=N; NO ORDERS`.
- `QWCT SCAN NEAREST SYMBOL SESSION pivot=P M5=H/L gap=+/-N at=HH:MM exact=N`. These are real *closed M5 extrema*, ranked across accepted D1 bounces. A nearest miss is **not** a BPU signal.
- `QWCT SCAN EVENT BSU_PROXY_BPU1` or `BSU_PROXY_BPU2_CLOSED`: only from state transitions already observed by existing `BsuDetector`, never synthetic.
- `Qwct research summary: ... SCENARIO=..., ERROR=...`. Confirm `ERROR=0` and `ALL ORDERS DISABLED`.

Interpretation:
- `nearest=0`: no accepted and armed D1 bounce with valid RAW M5 across window (possible universe/filter issue, not proof no market patterns exist).
- `nearest>0` with `exact=0`: real nearby prices, but **no precise touch**; do not adjust tolerances just to make hits.
- `exact>0` but `BPU1=0`: investigate guard, chronology and source candle before changing rules. Crossing/under/over are not equivalent to an exact reference-level touch.
- `BPU1>0`, `BPU2=0`: examine the immediately following native M5 candle, `BPU invalid reasons`, out-of-order and luft; no fabricated BPU2.
- `BPU2>0`: first genuine research example. Export and manually annotate that day, then validate -30s TVX **separately** with SECOND feed opt-in. Do not claim an executable trade, statistical expectancy or canonical Gerchik certification.

**Scope boundary:** this tool discovers signals **only within the Qwct screened/accepted D1 bounce subset**. It does **not** enumerate every historical price-level touch in all US equities. `focus_symbol` only affects the chart, not candidate eligibility. Qwct FREE ObjectStore journal remains OFF; logs show capped nearest/event samples, not a complete dataset.

## Validation

Python source/Cloud bundle checks and `BpuTouchAudit` exact-tick regression are run by `Pure Strategy Checks` and the bundle workflow. These do **not** prove native LEAN behavior outside the prior Jan–Feb 2024 Cloud result.

- [Cloud Parameters official reference](https://www.quantconnect.com/docs/v2/cloud-platform/optimization/parameters)
- [LEAN Algorithm Parameters reference](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters)
- [Qwct prior Cloud case evidence and approach](READY_MADE_GERCHIK_BSU_BPU_SOLUTIONS_2026-10-13.md)
