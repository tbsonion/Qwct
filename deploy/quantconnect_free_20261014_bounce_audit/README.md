# QuantConnect Free — D1 bounce arbitration audit (14 October 2026)

**Cloud-ready source snapshots for the existing 24-Python-file Qwct Free project.** Generated from the canonical Qwct main, using the same import bundling rules as `tools/package_quantconnect_free.py`. The canonical Qwct repository remains the source of truth; these are paste-ready snapshots, not independent modules.

## Exactly 3 Cloud paths to replace

1. [`main.py`](main.py) — **default next scan 2024-03-16 → 2024-04-26**; 45-day maximum and custom `scan_start`/`scan_end` are retained. Startup log confirms `QWCT SCAN ACTIVE`.
2. [`strategy/scenarios.py`](strategy/scenarios.py) — adds **read-only arbitration counters** using the original D1 `evaluate_all` feature scores, without ever overriding model selection, thresholds, tie-breaking, Level, BSU, BPU or trading gates.
3. [`strategy/reporting.py`](strategy/reporting.py) — **Cloud Free bundled** version that includes the latest canonical `strategy/runtime_reporting.py` function; prints `QWCT D1 BOUNCE AUDIT` and the existing `QWCT SCAN` summaries.

Paste each file into the **same path** in the existing QuantConnect project. Do not add a `deploy/` folder there. Do not paste canonical `strategy/runtime_reporting.py` into Cloud or substitute raw canonical `strategy/reporting.py` for the bundled snapshot.

**Existing unchanged Cloud files:** `strategy/m5_runtime.py` from the previous working Cloud scan and the other 20 unchanged Python files, plus `research.ipynb`. No orders, no simulated fills, no factor-tweaking or softened tick equality.

## Why this version is needed

User's native LEAN 2.5.0.0.18179 Feb 6–Mar 15, 2024 run had `SCENARIO=15` (all **false_breakout**), `bounce=0`, `QWCT SCAN nearest=0`, `BPU1=0`, `BPU2=0`, `ERROR=0`. Thus **no native BSU bounce observer was armed**. This outcome cannot establish that there were no BPU patterns anywhere in the market. Merely extending dates again could continue missing BPU if model arbitration consistently selects other models.

The added diagnostics distinguish:
- `nearby`: score evaluations with one or more nearby D1 levels;
- `eligible_level`: evaluations with a D1 swing_cluster support/resistance that meets structural BSU prerequisites, **not** a verified RAW pivot;
- `scored_ge_threshold`: best such D1 bounce score reaches the original `min_model_score`;
- `below_threshold`: such a level exists but its bounce score is too low;
- `outscored`: D1 bounce met the score threshold, but another selected model won;
- `tie_lost`: another model was selected at the same top score;
- `selected`: original evaluator actually selected bounce, regardless of later RAW bridge verdict;
- `no_eligible_level`: evaluated nearby levels, none structurally suitable for the native BSU bridge.

**Next native test:** update the three files, clear any stale `scan_start`/`scan_end` project parameter overrides (or set them exactly), keep `tvx_seconds=false`, run backtest. Confirm `QWCT SCAN ACTIVE 2024-03-16..2024-04-26` and review `QWCT D1 BOUNCE AUDIT`, `QWCT SCAN completed`, `QWCT SCAN NEAREST`, `QWCT SCAN EVENT`, `Qwct research summary`. Do not claim a real BPU1/BPU2 or profitability until native Cloud output proves it.

## Verification status

- GitHub pure-strategy CI **330 passed** after the implementation, regression tests include score arbitration with existing decision unchanged.
- [QuantConnect Free 24-file packaging workflow](https://github.com/tbsonion/Qwct/actions/runs/38518647619) succeeded on the current canonical `main.py`/`strategy/scenarios.py`/`strategy/runtime_reporting.py` implementation.
- **Native LEAN Cloud for 2024-03-16 through 2024-04-26 has NOT run yet.**

Always create new Cloud-ready snapshot links when these canonical files change again; never label this particular historical snapshot as automatically updated.
