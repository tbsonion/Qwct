# Qwct QuantConnect Cloud Free — ready-to-paste files (2026-10-14)

These are **generated deployment snapshots**, taken from the successful [24-file Cloud Free packaging workflow](https://github.com/tbsonion/Qwct/actions/runs/38517729167) for canonical source commit `aaa61283c92b19f552f1292ece77aacd5faf285e`. The pure-strategy regression tests passed on a subsequent docs/test commit. Do **not** maintain or edit these snapshots as a second source of truth: always regenerate them from `tools/package_quantconnect_free.py` when canonical source changes.

## Replace only these three paths in the existing project

- [Cloud `main.py`](main.py) — default research window 2024-02-06 through 2024-03-15; startup log `QWCT SCAN ACTIVE`; honors explicit `scan_start`/`scan_end` overrides.
- [Cloud `strategy/m5_runtime.py`](strategy/m5_runtime.py) — ranks nearest native RAW M5/BSU observed extrema.
- [Cloud `strategy/reporting.py`](strategy/reporting.py) — **bundled** reporting, including the canonical `strategy/runtime_reporting.py` helper. **Do not substitute the raw repository `strategy/reporting.py` file.**

Each path is the **actual Cloud-compatible version** output by the packaging rules, not the canonical source module. Do not add these files to the root Cloud project as a `deploy/` directory; copy each file's content into the *existing same-named Cloud path*.

Retain the other 21 Python files only if they match the previous working 24-file bundle, plus the existing `research.ipynb` (25th file). All trading orders remain disabled.

Expected next Cloud startup line: `QWCT SCAN ACTIVE 2024-02-06..2024-03-15`. If it still runs January–February, clear old saved `scan_start`/`scan_end` parameters or verify that the replaced `main.py` was saved.

**No actual Feb–Mar Cloud result has been verified yet.** Native backtest evidence is required to claim a BPU1/BPU2 example.
