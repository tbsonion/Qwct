# QWCT 2.6 — Native dynamic D1 → M5 research cohort (May 2024)

## 2026-10-15 — Chart-grounded next step shipped, no extra cohort Backtest

A separate [**QWCT D1/M5 native chart review notebook**](../chart_review_qc/BSU_D1_M5_REVIEW.ipynb) and [mirror as-of validator](../chart_review_qc/mirror_asof_audit.py) are implemented. [**One-page QuantConnect Research usage**](../chart_review_qc/README.md). Open in the **existing** QuantConnect project Research Notebook and run only AON/DELL first. The notebook visually draws original RAW D1 `first_idx` pivot and ATR swing cluster median at two different prices, and the actual OHLC 5-minute bars reconstructed from native original minute history at the June target session. Source D1 data strictly ends BEFORE 09:29 ET; time-bucket and first-cross findings must agree with the real 2.8 run or the review fails. Only the optional audit checks mirror proxy chronology, not manual certification. **Real QuantBook chart output is pending user execution.** No existing QuantConnect backtest or trade algorithm files need to change and this is not a new profitable trading signal.


## 2026-10-15 — VERIFIED Gerchik primary-book audit: level strength ≠ BPU1, mirror model is currently excluded

See **[`GERCHIK_PRIMARY_SOURCE_AUDIT.md`](./GERCHIK_PRIMARY_SOURCE_AUDIT.md)** for a detailed audit of the author's published book/official website vs `strategy/levels.py`, `BsuDetector`, and `research/cohort_cloud/main.py`. **Written author-text rules verified**: non-reaching bars can strengthen evidence for an existing *D1 level*, but are **not** a valid strict BPU1 bounce on US equities; BPU1 must reach the frozen fixed price, BPU2 is immediate and may use *its own* luft; BSU and BPU1 may approach from different sides (mirror). **Newly identified major scope gap:** `levels.py` detects confirmed `kind='mirror'`, yet current cohort `classify_snapshot` excludes mirror and restricts `support→long/resistance→short`, so this is **not a full Gerchik strategy screen**. Swing cluster ATR median / `first_idx` RAW source may differ by dozens of ticks and still needs manual fixed-level certification. Video *topics* were verified but actual dialogue/transcripts were **not** available; do not attribute the book's answer to a particular YouTube second. **No trading or detector rules changed** pending real annotated D1/M5 labels.


## 2026-10-15 — Native QWCT 2.8 completed; separate YouTube-based Gerchik specification research

**Real QuantConnect LEAN run `4b787847b9e5d2405b2fd97a541fa71e` completed successfully.** June 2024 had 19/19 market-session scans, 17 approved D1 source proxies, 1,326 native M5 observations, `BPU1=0`, `BPU2=0`, no orders or unexpected runtime errors. Geometry independent of the canonical detector: **`raw_exact=0 short_of=1038 range_crossed=11 beyond_no_span=277 cluster_ranges=14`**. The four disjoint RAW categories exactly sum to 1,326; 11 M5 *range* crossings came from four observed stock-days (AON Jun12, DELL Jun7, CRM Jun27, ABT Jun7). A separate D1 cluster median is not necessarily on executable tick grid and cannot simply replace the original RAW BSU source. **The range crossed even though no relevant M5 wick extreme was exactly equal to the source.** Earlier nearest-wick-only descriptions saying the price "never crossed the RAW level" were therefore incomplete.

**Review packet already committed:** [`BSU_MANUAL_REVIEW_JUNE_2024.md`](./BSU_MANUAL_REVIEW_JUNE_2024.md) contains ticker, source date, original RAW source price, swing-cluster median, first M5 range-cross time and precise independent labeling template for the four source-range-crossing cases. This is **manual BSU research pending**, not four confirmed trades or four BPU1s.

**User-specified additional source review:** The short official webpage is *not* the entire methodology. [`GERCHIK_VIDEO_EVIDENCE_REVIEW.md`](./GERCHIK_VIDEO_EVIDENCE_REVIEW.md) now catalogs confirmed official YouTube channel/video links, original Gerchik video-lesson pages, and timestamped Q&A recordings with crucial *questions* about **non-reaching bars, moving the level, pierced/floating zones, correct BSU/BPU geometry**. **The public titles/episode timestamps are verified; precise spoken answers and chart drawings were not independently transcribed.** The official course syllabus explicitly covers various types of D1 levels and multiple practical BSU/BPU lessons, so treating the **first swing-cluster RAW extremum** as the *only possible manually chosen Gerchik level* is presently unproven. **DO NOT loosen BPU1 equality or change production/code levels just because a title raises a question.** Require primary-video segment/annotated historical chart evidence.

**Next is chart-grounded methodological verification, not another identical June backtest.** Prioritise AON, DELL, CRM, ABT on original RAW D1/M5 charts using those video lessons, and record manual `YES/NO/INDETERMINATE` with actual source price/date, D1 level type, timestamped M5 geometry, and any explicit video timecode. Do not call 11 M5 range crossings real BPU1, 30s TVX, or profitable transactions.


