# QWCT 2.8 — Historical BSU and BPU1 manual-review packet (June 2024)

**Evidence status:** Native LEAN Cloud run `4b787847b9e5d2405b2fd97a541fa71e`, engine `2.5.0.0.18184`, 2024-06-01 through 2024-06-30. **Real run complete. Manual Gerchik chart labels NOT YET PERFORMED.** This is a *read-only four-case review*, not a trade signal, retrospective strategy optimization or an invitation to loosen thresholds.

## What the real Cloud result establishes

- 19/19 intended market-session screens (14 same-day + 5 next-valid-session Fundamental callback); 950 selected stock-days, 861 Stage2 qualified, 17 role-aligned RAW historical `first_idx` swing **proxies**, 7 RAW/SCALED_RAW origin `MATCH` and 10 `REBASED`.
- 6,411 real source M1 bars, 1,326 native admitted M5 bars, **17/17 final M5 period bars emitted** via native guarded `Scan`, no runtime or detector failures, no orders.
- **Zero** `BsuDetector` BPU1, zero BPU2, zero SEC/TICK preclose TVX. Independently observed original RAW pivot-to-M5 geometry: `EXACT_WICK=0`, `SHORT_OF=1038`, `RANGE_CROSSED=11`, `BEYOND_NO_SPAN=277`. These four mutually exclusive observations sum to **1,326** candidate-level/M5 observations; the 11 range crosses occurred in **4 of the 17** original swing proxies.
- The **D1 swing cluster median** is a *separate estimated level*, often different from the frozen original RAW swing's high/low and sometimes **not on executable native tick-grid**. `CLUSTER_RANGE=14` across all cases, but `cluster_only_cases=0`; a cluster range is never a certified BPU1.
- A candle whose high/low *spans* the original RAW pivot is **not the same as a high/low extreme exactly equaling that pivot**. A native M5 OHLC range does not prove how or in what sequence the price traded there, whether the pivot traded on its exact native order tick, or whether the price was an actionable Gerchik bounce. The original pure `BsuDetector` remains unchanged.

## FOUR actual source-range crossing cases — review before any strategy edits

All M5 observations below are already admitted real native *closed* candles. Times are America/New_York (ET) for the 2024 historical target day. `delta_ticks=(cluster-raw_pivot)/tick`, tick for these original pivots is 0.01.

| Manual priority | Stock/day/side | Original D1 BSU proxy source day | Exact original RAW pivot | D1 swing cluster median | Cluster − original | Original M5 range crosses | Median in M5 range | First M5 range crossing, close ET | Nearest relevant wick to ORIGINAL RAW pivot (ET) | Price-basis source |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| P0 | **AON Jun 12 short** | May 10 2024 | **293.5900** | 293.8175 | **+22.75 ticks** | **2** | 3 | **09:35** | high **2 ticks BELOW** 293.59, at **11:30** | MATCH |
| P0 | **DELL Jun 7 long** | May 14 2024 | **128.7500** | 128.6750 | **−7.5 ticks** | **7** | 8 | **14:15** | low **7 ticks ABOVE** 128.75, at **14:50** | MATCH |
| P1 | **CRM Jun 27 short** | Jun 6 2024 | **246.7500** | 246.0550 | **−69.5 ticks** | **1** | 1 | **09:40** | high **4 ticks BELOW** 246.75, at **09:35** | MATCH |
| P1 | **ABT Jun 7 short** | Dec 4 2023 | **105.5000** | 105.3150 | **−18.5 ticks** | **1** | 2 | **10:20** | high **7.5 ticks BELOW** 105.50, at **10:15** | REBASED |

**Do not misread the nearest-wick column.** It reports the nearest *M5 high for shorts / low for longs*, not whether the price *ever* crossed the level. For example, **AON crossed its original 293.59 raw level inside the M5 range of other candles** even though the nearest recorded high was 2 ticks below the pivot; the old nearest-only display was insufficient and earlier explanations saying the price “never touched/crossed the level” were incorrect. We still have **zero exact BPU1 extrema**, and no right to count 11 range crossings as canonical Gerchik BPU1.

### Source-vs-cluster quality flags

- **AON 293.5900 vs 293.8175:** Median differs by 22.75 cents and **falls between native price ticks** (`cluster_grid=0`). Do not substitute 293.8175 as an executable quote or as historical source without an independently marked D1 level.
- **DELL 128.7500 vs 128.6750:** Median is 7.5 cents different; **off native tick grid** (`cluster_grid=0`). Up to seven M5 candle ranges spanned the RAW source. Review actual approach and breakout vs bounce with the D1 source chart and *ordered* intraday bars.
- **CRM 246.7500 vs 246.0550:** Median differs by **69.5 cents** (`cluster_grid=0`). This is a material discrepancy between the proxy used to select a stock and the original high used as the BPU detector level; trace the earlier confirmed `swing_cluster` origin rather than tuning any threshold.
- **ABT 105.5000 vs 105.3150:** Median differs by 18.5 cents, and **historical SCALED_RAW origin is REBASED**. Use **RAW as-of 2024-06-07** D1/M5 comparison; a current adjusted chart may show a different historical source number. Do not infer that historical rebasing disqualifies the RAW pivot solely from this.
- A CAT June 24 short original 333.64 vs median 334.3750 was **2 ticks short**, with **zero** original-pivot range crosses: a genuine observed near-miss, *not* among these four crossed cases.

## Single-source-of-truth manual label protocol (not yet completed)

For **each** of the four cases, assemble a **RAW/unadjusted D1 chart** extending from prior to the historical source date up to the **day before** the M5 study, plus a clearly timestamped **RAW M5 chart of the target day**. On D1 draw and label **two distinct prices** (original source pivot and algorithmic swing median); show the original D1 extremum, touching/rejection history, and explain which if either is a genuine *manual Gerchik BSU* according to the lesson, **without viewing future days after the intended morning decision**. On M5 mark the given first-range-cross bar, the nearest relevant wick and the **immediately following** completed bar, with high/low and source price visible to the cent or sub-cent where native history uses it.

Use one of these explicit reviewer decisions, leaving **unverifiable as unverified**:

| Field | Required reviewer answer |
| --- | --- |
| `manual_bsu` | `YES / NO / INDETERMINATE` |
| `bsu_level_selection` | `ORIGINAL_RAW_EXTREME / CLUSTER_MEDIAN / OTHER_MARKED_LEVEL / NONE`, with actual marked chart price and rationale; median must be treated as geometric, not blindly executable |
| `valid_d1_context` | `YES / NO / INDETERMINATE`; mention mirror/consolidation/trend-break context and whether a stronger nearer left-hand level dominates |
| `relevant_m5_first_touch` | Exact real relevant wick high/low and *timestamp*, or `NONE / INDETERMINATE`. A range crossed is recorded **separately** and does not set this field to YES |
| `immediate_m5_bpu2` | `YES / NO / INDETERMINATE`; exact immediate next M5 timestamp, extreme, stop/luft compliance, and no break of BPU1 extreme |
| `tvx_-30s` | `UNVERIFIED` until actual SEC/TICK with native timestamps; never infer from closed M5 |
| `review_artifact` | Link to two RAW annotated charts with axis values/date/time, plus reviewer and date |
| `decision_reason` | Brief source-grounded explanation with explicitly identified uncertainty |

**Actionable acceptance threshold:** only after independent manual review of **multiple positive AND negative** real historical D1/M5 examples may a human propose a new, *separately tested* BSU level-selection hypothesis. Do not modify `strategy/patterns_bsu.py`, lower exact-tick tolerance, compute hypothetical fills or change live trading gates based solely on these four retrospectives. If none qualifies as manual Gerchik BSU, the correct next experiment is independently frozen cohort selection and documented level-expiry/forward-follow-up rules, not a false BPU1.

## Reproduction and traceability

Native evidence: `research/cohort_cloud/main.py` with `strategy/bsu_touch_audit.py` (source file [`bsu_touch_audit.py`](./bsu_touch_audit.py)). Run ID `4b787847b9e5d2405b2fd97a541fa71e`. Chart prices must use appropriate split/dividend normalization compatible with original RAW and explicit historical timestamp. Legacy `research/m5_cloud` fixed six-case project and production `main.py` remain untouched. Future results: [`research/cohort_cloud/README.md`](./README.md), root [`TODO.md`](../../TODO.md).

External reference for **normative wording, not empirical signal performance**: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya (BSU/BPU1/BPU2/TVX principles) and https://gerchik.com/pdf/algoritm_forts.pdf (discusses clear vs floating levels). Their wording does **not** prove these four specific automatically detected daily levels are correct.
