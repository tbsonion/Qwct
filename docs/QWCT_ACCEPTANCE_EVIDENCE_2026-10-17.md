# QWCT — acceptance evidence and next Cloud run (2026-10-17)

Status: **RESEARCH ONLY / NO ORDERS**. This is a checkpoint, not a live-trading certificate.

## What changed without reinventing the strategy

- Existing main branch commit `9bbf8f69de433d4dff0c4042213cd143ecd61737` already carries the **original D1 mirror role preservation** fix (#56).
- Draft [PR #57](https://github.com/tbsonion/Qwct/pull/57) aligns the separate QWCT 5.13 research runner with that canonical mirror behavior, so it no longer auto-rejects every proven mirror merely because it is a mirror. Missing original source role or wrong bounce side still fail closed.
- Extended existing pure regression tests: **both short- and long-side** FIXED/FLOATING evidence, M5 false break, follow-through, mirror retest and missing native M5 continuity.
- New **read-only** `tools/qwct_acceptance_snapshot.py` reuses saved real Cloud stdout JSON; it does not create candle data, a trading engine, trades, labels or acceptance.
- Independent `tests/test_qwct_acceptance_snapshot.py` rejects swapped provenance, missing features, fabricated M5 completeness, higher scores inconsistent with recorded rejections, invented eight-gate statuses, or imaginary SECOND queries.

## Machine-checked frozen evidence: 2024-06-03, AMAT/NFLX/SRPT/MSFT

The original 5.10 and 5.12 snapshots are user-supplied QuantConnect output, **not independent agent execution**. For these four predeclared symbols:

| Check | Actual evidence | Meaning |
|---|---|---|
| 14 feature fields | 56 recorded evaluations; 0 reported feature calculation errors | Mechanical evaluation, not predictive accuracy |
| M5 native bar completeness | **311 / 312**; SRPT missing one timestamp `2024-06-03T13:10:00` | Incomplete strict coverage, **not** 312/312 |
| D1 current model score | **0 accepted, 4 rejected** at minimum score 4 | No accepted canonical D1 decision |
| Source types | All 4 are `mirror/swing_cluster`; saved `bsu_origin_eligible=false` comes from an older diagnostic | **Retest after PR #56**, do not use stale flag for conclusions |
| 10 M5 classifications | Four detailed stdout rows **omitted** by output truncation | Not available in this snapshot; NEVER infer zeros or PASS |
| FIXED/FLOATING | Four stdout rows omitted | Not evaluated in this snapshot |
| Eight gates | **NO_CANONICAL_GATE_EVALUATION** on all 4 | Zero *evaluations*, not eight failures or eight passes |
| Seconds / TVX | 0 conditional-second queries | No genuine TVX -30s evaluation |
| Direct independent author M5 labels | **0**; native matched predictions **0** | Precision/recall **NOT MEASURABLE** |
| Risk Gate and orders | Unchanged; orders disabled | Not an execution or broker certification |

The current scope is ***as-of information integrity and regression safety***, not strategy accuracy or profitability. Positive-looking software events are not automatically author-confirmed Gerchik setups.

### Repeatable report

From this repository root with Python 3.11+:

```bash
python tools/qwct_acceptance_snapshot.py
python -m pytest -q tests/test_qwct_acceptance_snapshot.py tests/test_qwct_511_cloud_runner.py tests/test_m5_ten_reactions.py tests/test_gerchik_level_types.py
```

The report fails closed when the archived observation contract changes. Do not rewrite old 5.10/5.12 data to make the report pass; newer observations belong in **new** versioned native Cloud reports with their run IDs.

## Remaining blockers and how to eliminate them

1. **Cloud baseline**: create a clean Free algorithm using the existing [CI-produced 24-Python-file artifact](https://github.com/tbsonion/Qwct/actions/runs/39006201248) and keep the 25th `research.ipynb`. Run existing bounded signal-only baseline. Collect **backtest ID**, model source commit and full native end report. New main algorithm contains no extra test/audit files.
2. **Research-runner mirror parity**: on the separate research project (not the 25-file main), load tested QWCT 5.13 runner from PR #57 with the **matching current strategy modules**; collect full D1 per-symbol score, source-role, rejected-reason rows after PR #56. Do not mix main branch and PR branch code. No assumption that past 5.12 result is still definitive for mirror provenance.
3. **Independently labeled Gerchik examples**: identify exact chart/video source author, timestamped M5 native US-equity equivalent, frozen D1 source level and both positive/negative labels *before* inspecting QWCT predictions. The existing 5.2 evaluator is the acceptance tool. Editorial examples are not direct author-labeled M5 truth.
4. **One genuine accepted case**: after causal point-in-time D1 acceptance, exercise *existing* `strategy/pipeline_audit.py` for 14 feature identities and all eight canonical gates on genuine native data. Do not force a pass by lowering min score, altering session windows or treating UNKNOWN as True. Ensure exact BPU1, next completed BPU2 and no missing M5.
5. **TVX**: conditionally use existing `strategy/native_second_tvx.py` and LEAN-native seconds with a real cutoff 30 seconds before BPU2 close. Reject incomplete seconds and reconcile after close without lookahead. No TVX assertion from a completed M5 bar.
6. **Cohort → holdout**: freeze rules before unseen dates, preserve native Fundamental point-in-time Top 10 and independent `symbol + session + original pivot` counts; publish coverage/abstentions as well as signals. No P&L claim without a proper out-of-sample execution model.
7. **Risk and Schwab**: research only until separately approved. Use native LEAN OrderTickets, OnOrderEvent and brokerage fill constraints, not another broker adapter or custom synthetic OMS. **NO ORDERS** in this PR or Cloud baseline.

The SRPT gap is *accounted for and fail-closed*. It is not a data-source repair. Precise CVD/aggressor-side order flow and confirmation of a large passive limit player are separate, unresolved data-entitlement/attribution issues.

## Provenance and reusable components

- [Gerchik.com BSU/BPU article](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya) — **editorial** description, not a timestamped direct author-labeled US-equity trade.
- [LEAN built-in PivotPointsHighLow](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/pivot-points-high-low) — pivot comparator, **not** proof of Gerchik BSU equivalence.
- [LEAN historical-data requests](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests) — use native historical bars/time semantics, no homemade feed.
- [QuantConnect Free file quotas](https://www.quantconnect.com/docs/v2/cloud-platform/projects/files) — 25 files, 32 KB per file; keep 24 Python + 1 research notebook.
- [Previously reviewed ready-made comparators](READY_MADE_GERCHIK_BSU_BPU_SOLUTIONS_2026-10-13.md) — MT4/MT5 visual comparison only. No independently verified drop-in Gerchik Python/LEAN engine identified.

**Done now:** source/logic/provenance regression assurance and machine-enforced truthful evidence status. **Not done yet:** Cloud replay, direct author accuracy, accepted setup, TVX, holdout profitability, trading risk certification and broker order execution.