## 2026-10-15 — QWCT 2.8 BUILT: original RAW BSU wick vs OHLC range vs D1 cluster (native pending)

**Purpose and normative basis:** Gerchik's published BSU/BPU description requires the first confirming bar (BPU1) to meet the origin bar's price precisely, with BPU2 immediately following BPU1; an OHLC candle merely spanning a price does **not** prove an exact high/low wick touch or the 30-seconds-preclose TVX. Normative public reference: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya (9 May 2024). This is **read-only geometry research**, not an attempt to silently relabel a range cross as a canonical BPU1.

**What code was added:**
- New small pure portable helper [`bsu_touch_audit.py`](./bsu_touch_audit.py), installed in the EXISTING Cloud project as `strategy/bsu_touch_audit.py`. Immutable D1 evidence attached to each approved morning-frozen case: original `first_idx` source date, original exact native RAW support low/resistance high, historical D1 swing **cluster median**, native tick, RAW/SCALED_RAW `MATCH` or `REBASED`, cluster-to-source difference expressed in ticks, and whether the **cluster itself lies on the price tick grid**.
- On **each ALREADY admitted native closed M5** in the existing no-orders after-close replay, an independent `TouchAudit.observe` classifies the RAW original high/low **without modifying `BsuDetector`**. Four **mutually exclusive** observations are counted per approved candidate/candle: `EXACT_WICK` (relevant high/low within the existing detector's half-native-tick equality tolerance), `SHORT_OF` (relevant extreme never reached original price), `RANGE_CROSSED` (extreme **overshot** but low≤original≤high; M5 OHLC alone cannot prove traded level quotes or order of intrabar events), `BEYOND_NO_SPAN` (entire candle is already on the other side; **does not by itself prove a market opening gap**).
- **Separately**, count `CLUSTER_RANGE` (M5 OHLC spans the D1 swing cluster median) and `CLUSTER_WICK_NEAR` (directional wick within half tick of that median). These do **not** count as original-pivot BPU1. Cluster median may fall between native executable ticks.
- `QWCT BSU AUDIT SUMMARY`: total frozen approved proxy cases vs observed, number of case-M5 observations, four mutually exclusive original-pivot groups, cluster observations, cases with original range crosses and cases with **cluster span but no original touch or crossing**. The aggregation unit is **candidate-level/M5 candle**, not individual trade ticks. `QWCT BSU AUDIT CASE` shows **up to 12** source–cluster comparisons prioritized for original-source crossings / cluster spans, closest signed tick gap/time, and first original range crossing time. Existing `QWCT COHORT SUMMARY` still confirms old screener/fundamental/basis/M1/M5 and **0 or actual canonical BPU1/BPU2** separately.
- Added focused pure unit tests [`tests/test_bsu_touch_audit.py`](../../tests/test_bsu_touch_audit.py): short and long original-extreme geometry, two-tick non-touch, within-half-tick equality, source-median discrepancies, four mutually exclusive categories, invalid inputs, and **a real `BsuDetector` object that still rejects an OHLC range crossing as BPU1**. Updated existing source-level integration guards and GitHub Cohort Pure Checks workflow. CI and this new native LEAN study are **not yet confirmed as executed**.

**Cloud steps (existing project, only 2 files):**
1. In `Qwct-M5-Cohort-Research`, **replace `main.py`** from [`research/cohort_cloud/main.py`](./main.py). Expect startup `QWCT 2.8 BSU AUDIT ACTIVE`.
2. **Add `strategy/bsu_touch_audit.py`** using full contents of [`research/cohort_cloud/bsu_touch_audit.py`](./bsu_touch_audit.py). Keep original seven helper files and `strategy/timing_gate.py` unchanged; folder now has **nine** files including root `main.py`. This is a true import: if new helper is missing or placed at the root, Python raises `No module named strategy.bsu_touch_audit`.
3. Run **June 1–30, 2024 once** with `timing_mode=next_session`, specifically to obtain geometry for the already native-tested **19 trading sessions, 17 original proxies and 1,326 M5 observations**. No need to change dates, selected universe, exact tick, risk gates or execute orders. These previous result counts are a **baseline, not guaranteed output for a future modified build**.
4. Return the complete `QWCT BSU AUDIT SUMMARY`, `QWCT BSU AUDIT CASE`, `QWCT COHORT SUMMARY`, `QWCT COHORT REJECTS` and any errors. If `range_crossed > 0`, they are **research geometries only** until independent visual D1/M5 BSU certification, actual first touch and next-bar BPU2 are verified. If `cluster_only_cases > 0`, investigate whether the historical **cluster median** is a reasonable Gerchik D1 level rather than silently substituting it for the original BSU pivot. No discretion-free canonical BSU proof exists yet.

**Manual D1 validation remains PENDING:** neither the prior 2.7 backtest nor this program can infer from reconstructed swing-clusters alone that a discretionary Gerchik-originated level is correct. The new output gives **ticker/day/original D1 source date/RAW pivot/cluster median/relevant M5 time** to cross-check manually against actual historical D1 and M5 charts. Until such labeled examples exist, do not declare 8 trade filters, profitability, or BSU/BPU/TVX solved. **No trading, orders, fills or synthetic price ticks**.


## 2026-10-15 — QWCT 2.7 VERIFIED: all five previously missed June sessions recovered natively

**Real QuantConnect LEAN Cloud run** `a2faf8b5c39541af3d10104c8dc610b9` on LEAN `v2.5.0.0.18184`, **2024-06-01 through 2024-06-30**, `timing=next_session`. Algorithm completed normally in 86.32 s, without orders. All **five** previously missed sessions passed native next-exchange-session timing: **June 3 ← June 1, June 10 ← June 8, June 17 ← June 15, June 20 ← holiday June 19, June 24 ← June 22**. Those actual previous Fundamental selection callbacks had **50 selected symbols each, native callback at 00:00 ET on the displayed date, and observed `Fundamental.EndTime` source min/max equal to that LEAN callback timestamp**. These observations establish LEAN as-of eligibility for the frozen previous callback, not independent external proof of fundamental filing/dissemination timestamps. **June 3 and 10 produced no Shadow proxies; they are covered zero-Shadow days rather than skipped days.**

| Measure | Previous June `strict` native run | June `next_session` native run | Difference |
| --- | ---: | ---: | ---: |
| Scheduled equity scans | 19 | 19 | 0 |
| Sessions with observed selection | **14** | **19** | **+5** |
| Native selection days from next valid exchange session | 0 | 5 | +5 |
| Candidate stock-days screened | 700 | 950 | +250 |
| RAW D1 ready | 699 | 949 | +250 |
| Stage2 pass | 633 | 861 | +228 |
| Shadow stock-days / READY original swing proxies | 12 / 12 | **17 / 17** | **+5 / +5** |
| RAW/SCALED_RAW MATCH | 6 | 7 | +1 |
| RAW/SCALED_RAW REBASED | 6 | 10 | +4 |
| Sessions with eligible after-close M1 replay | 8 | **11** | +3 |
| Original native M1 bars replayed | 4,521 | 6,411 | +1,890 |
| Native valid M5 candles (all with 16:00 final closes) | 936 | **1,326** | **+390** |
| Guarded native M5 close `Scan` successful | 12 | **17** | +5 |
| Strict BPU1 / closed BPU2 | **0 / 0** | **0 / 0** | 0 / 0 |
| Other source-data rejects | one `D1_INSUFFICIENT_CLOSED_RAW` | one same | unchanged |

**Closest M5 wick distances to original RAW BSU proxy pivots:** AON Jun 12 resistance **-2 ticks ($0.02) at 11:30**, newly included CAT Jun 24 resistance **-2 ticks ($0.02) at 11:30**, CRM Jun 27 resistance **-4 ticks ($0.04) at 09:35**; DELL Jun 7 support **+7 ticks ($0.07) at 14:50**. Here signed is `(extreme - original_pivot)/tick`: negative for high below resistance, positive for low above support. **Near-misses are not an exact-touch BPU1 and do not imply one.** AON and CAT closed-M5 highs did not reach their chosen original pivot on the recorded nearest bar.

**Status:** QWCT 2.7 is now **native runtime VERIFIED for calendar-source recovery**, and the June cohort is fully covered by a same-day or next-valid-session LEAN Fundamental selection. **The Gerchik strategy is still UNVERIFIED**: 17 algorithmic D1 swing-level proxies are not 17 independently certified manual BSU; no exact BPU1 or BPU2 appeared in 1,326 M5 observations; no SEC/TICK -30s TVX, eight combined signal gates, or trade P&L was proven. The single insufficient RAW D1 case is separately recorded and is not a BSU outcome.

**NEXT research, before extending the time period:** independently check what a canonical manual Gerchik BSU/BPU1 touch means with actual labeled D1/M5 chart examples; compare original *source swing extreme* vs D1 *cluster median*, exact wick extreme vs intrabar range crossing, and whether market data crossed the level without its extremum equaling it. Count those separately as **read-only disjoint diagnostic categories**, never automatically promote range crossings to BPU1, change detector tick tolerance or report simulated orders/fills. The current preserved source baseline is the June 2.7 native run ID above. Subsequent multi-month sampling should only begin once this evidence question is answered. **No June rerun needed merely to reconfirm callback timing.**


## 2026-10-15 — QWCT 2.7 built: native-calendar Fundamental callback A/B, native LEAN proof PENDING

**Problem:** The fully closed June 2024 baseline run `b6ec6049eff86d7f021293eca42410c3` covered **14/19 scheduled equity sessions** with strict same-calendar-day Fundamental callbacks. June **3, 10, 17, 20, 24** were skipped, even though the native LEAN Fundamental selection can deliver Friday data on Saturday and preholiday data on a closed market date. Trading-day eligibility for the callback has not previously been proved. All 12 observed price-level proxy cases produced 936 genuine native M5 bars and zero exact BPU1/BPU2. No legitimate signal may be invented by changing that rule.

**What is NOW implemented, without changing any strategy or detector source:**
- **New module** [`research/cohort_cloud/timing_gate.py`](./timing_gate.py) (copy to the new Cloud file `strategy/timing_gate.py`). This pure, fail-closed filter accepts only a **REAL previous Fundamental callback**, retaining its original selected symbol list, actual selection `at` timestamp and **ALL 50 source `Fundamental.EndTime`** values. It rejects missing source ends, future source data, callbacks more than five days old, repeated/ambiguous callbacks, callbacks occurring on a trading date, and dates that are not **the next real regular stock-market open**.
- Exchange dates are **not hard-coded**: the algorithm calls LEAN's native `self.securities[self.anchor].exchange.hours.is_date_open` and `get_next_market_open` (regular session only). The chosen source must already exist **BEFORE 09:29 ET**, and that session's actual exchange open must be **09:30 ET the same calendar day**. No arbitrary prior selection, historical reconstruction, lookahead or inferred Fundamental stock membership.
- [`research/cohort_cloud/main.py`](./main.py) introduces the optional user parameter `timing_mode = next_session | strict`. The **current default is `next_session`** for the new A/B research. `strict` reproduces the old same-calendar-day rule. If there is a genuine SAME-DAY callback (even an explicitly EMPTY result), it ALWAYS takes precedence in either mode; an empty same-day result may NOT be replaced by an older non-trading callback. Missing coverage is still logged as **SKIP**, never a zero-candidate day.
- Only the source of **morning candidate membership** changes for uncovered sessions. Original `classify_snapshot`, D1 Stage2, D1 Shadow Top10, raw-origin validation, SCALED_RAW comparison, original RAW pivot, native M1→M5 consolidation with previously LEAN-verified five-real-minute close `Scan()`, `BsuDetector`, exact BPU1/BPU2, split quarantine and no-order policy remain unchanged.
**Additional diagnostic:** QWCT 2.7 also emits compact `QWCT TIMING EVENT` entries when a real native callback occurs on a closed market date, recording all selected-source `EndTime` extrema and completeness. Its `QWCT COHORT NEAREST` records now include a **signed** tick distance and exact M5 time. The signed gap distinguishes the price remaining short of the old BSU pivot from the wick actually passing through it without forming an exact BPU1 wick extreme. These are descriptive observations, not relaxed BPU rules.

**CI attempt:** added [`QWCT Cohort Pure Checks`](../../.github/workflows/qwct-cohort-pure-checks.yml) GitHub Actions workflow (pytest on the existing research-only M5 tests), triggered by research/test-code changes and available manually. **Actual GitHub CI run state and native QuantConnect runtime remain unverified**. The pure calendar smoke fixtures passed locally but intentionally did not exercise the native LEAN Python.NET bridge.

- New logs include **`QWCT TIMING VERIFIED`** (date, original callback time, min/max selected source EndTimes and number of members), `timing=<strict|next_session>` in startup, `strict_days` / `next_days` in `QWCT COHORT SUMMARY`, and reasons `NO_VERIFIED_NEXT_SESSION` / `AMBIGUOUS_NEXT_SESSION_CALLBACKS` if needed. Previously completed final-bar tail diagnostic was removed from daily logging to keep main.py under **32KB**, but verified `close_scanned` remains in the summary.
- **Pure fixture checks:** recorded Saturday→Monday and holiday→Thursday, rejected stale/future/ambiguous callbacks and late-after-open use; **7 isolated smoke assertions passed locally** with a fake exchange calendar. These do **NOT** confirm native LEAN source EndTime or calendar marshaling. Full project CI remains unverified.

**QWCT 2.7 Cloud action — existing project, 2 file changes only:**
1. In the EXISTING `Qwct-M5-Cohort-Research` Cloud project, **replace only `main.py`** from [updated `research/cohort_cloud/main.py`](./main.py).
2. **Create one new file `strategy/timing_gate.py`** and copy the entirety of [`research/cohort_cloud/timing_gate.py`](./timing_gate.py). Keep all seven previous files otherwise unchanged.
3. Run **the SAME June 1–30, 2024** dates, necessary for the timing A/B comparison; set project parameter `timing_mode=next_session` (or omit if unset). Verify startup log `timing=next_session`. Saved parameters `scan_start`, `scan_end`, `timing_mode` override defaults.
4. Send **ALL** `QWCT TIMING VERIFIED` rows, `QWCT COHORT SUMMARY`, `QWCT COHORT REJECTS` and any BPU1/BPU2 logs. First gate: whether 5 historically skipped dates pass the actual native calendar and source cutoff. Do **not** assume `days=19`, all callbacks are populated, or positive BPU1. If a skipped day stays skipped, the sources determine whether it should.

**A/B reference (previous independently observed strict June):** `scans=19 days=14 stock_days=700 d1_ready=699 stage2=633 shadow_days=12 ready_origins=12 m5=936 close_scanned=12 bpu1=0 bpu2=0` with 5 missing-session skips. The same-time strict path remains available as `timing_mode=strict`; no claim that the new mode has been native backtested.

**Future priorities after genuine native 2.7 proof:** independent month-by-month cohorts with exact BSU/BPU rules unchanged, explainable 8 strategy filters, manually labeled true D1 BSU sources, genuine SEC/TICK -30s TVX, and only then portfolio execution/risk acceptance. Current QWCT state is **research only, zero proven strategy signals or fills**.

**Official LEAN APIs:** https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours and https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes .


## 2026-10-15 — NATIVE VALIDATION SUCCESS: guarded LEAN Scan recovers all 12 real closing M5 bars

**LEAN Cloud run `b6ec6049eff86d7f021293eca42410c3`, June 1–30 2024, LEAN 2.5.0.0.18184.** User ran the patched `research/cohort_cloud/main.py`. The previously missing **15:55–16:00 native M5 bar is now emitted for all 12 eligible symbol-days**, with **real, existing M1 history**, no artificial TradeBar and no new orders. Direct native evidence: `m1=4521 m5=936 m1_tail_close=12 m1_tail_early=0 m5_tail_close=12 m5_tail_early=0 close_scanned=12`. All four printed `QWCT COHORT TAIL` examples report `m5_last=16:00`. Old run without Scan had `m5=924 m5_tail_close=0`. Thus **+12/12 real close M5 candles**, no changed selection or price thresholds.

**Unchanged D1/Universe comparison to original June:** `scans=19 callbacks=20 weekend_callbacks=5 days=14 stock_days=700 d1_ready=699 stage2=633 shadow_days=12 raw_origin_pass=12 origin_unknown=0 origin_fail=0 basis_match=6 basis_rebased=6 ready_origins=12 replay_days=8`. **Five sessions excluded due to no same-calendar-day Fundamental callback: June 3, 10, 17, 20, 24**. One separate `D1_INSUFFICIENT_CLOSED_RAW`. Do **not** call the month fully covered or those five days 0 qualified names.

**Validated observed M5 outcome:** `bpu1=0 strict_bpu1=0 bpu2=0 strict_bpu2=0 strict_window=0 invalid=0`. Nearest original RAW pivots remained **AON June 12 short 2 ticks, CRM June 27 short 4 ticks, DELL June 7 long 7 ticks, ABT June 7 short 7.5 ticks**; these are not exact BPU1 touches. Native Scan correction did **not** produce a spurious signal or change those closest recorded examples.

**Important nuance:** The ABT June 7 diagnostic reports **389 M1 bars but 78 emitted M5**; 78 period-end timestamps demonstrate all 78 time buckets exist, **not** 390/390 original minute observations for that symbol. Native 5-minute consolidator can emit a bucket with fewer than five observed minute bars. The final five minutes were separately checked for completeness before the close Scan. If any future success depends on exact intrabar trade coverage in an M5 bucket, treat minute gaps explicitly instead of claiming every bucket complete.

**Next priority is NOT rerunning June or reducing the BPU1 tick tolerance.** Preserve this native pass as baseline; next do separately labeled, causally verified **Saturday/holiday Fundamental callback → next tradeable session** mapping so June 3/10/17/20/24 can be analyzed without hindsight. Compare with existing strict-same-day baseline **A/B**, confirm source data ends before 09:29, prevent stale selections and double counting. Only then broaden independent monthly cohorts with the same fixed BSU/BPU exact-touch rules. Manual Gerchik BSU qualification, actual -30s TVX, and profits remain unverified.


## 2026-10-15 — Native JUNE 2024 diagnosis: last M5 bar confirmed missing, targeted native LEAN fix committed

**Actual independent June native LEAN 2.5.0.0.18184 run `ef9602676ddeeb2f65902cca6edaee72` (2024-06-01..2024-06-30):**
`scans=19 callbacks=20 weekend_callbacks=5 days=14 stock_days=700 d1_ready=699 stage2=633 shadow_days=12 raw_origin_pass=12 origin_unknown=0 origin_fail=0 basis_match=6 basis_rebased=6 ready_origins=12 replay_days=8 m1=4521 m5=924 m1_tail_close=12 m1_tail_early=0 m5_tail_close=0 m5_tail_early=12 bpu1=0 strict_bpu1=0 bpu2=0 strict_bpu2=0 strict_window=0 invalid=0`. Five missed SAME-DAY Fundamental sessions: **June 3, 10, 17, 20, 24** (June 20 follows a market holiday, not a Monday). Plus one D1 insufficient-data rejection.

**The M5 loss is no longer speculative.** In **all 12** eligible symbol-days, the last historical native M1 bar was timestamped **16:00**, but the last emitted native TradeBarConsolidator M5 bar was timestamped **15:55** (77 five-minute bars per symbol-day, 924 total). Representative actual `TAIL` rows: META Jun4 and Jun5 both `m1=390 m5=77 m1_last=16:00 m5_last=15:55`; DELL Jun7 `390/77`; ABT Jun7 `389/77`. This is exactly consistent with LEAN **period consolidator emission only at the NEXT input timestamp unless explicitly Scan()ned at interval end**. QuantConnect's own `PeriodCountConsolidatorBase.Scan(DateTime)` method emits a pending period bar when the end time has passed; `TradeBarConsolidator` derives from it. Primary LEAN C# implementation: https://github.com/QuantConnect/Lean/blob/master/Common/Data/Consolidators/PeriodCountConsolidatorBase.cs .

**New focused patch, NOT native-tested yet:** The updated [`research/cohort_cloud/main.py`](./main.py) calls **the existing native** `TradeBarConsolidator.scan(last_native_minute.end_time)` *once at the observed session close*, **only when the five original native minute TradeBars covering the final five-minute period are present, consecutive, have positive volume, and are not fill-forward**. It requires the native emitted candle to have exactly the expected start/end. It does **not** create a TradeBar, extend history into the future, or modify prices, exact BPU1/BPU2 rules, BSU levels, or any other scripts. Missing a real closing minute yields `M1_CLOSE_FIVE_NOT_COMPLETE` and no inferred candle; failures to native-emit yield `M5_CLOSE_NOT_EMITTED`. A successful release increments `close_scanned` and `m5_tail_close` in `QWCT COHORT SUMMARY`.

**June observed nearest ORIGINAL pivot distances among 77 known M5 candles per case:** AON Jun12 short **2 ticks ($0.02)**; CRM Jun27 short **4 ticks ($0.04)**; DELL Jun7 long **7 ticks ($0.07)**; ABT Jun7 short **7.5 ticks ($0.075)**. None is a strict exact BPU1 in the 924 native-emitted candles. **A half-cent distance is not an exact one-cent grid touch.** The final-bar gap prevents any "zero BPU1 for complete June session" claim until the new patch is native-verified.

**Immediate experiment: replace ONLY existing Cloud cohort `main.py` with updated linked GitHub source.** No need to recreate the seven-file project. Keep **June 1–30, 2024**, or clear saved scan parameters so code defaults apply. Run **one fresh native backtest** specifically to validate the missing last candle. Compare unchanged `scans/stock_days/shadow_days/ready_origins` with baseline and check **`QWCT COHORT TAIL m5_last=16:00`**, summary `close_scanned`, `m5_tail_close`, total `m5`, and any actual additional BPU1/BPU2. Validated M5 might increase by **at most 12** (to **936** for this 12-case June cohort) *if* all 12 native last-five-minute segments are complete; do **not** guarantee this, since some symbols have missing intraday minutes. If there are errors, send full log before further code changes. **Saturday/Fundamental missing-session issue is separate and remains uncorrected.**


## 2026-10-15 — Real native May 2024 result: no exact BPU1, incomplete coverage to investigate

**Native QuantConnect LEAN 2.5.0.0.18184 backtest `e30da5e09d7fc0b9507871f63f7536c7` completed, May 1–31 2024.** This is the first genuine QWCT 2.6 run, superseding the original "native pending" status in the setup instructions below.

| Observed result | Count |
| --- | ---: |
| Scheduled market-day scans | 22 |
| Fundamental selection callbacks | 22, including 4 weekends |
| Sessions with same-calendar-day Fundamental selection | 18 |
| **Four sessions skipped for missing same-day callback** | **May 6, 13, 20, 28** |
| Fundamental top50 stock-days examined | 900 |
| Native RAW D1-ready / Stage2 pass | 900 / 813 |
| Shadow qualified stock-days | 13 |
| Origin provenance PASS / UNKNOWN / FAIL | 13 / 0 / 0 |
| Native RAW/SCALED origins | 8 MATCH / 5 REBASED |
| Ready BSU **proxies** | 13 |
| Sessions with eligible after-close minute replay | 10 |
| Native M1 TradeBars | 5,000 |
| Validated emitted native M5 bars | 1,001 |
| Closed-M5 BPU1 strict / BPU2 confirmed | **0 / 0** |
| Rejected events | four missed-callback sessions; no other logged reject reasons |
| Executed trades / TVX fills | 0 / NOT TESTED |

**Nearest observed native M5 extrema relative to original RAW pivots (tick=$0.01 for these cases):** **ADBE May 3 short ≈2 ticks ($0.02)** and **FTNT May 8 short ≈2 ticks ($0.02)** were nearest. Neither exactly touched the pivot as required. Next was JNJ May 2, 8 ticks ($0.08), then JNJ May 14, 21 ticks ($0.21). A two-tick miss is **NOT an exact touch**, even if that seems close visually. These are **minimum absolute distances in the checked closed M5 extrema**, not verified tick-by-tick prices or entries.

**Coverage warning — do not mislabel this as a full-month negative result:** every one of the 13 ready cases had exactly **77 validated M5 candles** (`13 × 77 = 1,001`). An uninterrupted regular US equity session normally contains **78 complete five-minute periods** from 09:30 through 16:00. The gap is suspicious and may be explained by the final 15:55–16:00 candle not being emitted by manual `TradeBarConsolidator` replay at an exact-close History boundary; missing last-minute input is another possible explanation. **This is a hypothesis, not yet proved by timestamp evidence.** The backtest's 5,000 M1 bars versus a hypothetical 13×390=5,070 also warrants checking actual closed minute coverage, but missing minutes may reflect real market data availability. Therefore the hard result is **zero observed BPU1 in the available 1,001 validated M5 bars**, not zero possible BPU1 throughout all 13 complete sessions.

**Data-universe coverage warning:** 4 of 22 intended scans were **skipped**, not screened with zero qualified tickers. The Saturday Fundamental callbacks are real, but this experiment still keys selection by the callback's same calendar day. Coverage is only **18 of 22 market sessions**, not a complete 22-day universe. Do not silently infer Monday candidates or retest those days using hindsight.

**Targeted research instrumentation now added to GitHub only:** `research/cohort_cloud/main.py` retains identical Fundamental/D1 origin/basis/Shadow/BPU1/BPU2 logic, but now includes `QWCT COHORT TAIL` for up to four actual symbol-days and summary counts `m1_tail_close`, `m1_tail_early`, `m5_tail_close`, `m5_tail_early`. They print true last native minute and true emitted native M5 timestamps vs exchange close — **without manually flushing, manufacturing missing bars, or relaxing any pattern rule**. This modified code is **NOT what produced the real May run**; these additional tail metrics are **native unverified** until a new backtest.

**Next bounded action:** do **not** rerun the unchanged six April cases or claim "BPU detector broken". Current updated code defaults to **June 2024**: check M1/M5 tail provenance first in that next independent monthly run, so positive/negative signal counts carry valid coverage. Then separately design an explicit, causally safe weekend-callback→Monday effective-session policy if improving coverage is required. Do not fit a two-tick tolerance or use the cluster median as an exact BSU. Manual Gerchik BSU validation and actual -30s SEC/TICK TVX remain separate later gates.


**Status:** One real May 2024 native QuantConnect 2.6 run completed; see evidence above. Later tail-diagnostic code revision is not yet native-tested. No trading orders, SEC/TICK data, backtested fills, or claimed profitability.

## Purpose: broader point-in-time evidence, without changing the trading rules

Previous real native QWCT 2.5 six-case fixed-cohort run `b6c0a9982e638d3f5fd1aa0e56a1f84e` observed **6/6 D1 BSU proxies READY, 468 validated M5 bars, BPU1=0/BPU2=0** over six stock-days in April 2024. The initial six symbol-day test has finished; repeating it unchanged is not a useful next step.

New QWCT 2.6 is a **different, independent, continuously-selected Fundamental/D1 Shadow cohort for all 2024 May trading dates**, up to 50 native Fundamental candidates/day, legacy stage2 filter, and max 10 **D1 role-aligned Shadow** stocks/day. It **does not cherry-pick tickers after seeing future M5 candles** or infer signals from price proximity. Exact BPU1 native-tick and immediate BPU2 rules of the existing `strategy.patterns_bsu.BsuDetector` remain unchanged.

**Ready-solution review:** We reused the actual, previously native-verified QWCT 2.4 functions `d1_shadow_shortlist`, `classify_snapshot`, `origin_d1_audit` and `compare_raw_scaled` **unchanged** (copied from `research/universe_cloud/main.py`). Reused canonical `strategy/__init__.py` Cloud selector, `strategy.levels`, native `AverageTrueRange` / `SimpleMovingAverage`, `BsuDetector`, `validate_m5_tradebar`, and LEAN native `TradeBarConsolidator(timedelta(minutes=5))`. No new indicator, separate broker, homemade candle generator or execution engine.

## Original QWCT 2.6 installation — seven original files, now PLUS one timing gate for QWCT 2.7

Project: **`Qwct-M5-Cohort-Research`**. Do not modify or replace `Qwct-LEAN-Test`, `Qwct-BSU-Research`, `Qwct-Universe-Research`, or `Qwct-M5-SixCase-Research`.

| Cloud file | GitHub main file to copy |
|---|---|
| `main.py` | [`research/cohort_cloud/main.py`](./main.py) |
| `strategy/__init__.py` | [`research/universe_cloud/strategy_init_cloud.py`](../universe_cloud/strategy_init_cloud.py) **(copy contents, rename to `__init__.py`)** |
| `strategy/config.py` | [`strategy/config.py`](../../strategy/config.py) |
| `strategy/indicators.py` | [`strategy/indicators.py`](../../strategy/indicators.py) |
| `strategy/levels.py` | [`strategy/levels.py`](../../strategy/levels.py) |
| `strategy/patterns_bsu.py` | [`strategy/patterns_bsu.py`](../../strategy/patterns_bsu.py) |
| `strategy/native_m5_validation.py` | [`strategy/native_m5_validation.py`](../../strategy/native_m5_validation.py) |
| `strategy/timing_gate.py` **(NEW in 2.7)** | [`research/cohort_cloud/timing_gate.py`](./timing_gate.py) |
| `strategy/bsu_touch_audit.py` **(NEW in 2.8)** | [`research/cohort_cloud/bsu_touch_audit.py`](./bsu_touch_audit.py) |

**IMPORTANT:** The bundled Universe selector `strategy_init_cloud.py` **is NOT the nearly empty `strategy_init_cloud.py` from the six-case project.** Use precisely the link above. It provides canonical `select_liquid_fundamentals` and `passes_gerchik_screener`.

**Current defaults in updated `main.py`:** `scan_start = 2024-06-01`, `scan_end = 2024-06-30` (new independent month; earlier May run already completed). Custom date span allowed only up to **35 calendar days** per run. **Saved QuantConnect project parameters OVERRIDE these defaults** — remove/update any saved May dates. Expect `QWCT 2.6 COHORT ACTIVE 2024-06-01..2024-06-30`. Do **not** rerun unchanged April or May evidence.

## Timing and data validity — do not confuse replay with real-time trading

- **Selection happens by 09:29 ET** from actual same-day native Fundamental callback, up to **50** candidates. A real native Fundamental Saturday callback is **not silently reinterpreted** as a Monday selection; Monday can be explicitly marked `QWCT COHORT SKIP ... NO_SAME_DAY_CALLBACK`. This is **missing coverage**, not a negative BPU result or proof of no qualified stocks. `weekend_callbacks` count is included.
- One batched, closed, as-of **RAW D1** 180-bar history request for selected 50; same legacy stage2 and original `d1_shadow_shortlist` only. No current session D1 is allowed.
- Up to 10 **Shadow** stock candidates get a second batched native `SCALED_RAW` D1 request, verifying original SOURCE high/low, latest closed RAW/SCALED prices, native tick-grid applicability and native D1 bar-end timestamp consistency. Historical `REBASED` pivots are explicitly labeled and may be observed using the **original RAW** source if newest RAW/SCALED close agrees; historical transformation is NEVER substituted into a RAW M5 level. `MATCH` and `REBASED` are evidence classes, not manually certified BSU approvals. Off-native-grid RAW origins remain disallowed. All other failures are rejected with counted reason.
- **Only at the actual exchange close, including the final backtest day and early-close dates**, make one *additional* **bounded 09:30 → real close** batched `History[TradeBar]` RAW **M1** request for **the already frozen and qualified Shadow symbols only**. It does not subscribe to 50 minute streams, use future minutes in the morning, or model live entries. Native `TradeBarConsolidator(5min)` aggregates **real historical minute TradeBars** into completed native M5; `validate_m5_tradebar` rejects fill-forward/zero-volume/invalid-period candles. A split on a studied day quarantines its affected symbol.
- Reuse existing `BsuDetector.on_bar(ClosedBar(...))`, with exact original historical RAW swing pivot and native tick, preserving `BPU1` strict tick-touch and immediately following `BPU2`, wick breach, 20%-luft stop-distance rule, and 12:00–13:30 bounce-session window. Do not "round" WMT or lower BPU tolerance to inflate positives. A positive M5 BPU2 is an **algorithmic closed-candle proxy**, not automatically a manually valid Gerchik setup or a valid -30s TVX observation.
- Algorithm prints `QWCT COHORT SUMMARY` (callbacks/scans/covered days/D1 origin/basis/M1/M5/BPU1/BPU2/strict/window/invalidated), `QWCT COHORT REJECTS`, `QWCT COHORT COVERAGE`, nearest 10 original pivots (`QWCT COHORT NEAREST`), and up to 12 `QWCT COHORT BPU1/BPU2` examples. Output is compact for QuantConnect Free logging limits; no orders or synthetic fills.

**Why at the market close rather than +1 minute?** QuantConnect may skip after-market-close +1 minute scheduled events on the **final backtest date**. Zero-minute actual close is supported. The retrospective historical request ends at the *actual* current LEAN time, so early market closes also cannot include future data. Source: https://www.quantconnect.com/forum/discussion/13602/everyday-event-doesn-039-t-get-triggered-the-last-day-after-16-00-00/ .

## Backtest, expected proof, and decision gate

1. Create the new **7-file project**; run the **May 1–31, 2024** native QuantConnect Cloud Backtest once.
2. Return complete logs with `QWCT 2.6 COHORT ACTIVE`, `QWCT COHORT SUMMARY`, `QWCT COHORT REJECTS`, `QWCT COHORT COVERAGE`, `QWCT COHORT NEAREST`, and any `BPU1/BPU2` examples. A `M5_CONSOLIDATOR` or `MINUTE_HISTORY` error means **NOT** tested, not "zero signals."
3. If still **zero BPU1/BPU2**, report that outcome without relaxing exact-touch or fitting thresholds to the test. Next hypothesis is valid frozen-level **forward follow-up with separately proven expiry/invalidations**, or more independent monthly windows, not fabricated BPU.
4. If any real strict M5 BPU2 is found, independently label the source as Gerchik BSU from its actual D1 geometry before considering separate SEC/TICK retrospective -30s TVX proof. **No order execution or P&L until trading evidence and validations are complete.**

Official docs: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes ; https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests ; https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators .
