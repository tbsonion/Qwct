# QWCT — clean QuantConnect LEAN Cloud project bootstrap (2026-10-17)

## Principle: reuse the tested LEAN bundle, not another pasted strategy

**Canonical source:** tbsonion/Qwct, `main` commit `9bbf8f69de433d4dff0c4042213cd143ecd61737` (the tested baseline at preparation time). No live/paper orders.

**Ready 24-Python-file bundle:** [successful QuantConnect Free workflow, run 39006201248](https://github.com/tbsonion/Qwct/actions/runs/39006201248) — artifact **Qwct-QuantConnect-Free-24py**. Download the workflow artifact; it wraps `Qwct-QuantConnect-Free-24py.zip`. **Extract BOTH archive levels.** The inner ZIP contains `main.py` and 23 `strategy/*.py` files. Do **not** paste an archive into the Python editor as code.

The same commit also passed [full pure Python tests](https://github.com/tbsonion/Qwct/actions/runs/39006201220) and [cohort pure regression tests](https://github.com/tbsonion/Qwct/actions/runs/39006201278). Pure CI checks do NOT prove actual QuantConnect Cloud historical feed behavior or Gerchik accuracy.

## New Free Cloud project — exact scope

1. In QuantConnect Algorithm Lab create a **new Python algorithm project** (e.g. `Qwct-LEAN-Research-Reset`); keep the auto-created `research.ipynb` without adding any other research files.
2. Replace the project `main.py` with **the packaged `main.py`**, not the raw GitHub repo `main.py` or any historic notebook cell. Add the **exact 23 packaged strategy files** under the `strategy/` directory, preserving paths and `strategy/__init__.py`. These 24 Python files plus one default notebook use all **25 Free slots**. The bundle is intentionally transformed by the existing `tools/package_quantconnect_free.py`; never mix it with old individual modules.
3. Do **not** add `qwct_pipeline_runner.py`, notebooks from `research/chart_review_qc/`, tests, old helpers, code from prior chats, or a second `strategy/data.py` to this project. Those are separate *Research* tasks; adding files to the 25-file Free project causes quota/import drift.
4. Baseline run: leave `tvx_seconds` absent/false; leave `scan_start` and `scan_end` absent to use the existing safe defaults `2024-03-16` to `2024-04-26` (45 calendar days maximum), unless the research question explicitly requires a bounded alternative. Do **not** alter strategy scores, timeframe windows, or risk thresholds to force signals.
5. Confirm the Cloud **BUILD and BACKTEST** independently. Required evidence: engine version, project/build/backtest IDs, initial `QWCT SCAN ACTIVE` log, end-of-algorithm research summary, Native D1/M5 diagnostics, any import errors, and **0 submitted orders**. If build fails, first compare the full 24-file manifest to the artifact; do not fix imports through ad hoc substitutions.

**Sources:** [QC file quotas (Free: 25 files, 32 KB/file)](https://www.quantconnect.com/docs/v2/cloud-platform/projects/files) and [native consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators). [LEAN CLI cloud push is documented as paid-tier](https://www.quantconnect.com/docs/v2/lean-cli/api-reference/lean-cloud-push); the manual Cloud project copy is the Free-compatible route.

## Acceptance sequence — one blocker at a time, no new trading engine

| Stage | Acceptance evidence | Stop condition |
|---|---|---|
| 0. Cloud package | 24 Python + one notebook; no import errors; 0 orders | Any missing/wrong module, unexpected order or Cloud quota issue |
| 1. D1 provenance | Frozen premarket RAW native D1, historical original pivot, mirror original role, price normalization and grid; causal as-of proof | A `swing_cluster` median misreported as original Gerchik BSU |
| 2. Author labels | Independently selected, source-linked positive **and negative** Gerchik BSU/FLOATING/FIXED examples, with actual source screenshots/timestamps and human labels | No trustworthy labeled cases: accuracy must remain UNKNOWN |
| 3. M5 reactions | Ten individual classifications on native complete M5 with time and OHLC; separate missing-native-minute rejects (SRPT 2024-06-03 13:10 was 1 missing of 312) | Forced fill-forward/synthetic bars or unverified candle interpretations |
| 4. 14 features / 8 gates | For a **truly accepted** frozen D1 setup: complete feature/gate pass/fail/unknown ledger, native BSU/BPU as-of trace | 4 June 3 D1 cases rejected; cannot claim they passed eight gates |
| 5. TVX | Real, eligible native SECOND feed, pre-close -30 seconds cutoff and causal reconciliation; do not derive from completed BPU2 | Inadequate historical SEC coverage or lookahead |
| 6. Cohort and holdout | Point-in-time Top 10 cohort, fixed thresholds and unseen dates, unique symbol/session/pivot accounting | Tuning on holdout or cherry-picked scores |
| 7. Execution | **SEPARATE explicit approval**, native LEAN risk/order semantics and Schwab paper alternative researched | NO ORDERS until risk/execution certification |

## Reuse-first decisions

- Keep original QWCT main/strategy modules and official LEAN native `History`, `Consolidate`, RAW/SCALED_RAW, Fundamental Universe, indicators, exchange calendar and portfolio. Never build a custom feed, ATR/SMA, broker adapter, synthetic fills, OMS or OCO.
- LEAN `pphl()` is a **pivot comparator**, not an author's confirmed Gerchik BSU. Native `rdv()` is a **cumulative same-time-of-day relative volume** comparator; not an arbitrary M5-bar RVOL replacement.
- Existing QWCT evaluation research and [ready-made Gerchik comparator audit](../docs/READY_MADE_GERCHIK_BSU_BPU_SOLUTIONS_2026-10-13.md): free MT4/MT5 **Trade by levels/TBL** can only be used for visual comparison; no verified open-source Python/LEAN drop-in implementation was identified. Do not port a closed-source MT indicator or unrelated opening-range-breakout as if equivalent.
- [Official Gerchik BSU/BPU rules](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya) are the author reference for exact BPU1 touch, immediate BPU2, 20%-stop luft, and -30s TVX. The existing `docs/strategy_spec.md` is the separate course-summary research contract.

## Current known limits (not solved by making a new project)

QWCT 5.12 (four symbols, June 3 2024) returned **0 accepted D1 scenarios, 4 rejected** because the current scores were below 4; all four nearby levels were mirrors. That is not evidence of a crashed engine. M5, eight gates and TVX did **not** run in 5.12. A later merged fix (PR #56) preserves a mirror's original source role in the canonical scenario/BSU bridge; the previous 5.12 result predates fresh Cloud verification of that change.

There is no independent native Cloud certification of the new project here. **Do not mark GitHub pure tests as Cloud PASS**. CVD/aggressor-side order flow cannot be promoted using Quote/Trade tick records without an entitled, validated aggressor classification feed.

## Boundaries

NO TRADES / NO PAPER / NO SCHWAB, no forced threshold changes, no extra files in the 25-file main algorithm, and no claim of Gerchik author's accuracy until independent labeled cases and Cloud holdout are available.
