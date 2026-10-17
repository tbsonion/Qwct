# QWCT native LEAN acceptance protocol — freeze before testing

**Baseline:** `main` SHA `9bbf8f69de433d4dff0c4042213cd143ecd61737`. Draft PR #57 is **not merged**; record the precise imported ZIP SHA and whether any reviewed PR files were included. Free Cloud project: exactly 24 Python files plus existing `research.ipynb`. `NO_ORDERS`; default `tvx_seconds=false` until a bounded targeted native-second run.

## Mandatory run manifest (no anonymous pasted logs)

```text
cloud_project_id:
cloud_backtest_id:
source_git_sha:
uploaded_zip_sha256:
start_date / end_date:
timezone: America/New_York
symbol_universe_and_fundamental_asof:
parameters: (including tvx_seconds, min_model_score, session windows)
data_mode: native RAW / SCALED_RAW; no fillforward replacement
algorithm_runtime_status: success / loader_error / runtime_error
full_stdout_attached: yes / no
native_data_coverage_attached: yes / no
```

A missing field is `UNVERIFIED`, not a pass.

## Sequential gates with precise evidence

| Stage | Minimum artifact | PASS means | FAIL / UNKNOWN handling |
|---|---|---|---|
| 0. Boot/import | Cloud backtest ID and complete initialization/exit logs | All packaged imports resolve; no loader/runtime error; no orders | STOP on any exception; no next-stage interpretation |
| 1. Point-in-time D1 | Frozen previous-session D1 RAW/SCALED_RAW, original swing EndTime, `valid_from`, mirror `original_kind` | D1 snapshot strictly precedes session decision, no future pivot | Reject missing role, invalid tick, future timestamp |
| 2. Model arbitration | All nearby level/model scores and winning model+level, shadow BSU role | Explain every winner and score-qualified unselected bounce, including ties | A single winner is policy, not proof alternatives were invalid |
| 3. Pivot price identity | Cluster, original RAW pivot, native tick, absolute difference in ticks | Document if strict half-tick TVX identity can ever pass | Wider ATR cluster only = research; **do not request costly SEC as if accepted** |
| 4. Native M5 continuity | Native timestamped M5 sequence and expected session grid | No missing required BPU1/BPU2 bar; no synthetic replacements | Missing SRPT 13:10 remains an explicit gap |
| 5. Model-specific M5 | Breakout: break→retest→confirm; bounce: exact BPU1 + BPU2; false break: proxy explicitly labeled | Native timestamps and causal phase sequence | Never use research taxonomy labels as author-certified truth |
| 6. Actual SEC cutoff | Conditional native SEC window, observed last price, exact `BPU2_end - 30s`, missing seconds | Real native observation at exact cutoff, never later-close inference | `tvx_seconds=false`, absent cutoff or excessive gaps => UNKNOWN/BLOCK |
| 7. Post-close reconciliation | Native closed BPU2 OHLC, earlier SEC extremes, immutable provenance | BPU2 close reconciles without lookahead, `BpuTvxEvidence.matches` true | Reject mismatched pivot, wrong session, changed side, out-of-order bars |
| 8. 14 features | One `g01..g14` map with values True/False/None, reasons, timestamp | All 14 identities present and calculated on the same frozen data | Missing/exception => explicit blocker; no default false positives |
| 9. Eight gates | All eight named gates with True/False/None and reasons | All eight statuses present; **pattern readiness** separate from `risk_approved` | Risk UNKNOWN is expected in research; do not call 8/8 PASS |
| 10. Author validity | Exact video/chart link, source time, instrument, session, D1 level, side, BPU labels; blind negative controls | Independent, timestamped author labels evaluated without tuning on same cases | If zero direct author labels, accuracy = NOT MEASURABLE |
| 11. Cohort | Point-in-time Top 10 and all screened candidate records | All candidate exclusions, model winners and coverage reported by session | No cherry-picked survivors; count unique symbols/sessions/pivots |
| 12. Holdout | Frozen SHA/params before unseen dates, all rejections and abstentions | Separate unseen period; publish precision/recall, counts, coverage and confidence | No tuning after looking at holdout; reset holdout after changes |
| 13. Risk/execution | Native portfolio history, pending orders, buying power, fills, protective stops, risk budget | Independent paper-trading certification and explicit user authorization | Remain NO_ORDERS; Schwab/live not certified by this protocol |

## Mandatory failure-mode cases (do not alter market data)

- Mirror `original_kind` absent, mirror bounce direction inverted, future swing confirmation.
- Valid ATR cluster but original RAW pivot farther than 0.5 native tick from the cluster: **research-only**, not silent acceptance.
- Score-qualified bounce loses to breakout or another level; retain the shadow record and exact tie order.
- M5 gap within BPU sequence, delayed SECOND after cutoff, SEC timestamp mismatch, SEC high/low incompatible with later M5.
- `None` feature, missing gate, `risk_approved=None`, incomplete `PrecloseReview.checks`.
- No next frozen level (4R unknown), spread unavailable (no quote-based approval), split/corporate action mismatch.

## Pass/fail vocabulary

- `IMPLEMENTED`: code path exists and has source/pure regression tests.
- `OBSERVED`: actually emitted by a named native LEAN Cloud backtest ID.
- `AUTHOR_VERIFIED`: compared with independent labeled author examples.
- `PATTERN_READY`: 7 non-risk gates TRUE on one observed canonical case, and required author evidence recorded separately.
- `TRADE_AUTHORIZED`: eight gates TRUE *plus* native broker/risk and owner authorization. **Not available in this research phase.**
- `UNKNOWN`: absent/incomplete evidence; never coerce to TRUE or FALSE unless a strict failure condition is actually observed.

**Release rule:** No Cloud success claim from pure CI; no author accuracy claim from self-generated labels; no order submission, Schwab integration or live execution without a separate authorization and native broker certification.
