# QWCT — six-part pre-Cloud engineering freeze (2026-10-17)

**Scope:** Source-level inspection of canonical main `9bbf8f69de433d4dff0c4042213cd143ecd61737` and research draft PR #57. This report distinguishes **confirmed source behavior**, **design decision**, **missing author evidence** and **runtime unverified**. NO ORDERS. Do not silently change thresholds, time windows, scoring or Risk Gate.

## 1. Exact execution path / responsibility map

```text
LEAN Fundamental Universe (native) → screener/focus → Top 10
    → native D1 RAW/SCALED_RAW as-of warmup + ATR/SMA
    → levels.py: confirmed k-right D1 swing → ATR cluster → mirror with original_kind
    → scenarios.py: 14 feature evaluations × nearby D1 level
    → 3 scores per level → ONE global best (model, level, side)
      ├─ breakout → BreakoutRetestObserver (distinct native M5 phases)
      ├─ bounce   → RAW original D1 pivot evidence → BsuResearchLink
      │               → BsuDetector BPU1 (closed M5)
      │               → NativeSecondTvxWindow (actual SEC, opt-in)
      │               → preclose_review at BPU2_end − 30s [read-only]
      │               → closed M5 BPU2 reconciliation
      │               → BpuTvxEvidence.matches [strict pivot/cluster identity]
      └─ false_breakout → signals._check_m5 legacy 2-M5 price proxy
    → m5_runtime: build_intent → signals.evaluate_gates (8 tri-state gates)
    → runtime_reporting (CSV/statistics/logs), NO_ORDERS
```

**Parallel diagnostic branch:** `M5BsuSequenceScanner` in `m5_runtime.py` observes M5-source BSU events near frozen D1 levels independently of the selected model. This is NOT a canonical accepted bounce, and its BPU counts cannot be added to D1-linked BPU counts. `strategy/m5_reaction_taxonomy.py`, `strategy/gerchik_level_types.py` and `strategy/pipeline_audit.py` are *offline research only* and excluded by `tools/package_quantconnect_free.py:OPTIONAL_RESEARCH` from the 24-Python Free Cloud bundle.

**State ownership:** `main.py` owns LEAN subscriptions, symbol/session state, daily selection and reporting; `m5_runtime.py` owns M5 observer progression and gate attempts; `second_runtime.py` owns native-second preclose samples. Existing `signals.py` owns final gate definitions. No second trade engine is justified.

## 2. D1 selection: precise missing-candidate contract

`strategy/scenarios.py:115–219` computes all three model scores for every nearby level but retains only **one** `best` across all levels and models. Strict `score > best.score` makes ties depend on candidate/model iteration order. `main.py:393–450` arms a BSU only for that single selected `bounce`. Thus a bounce above the score threshold may never enter BPU analysis when another model wins.

Existing `scan_model_audit` counters (`bounce_scored_eligible`, `bounce_outscored`, `bounce_tie_lost`, `selected_bounce`, `no_bsu_eligible_level`) are useful **shadow indicators**, but NOT a complete independent-candidate ledger:

- `best_bounce` is the maximum score among BSU-role-eligible levels, while `best` can be a bounce on a *different, BSU-ineligible level*. Consequently `selected_bounce` is not necessarily a BSU-armed bounce and `bounce_outscored` can undercount excluded eligible BSU bounces.
- Counters aggregate evaluator invocations, not unique `(symbol, session, original pivot, model)` candidates; no precision/recall or opportunity loss can be inferred from the totals alone.
- A candidate with `score < 4` is not a 'lost eligible trade'; a score-qualified but unselected candidate is a *shadow hypothesis*, not author-approved.

**Pre-test decision:** preserve winner selection and tie rules. Measure separately: eligible-level count, score-qualified bounce count, selected winner model/level, selected BSU role and pivot; identify all distinct shadow candidates before considering multiple-model support. Do not alter `ScenarioDecision` or introduce orders in this phase.

## 3. BSU pivot / cluster / mirror price contract

| Value | Owner | Meaning | Required |
|---|---|---|---|
| `Level.price` | `levels._cluster` / `scenarios` | ATR-cluster screening price; may be median of multiple swings | Causal D1 session snapshot |
| `Level.original_kind` | `levels._mark_mirror` | Historical source role before role reversal; not the current bounce direction | For mirrors, only `support` or `resistance` |
| `RawBsuEvidence.origin_price` | `bsu_bridge.resolve_raw_bsu_evidence` | Exact native RAW original D1 high/low on historical pivot date | Native tick grid, matching EndTime and source |
| `BsuResearchLink.origin_price` | `bsu_bridge.create_bsu_research_observer` | Pivot actually used by BPU1/BPU2 detector | From RAW evidence when `require_raw=True` |
| `BpuTvxEvidence.d1_level_price` | `m5_runtime` | Frozen screening cluster price | Must equal `decision.level.price` |
| `BpuTvxEvidence.native_origin_price` | `m5_runtime` | Frozen exact pivot | Must be within 0.5 native tick of cluster to pass `matches` |

**Confirmed mismatch:** `bsu_bridge.py:252–260` allows pivot-to-cluster distance up to `native_cluster_tolerance` (ATR based). `bpu_tvx_evidence.py:60–68` and `preclose_review.py:76–86` require distance <= half a tick. This is **not** a reason to relax the downstream condition: the screening cluster and author-defined exact BSU may legitimately be different prices. Today a D1-linked research observer can arm and process BPU events that are *structurally unable to become TVX-matched*. This wastes native SECOND work when enabled and obscures the rejection cause.

**Proposed no-behavior-change resolution:** treat the strict half-tick equality as the *current execution-intent contract*, label any wider ATR-cluster-only observer `RESEARCH_CLUSTER_NOT_EXACT_BSU` **before requesting conditional SECOND** in future reviewed implementation. Report both prices and the difference in native ticks. Never relabel the median as the exact pivot, round prices into equality, or infer a new Gerchik tolerance. No modification to active bridge/matcher is included in this audit.

Mirror mapping: original support→mirror resistance→short bounce; original resistance→mirror support→long bounce. Nonmirror support→long, resistance→short. Any absent original role is UNKNOWN. The corrected source role is in main PR #56; separate 5.13 diagnostic parity is in draft PR #57.

## 4. Fourteen features — source inventory and overlap

The *14 feature identities* are in `strategy/features.py:FEATURES`; they are not 14 independent ground-truth labels. Scores are weighted heuristics, not probabilities.

| ID | Existing implementation | Potential overlap / limitation |
|---|---|---|
| g01 | squeeze | Overlaps g02/g08 price compression; distinct definitions, correlated evidence |
| g02 | tight consolidation | Overlaps g01, g04 and some M5 taxonomy labels |
| g03 | nearby retest | Breakout score also gives subfeature bonuses; not independent extra setup |
| g04 | accumulation | Price-range proxy, not confirmation of institutional accumulation |
| g05 | no pullback after false break | Uses D1 heuristic false break; not a verified M5 author pattern |
| g06 | no pullback after impulse | Shares trend/momentum evidence with g07/g09 |
| g07 | close at extreme | OHLC location proxy, not order flow |
| g08 | small bars approach | Compression/approach overlap with g01/g02 |
| g09 | context (compound) | Contains trend flags, approach, big bars, pullback-free and clean-zone; overlaps gate trend and room |
| g10 | higher-timeframe distribution | OHLC proxy; not volume-at-price proof |
| g11 | missing impulse | Proxy, not direct Gerchik author label |
| g12 | contaminated zone | Weighted positive in bounce scoring when true; author polarity requires validation |
| g13 | extremum | May overlap swing-level strength and room context |
| g14 | liquidity sweep | Candle-wick/reclaim proxy; cannot establish aggressor side or a large passive participant |

**Concrete dependency facts:** `scenarios._score_bounce` uses `g09.detail.long_pullback_free` and `big_bars_approach`, plus g12 and g13. `_score_breakout` weights g01–g10 and g03 subfeature bonuses. `_score_false_breakout` weights g11, g14, g04 and *negative* g05. All 14 are computed for each nearby level even if a particular model uses only a subset. `evaluate_all` converts exceptions to `None`; `ScenarioEvaluator` rejects a level on calculation-error reasons rather than promoting partial failures.

**Audit outcome:** No safe basis to delete any feature or rewrite its formula before author-labeled comparisons. But do not describe correlated features as independent votes or g04/g10/g14 as proof of a large player. A useful later simplification is to calculate common primitive ATR/price-distance/trend facts once per as-of snapshot, only after profiling shows measurable cost and exact outputs are preserved.

## 5. Eight gates — explicit source, duplicate checks, and authority

| Gate | Existing authority | Classification | Current certification |
|---|---|---|---|
| `trend_aligned` | D1 global+local trend | Mandatory mechanical filter; repeats g09 trend detail | Pure code tested, author accuracy unverified |
| `daily_level_valid` | Strength, touches, session `valid_from` | Mechanical; overlaps upstream level eligibility | Pure code tested |
| `m5_confirmed` | Breakout: native retest evidence; bounce: reconciled SEC BPU/TVX; false breakout: legacy two-M5 proxy | **Different proof strength by model**; cannot call all 'author certified' | Bounce actual Cloud cutoff unverified |
| `stop_behind_d1_level` | Directional stop/entry geometry | Mechanical safety | Native broker protection unverified |
| `room_at_least_4r` | Next frozen D1 level and per-share risk | Mechanical geometry; shares g09 clean-zone concept | No-next-level fails closed |
| `target_at_least_3r` | `tp_r=3`, `min_rr=3`, arithmetic | Largely restates configured target; not independent evidence of achievable 3R | Mechanical only |
| `risk_approved` | Native LEAN risk/ledger and broker protection | **Authority gate**; deliberately UNKNOWN in current research | NOT CERTIFIED; never force True |
| `matching_trade_model` | Allowed model/side enum | Basic contract / near tautology | Mechanical only |

**Important:** `TradeIntent.all_gates_passed` requires exactly eight true statuses. `m5_runtime.py` can downgrade native risk UNKNOWN to FALSE on partial mechanical blockers, not upgrade to TRUE. Therefore an 8/8 accepted trading signal is *not possible by design* in research-only mode. For acceptance reporting, separate **pattern mechanically qualified (7 non-risk checks)** from **risk/broker authorized (8/8)**; do not change gate definitions to manufacture passes. An all-true pure test fixture is not historical market evidence.

## 6. Complexity and pre-Cloud acceptance freeze

**Keep** LEAN native Fundamental, History, ATR/SMA, consolidators, as-of D1/M1/M5, native SECOND/TICK, `BsuDetector`, `BreakoutRetestObserver`, native risk observer and current reporting. Do not write a replacement broker/OMS, synthetic candle generator or second indicator engine.

**Separate** into one core acceptance path and three research-only tools:

1. Core: one frozen D1 `ScenarioDecision` → model-specific native observer → immutable evidence → canonical `build_intent` → eight tri-state gates → existing report. **No orders**.
2. Offline taxonomy: `M5TenReactionObserver` (10 labels) and `gerchik_level_types` (FIXED/FLOATING) remain external to the 24py package; not yet author-certified.
3. Independent M5-source scanner: useful exploratory case-finding only; must not be summed with canonical D1-linked BSU acceptance.
4. Offline `pipeline_audit`: independently validates 14 feature identities, eight gate identities, chronological metadata; does not replace Cloud native execution.

**Mark as future-only:** `max_spread_bps`, `data_stale_after_min`, `limit_order_timeout_min`, `max_attempts_per_level`, `reentry_cooldown_min` are configured but not actively enforced in the main signal path. Actual spread needs native quotes, and order timeouts/attempts need native order states. Do not pretend OHLC data certify them.

**Freeze checklist before Cloud:**
- [x] Main baseline identified; no active trading changes.
- [x] Read-only source pipeline traced, including research-only paths.
- [x] D1 single-winner shadow loss and counter limitations documented.
- [x] BSU RAW pivot vs ATR cluster vs half-tick TVX conflict documented; strict gate preserved.
- [x] Fourteen feature and eight gate inventories reviewed, with overlap and unverified author semantics.
- [x] Excess detectors and future-only configuration separated by responsibility.
- [x] Preclose empty/partial checks fail closed on draft PR #57.
- [ ] Confirm one true source-labeled positive and negative author example.
- [ ] Obtain **new native Cloud backtest ID** with exact code SHA, dates, symbol universe and parameters.
- [ ] Show one frozen accepted D1 case, genuine BPU1/BPU2, complete native SEC −30s, 14 feature values and eight statuses (risk may remain UNKNOWN).
- [ ] Resolve any missing M5 timestamp explicitly, never fill forward a synthetic bar.
- [ ] Run unseen holdout after code freeze and separately certify risk/Schwab before orders.

**Engineering decision:** No additional strategy edits are justified solely by this static audit. The next changes, if any, should be small, independent, test-first PRs addressing measured lost candidate counts or explicit early `CLUSTER_NOT_EXACT_PIVOT` status; do not combine them with thresholds or entry logic.
