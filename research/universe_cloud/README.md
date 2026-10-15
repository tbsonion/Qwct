# Qwct Universe D1 Research — a new, separate QuantConnect LEAN Cloud project

## 2026-10-15 — Native Apr 8–19 confirms Saturday callback explains the missed Monday scan

**REAL QuantConnect LEAN v2.5.0.0.18179 run `b150a7c028111580f879cc75e2512b0d`** ran the correct **2024-04-08..2024-04-19** window. Ten intended exchange sessions generated **nine actually scanned sessions**, with the tenth being **Monday 2024-04-15, unobserved**. This is a calendar-keying problem, *not evidence that April 15 had zero qualified stocks*. Metrics **reproduced the previous same-window run**: 450 Fundamental stock-days, 446 usable D1, 412 stage2, 14 Shadow D1-qualified stock-days, 11 original level fingerprints, 3 legacy Top10 overlaps, 11 Shadow observations outside Top10. This is NOT 14 BSU/BPU setups or trades.

**New evidence identifying the mechanism:**
- `2024-04-12 00:00` Fundamental callback: sample window Apr11..Apr12 (normal Friday selection).
- **`2024-04-13 00:00` (SATURDAY)**: a real `QWCT UNIVERSE TIMING SELECT` callback picked **50 stocks** from **Friday Apr12 00:00..Saturday Apr13 00:00** underlying source data.
- **`2024-04-15 09:29` (MONDAY)**: `NO_CALLBACK_BEFORE_SCAN`, because no new callback on Monday. `_screen` stores callbacks as `screen_by_day[et(self.time).date()]`, so Friday-close data selected Saturday was stored under **Apr13**; `_prepare` exclusively looks up **Apr15**. Thus the existing strict same-calendar-day research scan skipped Monday.
- `TIMING SUMMARY scans=10 selection_callbacks=10 selection_days=10 missed_scan_days=['2024-04-15'] late_callbacks=0`: **10 callbacks include the Saturday callback, not 10 weekday callbacks.**
- QuantConnect staff documentation explains that daily US Equity universe data can be delivered **after the trading session** and that a **Friday** session's callback can run **Saturday**. Sources: https://www.quantconnect.com/forum/discussion/918/feature-coarse-universe-selection/p2 and https://www.quantconnect.com/forum/discussion/2727/bug-or-intended-universe-selection-doesn-039-t-occur-until-one-trading-day-has-passed/ . Consequently, there is **no evidence of a missing underlying Friday data set** or a late Monday callback. The precise weekend delivery timing is runtime behavior, not a user strategy parameter.
- **Safety boundary:** The weekend-selected list is a real point-in-time pre-Monday snapshot, but it has NOT been treated as Monday's **same-day** selection, and the historical Apr15 Shadow/BPU candidate count is **unknown**. Before adopting a next-exchange-session effective-date policy in the canonical strategy, independently prove timestamp freshness and any position/universe side effects. **Do not silently fill Monday from Friday/Saturday selections or rewrite the original Top10.**

**RAW-origin result:** `raw_only_pass=13 fail=1 unknown=0`, 14 *symbol-day observations* / 11 distinct original level fingerprints. The single failure is the **same recurring WMT March 12 RAW pivot 61.565** (Apr11 observation), compared with current native tick metadata 0.01. The other 13 are only RAW D1 swing/grid/chronology checks; **SCALED_RAW, corporate-action factor reconciliation and manual Gerchik BSU validity remain unverified**. All 9 originally measured sessions, 14 Shadow rows and prior counts remain unchanged.

**Next engineering priority (do NOT leap to M5):** a bounded, read-only, native `SCALED_RAW` comparison for the **existing actual Shadow RAW pivot dates**, latest as-of D1 close, timestamps, and native tick metadata. Reuse `strategy/bsu_bridge.py` methodology rather than change the BsuDetector or Stage1/2. A targeted single batched extra D1 History call for observed Shadow symbols is preferable to a new subscription or an unbounded market-wide search. The WMT half-cent source is UNKNOWN for historical executable tick provenance; never auto-round it. After that, decide whether a *separately labeled research* effective-next-session replay of Apr15 using the **recorded real Saturday selection** is warranted; **do not silently alter baseline counters**.

**Action now:** No Cloud change or repeat backtest necessary for this Apr15 timing diagnosis. Original `Qwct-LEAN-Test` and `Qwct-BSU-Research` remain untouched.


## 2026-10-15 — Second native compact-log run completed; April 15 STILL not measured

User's latest real LEAN 2.5.0.0.18179 backtest `2e5f65fc65c3467e0534a794b8a6e3f8` ran **Apr 1–5, 2024 again**. Compact logging works and finishes without the earlier QuantConnect Free 10KB truncation. It reproduces 5 scans/5 native selection callbacks, 250 candidates, 246 ready RAW D1, 227 stage2 PASS, 9 Shadow stock-days (7 original level fingerprints), and **RAW origin 8 PASS / 1 FAIL (WMT original RAW 61.565 off observed 0.01 tick)**. **It does NOT investigate the April 15, 2024 missing Fundamental callback.** No M5 or orders were run.

**Operational fix:** The isolated research Cloud-ready `main.py` now defaults to **`2024-04-08` through `2024-04-19`** when project parameters `scan_start` and `scan_end` are absent/empty. This changes **only fallback test dates**; all D1 logic, selection, subscriptions and order prohibitions stay intact. If the QuantConnect project already defines `scan_start`/`scan_end`, those settings override fallback dates and **must be updated in the Cloud Project panel**. Before trusting any rerun, verify opening log says `QWCT UNIVERSE RESEARCH ACTIVE 2024-04-08..2024-04-19`.

**Next:** Replace only [Cloud `Qwct-Universe-Research/main.py`](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py), check the start/end parameters (if present), keep `verbose_logs` unset/off, and inspect `QWCT UNIVERSE TIMING SELECT/SCAN/SUMMARY` for Apr 15 together with `QWCT ORIGIN SUMMARY/DETAIL`. Still research-only; no M5/SEC/orders, and no conclusion about profitability.

## 2026-10-15 — REAL Cloud RAW origin smoke: 2024-04-01..05 (8 PASS / 1 FAIL), compact logging now ready

Native LEAN **v2.5.0.0.18179** completed run **`e52e0c836a0cd349d078dc64775f82bd`** for **2024-04-01..2024-04-05**, *NOT the requested April 8–19 missing-date investigation*. One Fundamental selection callback at midnight and same-day selection at 09:29 ET on each of the five sessions: `scans=5`, `selection_callbacks=5`, `missed_scan_days=[]`. April 15 is therefore **STILL UNTESTED** in this run.

Existing baseline results reproduced **exactly**: 250 candidate-stock-days; 246 RAW D1 ready; 227 stage2 passed; 9 Shadow symbol-days across 7 unique level-origin fingerprints; legacy Top10 overlap 0; zero orders.

New `QWCT ORIGIN SUMMARY`: **8 RAW-only PASS, 1 FAIL, 0 UNKNOWN**, covering nine *symbol-days*, **not nine different origins**. Six of the seven distinct original swing sources passed this read-only RAW/tick/chronology audit; the single failed origin was **WMT, Apr 2**, resistance-cluster `61.6075`, **actual first RAW D1 swing high `61.565` on Mar 12, 2024**, minimum tick metadata `0.01`, reason `RAW_ORIGIN_OFF_NATIVE_TICK_GRID` (0.005 gap to nearest $0.01 grid). **DO NOT ROUND OR ARM WMT BSU**. Walmart's 3:1 split began split-adjusted trading on Feb 26, 2024, *before this March 12 swing*; split alone is therefore **not an established explanation**. The other observed RAW-only origin prices: UNH `496.61` (Apr 1 and Apr 2), MCD `286.08`, MMM `94.82`, PG `160.10` (Apr 2 and Apr 3), ABBV `175.39`, MA `464.64`.

These are **RAW-only algorithmic swing checks**, not independent SCALED_RAW comparisons, verified corporate-action price-basis reconcilations, manual Gerchik BSUs, M5 BPU setups or trades. Even eight PASS observations **prove no profitability**.

The actual log hit **QuantConnect Free's 10KB per-backtest cap** after its second legacy OUTSIDE10 row. To prevent the April 8–19 10-session run from truncating critical ORIGIN evidence, the **latest GitHub** `research/universe_cloud/main.py` now defaults to **compact logging**. It retains per-callback TIMING SELECT, missed-scan TIMING SCAN, SHADOW DAY, TIMING/ORIGIN/UNIVERSE/SHADOW/FULL50 summaries and capped ORIGIN DETAIL. Verbose routine scan success and legacy UNIVERSE DAY / SHADOW PICK / OUTSIDE10 / EXAMPLE rows require optional **`verbose_logs=1`**, which is **NOT recommended on Free**. This adjustment affects *only logging*, not selection, history, indicators, rules or orders. New GitHub revision **not yet tested in native Cloud**.

**NEXT single Cloud step:** In **Qwct-Universe-Research**, replace **only** [`main.py`](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py); set `scan_start=2024-04-08`, `scan_end=2024-04-19`, leave `verbose_logs` absent (or not `1`). Inspect `QWCT UNIVERSE TIMING` Apr 15 and `QWCT ORIGIN SUMMARY/DETAIL`. Keep both older Cloud projects untouched. No M5/SEC/orders yet.


## 2026-10-15 — NEXT Cloud run: RAW-only origin + April 15 timing diagnostics (GitHub implemented; native run PENDING)

**Scope:** Replace **ONLY** [Qwct-Universe-Research Cloud `main.py`](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py). Keep the other four research Cloud files unchanged, and never edit `Qwct-LEAN-Test` or `Qwct-BSU-Research`. This is **read-only D1 research**, not native-verified until the next backtest.

**Period:** first rerun **2024-04-08..2024-04-19** (expected 10 sessions; previous actual 9). Then, for independent confirmation of the 9 initial candidates, rerun **2024-04-01..2024-04-05** if needed. Change only the existing `scan_start`/`scan_end` Cloud parameters between runs.

**New compact logs:**
- `QWCT UNIVERSE TIMING SELECT` reports each actual Fundamental callback clock and example native data timestamps. `QWCT UNIVERSE TIMING SCAN` distinguishes **NO_CALLBACK_BEFORE_SCAN**, **EMPTY_SELECTION**, **SAME_DAY_SELECTION_READY** at the scheduled 09:29 ET scan. An actual callback after a missed scan is marked **after_missed_scan=True** but **never retroactively analyzed**. `TIMING SUMMARY` reports missing dates and callback counts. Sample data timestamp is observational, not proof of dataset correctness.
- `QWCT ORIGIN DETAIL` reports each Shadow level's **existing** `first_idx` RAW D1 high/low, original cluster median, `formed_at` (last swing source), last swing confirmation, `valid_from`, LEAN `symbol_properties.minimum_price_variation`, and **PASS/FAIL/UNKNOWN** with reason; up to 30 details are logged. `QWCT ORIGIN SUMMARY` counts results across all scanned Shadow levels (at most 3 per stock-day).
- `PASS` verifies **only** algorithmic D1 source chronology and RAW origin on the *currently observed* minimum-tick grid, inside the original cluster tolerance. It **does not** certify historical split-adjustment provenance, equivalence to `SCALED_RAW`, a discretionary Gerchik BSU, BPU1/BPU2 or profitability. `FAIL`/ `UNKNOWN` entries are never silently rounded into BSU; a historical native tick-size change could require independent evidence before treating `FAIL` as a definitive feed error.

**Reuse and safety:** No new subscriptions, M5/SEC/RAW history requests, or orders were added. The existing SINGLE batched `History[TradeBar]` RAW D1 request, canonical D1 levels, stage2 filters, liquidity ordering, legacy Top10 and Shadow selection are unchanged. The previous run's April 15 is **unobserved**, not zero matches; logging can distinguish no callback, empty selection and late selection, but cannot infer the reason for a truly absent callback.

**Acceptance:** GitHub unit tests are mock/logic tests **only**. Provide a native LEAN log with `QWCT UNIVERSE TIMING`, `QWCT ORIGIN SUMMARY`, `QWCT ORIGIN DETAIL`, `QWCT SHADOW SUMMARY`, `QWCT UNIVERSE SUMMARY`; compare earlier counts to detect unintended deviations. Do not proceed to M5 or alter rules until these actual outputs have been reviewed.


## NEW independent-period native result: Apr 8–19, 2024 — 9 of 10 trading days covered

**QuantConnect LEAN v2.5.0.0.18179 backtest `37850a5ba8ff6f8cc5383afd21d030ca`**, dated 2024-04-08..2024-04-19, successfully completed **WITHOUT M5, SEC, or orders**. It is a **different time window** from the original Apr 1–5 experiment and uses **unchanged** same-stage D1 filters and original liquidity ranking. **Important integrity exception:** it expected **10 US equity sessions**, but `days=9`, with **2024-04-15 missing** from day logs and `rejects['missing_same_day_universe']=1`. This is a fail-closed missing-native-Universe day; do **not** treat Apr 15 as zero matches, silently fill from a prior day's universe, extrapolate to ten sessions, or claim exhaustive validation.

| Cohort / metric | Native observed value (9 covered days) |
|---|---:|
| Historical liquidity Top50 membership | **450 candidate-stock-days**, 50 per observed session |
| D1 histories ready | **446**, four insufficient RAW D1 history |
| Canonical stage2 passed | **412** |
| Legacy liquidity Top10 | **90** symbol-days |
| Legacy Top10 with D1 confirmed near level | **25** |
| Legacy Top10 with D1 source-role+native trend match | **3** (one each TSLA Apr 10, AAPL Apr 16, META Apr 18) |
| Full Top50 source-role+trend | **14** candidate-symbol-days |
| D1-first Shadow Top10 | **14**, 11 distinct tickers and 11 distinct source fingerprints |
| Shadow intersection with legacy Top10 | **3** |
| Shadow outside legacy Top10 | **11** |
| Shadow has at least one match | **8 of 9 observed sessions** (Apr 17 zero; Apr 15 unobserved) |

The per-session Shadow counts for observed days Apr 8/9/10/11/12/16/17/18/19 were **1,1,2,4,1,2,0,2,1**. Unlike the original development period Apr 1–5 (9 candidates / 7 tickers, **zero** within legacy Top10), this independent window includes **three** legacy-aligned candidates, but an additional **eleven** D1-only rows appear by filtering the same Top50 **before** the Top10 cutoff. The sample supports a consistent **coverage gain at the D1-precondition stage**, not any claim of better returns, M5 BPU1/BPU2, preclose TVX, fills, or profitability. The original count of 10 sessions must **not** be used as denominator until the Apr 15 universe gap is investigated.

**All 14 native Shadow stock-days, with original Fundamental liquidity rank:** Apr 8 JNJ #40; Apr 9 JNJ #38; Apr 10 TSLA #2 and JNJ #42; Apr 11 INTC #18, WMT #41, TXN #42, CRM #46; Apr 12 CRM #44; Apr 16 AAPL #3 and AMAT #50; Apr 17 none; Apr 18 META #8 and MCD #49; Apr 19 NFLX #12. JNJ repeated three times and CRM twice; that is **11 distinct tickers**, **not 14 independent BSU trade setups**.

**Additional safety caveat from real evidence:** Several native D1 `shadow_level` cluster centroids are fractional-tick-looking prices (e.g. **INTC $37.2025, WMT $61.6075, TXN $167.325, CRM $294.315, NFLX $602.785**). Do not feed these averages directly to native exact-touch M5 BSU detection. The raw original swing high/low, `first_idx`, native security tick size, source dates, normalization/corporate actions need validation first. The existing Qwct `strategy/bsu_bridge.py` documents these fail-closed requirements. **Apr15 universe callback timing/data reason is unverified**: inspect missing-day logs and recorded selection timestamps; do not silently carry forward members or loosen any filters.

**NEXT engineering task:** (a) add a **read-only `missing_same_day_universe` day/date diagnostic** to the isolated research `main.py` and verify if Apr15 selection was absent or late, without changing membership timing; (b) add a **native-RAW D1 origin/tick-size research audit** of shadow candidates using the same already retrieved D1 bar objects, no M5 or order insertion, without pretending RAW-only proof equals split-adjusted proof; (c) once safe, use native M5 only on source-verified candidates. A single cohesive source change and one Cloud retest is preferable to several blind reruns. **None of these new diagnostics has been implemented or native tested yet.** The current code is unchanged and the independent-window results have been recorded as source evidence.

**Cloud action now: NONE — existing `Qwct-Universe-Research` runs as-is.** Do not touch original `Qwct-LEAN-Test` or older `Qwct-BSU-Research`.  


## 2026-10-15: Native Shadow Top10 VERIFIED — nine D1-only rows / seven original-level origins

**Real native QuantConnect LEAN 2.5.0.0.18179 run `925f9cad95176a12269bae8b9f8f030d`**, 2024-04-01..2024-04-05, **completed 31.53 s with no orders**. Shadow comparison added to the existing `Qwct-Universe-Research` project, all prior Top10 and full50 counters unchanged:

| Cohort | 5-session symbol-days | Unique tickers | Notes |
|---|---:|---:|---|
| Original liquidity-only Top10 | 50 | not separately reported | 10 per day; 0 with source-role+trend D1 combination |
| Full Top50, original stage2 qualified | 227 | not separately reported | 246 historical D1 rows valid of 250 stage1, four insufficient |
| Near a confirmed two-touch D1 level in full50 | 42 | 24 | Within original 1xATR proximity |
| D1 source-role AND global/local SMA trend aligned in full50 | **9** | **7** | D1-only premarket candidates, *not* patterns or trades |
| **New filtered-first Shadow Top10** | **9** | **7** | Same results as full50; per-day cap 10 never reached |
| Overlap with original liquidity-only Top10 | **0** | — | All 9 would be omitted by current liquidity-first top10 |

**Exact day-by-day real Shadow selections (liquidity ranks are ORIGINAL daily Fundamental ranks):**

| Session 2024 | Candidate/rank | Source swing-cluster D1 level and hypothetical side | Provenance `valid_from` / `formed_at` |
|---|---|---|---|
| Apr 1 | UNH #21 | resistance **496.125**, SHORT, 3 touches, strength 4 | Mar 27 / Mar 21 |
| Apr 1 | MCD #49 | resistance **285.60**, SHORT, 3 touches, strength 3 | Mar 27 / Mar 21 |
| Apr 2 | UNH #21 | same resistance 496.125, SHORT | Mar 27 / Mar 21 |
| Apr 2 | MMM #26 | resistance **94.94**, SHORT, 2 touches, strength 2 | Feb 16 / Feb 12 |
| Apr 2 | PG #46 | support **159.915**, LONG, 2 touches, strength 2 | Mar 29 / Mar 25 |
| Apr 2 | WMT #50 | resistance **61.6075**, SHORT, 2 touches, strength 2 | Mar 27 / Mar 21 |
| Apr 3 | PG #48 | same support 159.915, LONG | Mar 29 / Mar 25 |
| Apr 4 | ABBV #40 | support **175.56**, LONG, 2 touches, strength 2 | Mar 26 / Mar 20 |
| Apr 5 | **MA #47** | support **464.74**, LONG, 2 touches, strength 2 | Mar 15 / Mar 11 |

`QWCT SHADOW DAY` counts were **2,4,1,1,1** (five non-empty days); summary: `shadow_symbol_days=9`, `unique_shadow_tickers=7`, `unique_shadow_level_origins=7`, `legacy_overlap_symbol_days=0`. **The ninth MA candidate is now fully identified**; previous `OUTSIDE10` diagnostic omitted it only because examples were capped at eight. UNH and PG are repeated *same-level* across dates, not separate origins. No market orders, M5, preclose SEC, trades or P&L.

### What is established / what is still missing

The test **establishes a premarket Top10 liquidity-rank coverage bottleneck**, because filtering within the already fetched historical Top50 by the original D1 preconditions would preserve all nine D1-only symbol-days in this specific five-day period, without exceeding 10. **It does not establish** positive edge, a completed Gerchik setup, native exact BPU1, next-bar BPU2, exact -30-second TVX, target/room or executable entry. These nine were selected by a shadow policy invented for research and then reproduced on the **same development window**; wider independent windows are still required before policy acceptance.

**Critical next validation before native M5:** `shadow_levels` values are **D1 cluster centroids**, not guaranteed **RAW native source pivots or exchange tick-grid prices**. Examples include `UNH 496.125`, `PG 159.915` and `WMT 61.6075`. A half-cent/quarter-cent cluster cannot be silently used as an exact-touch BSU trade price; the original `bsu_bridge.py` requires the historical origin extreme, native tick-size, verified RAW-vs-SCALED_RAW provenance and source timestamps, separately. A genuine native M5 BSU detector **must** use a verified RAW origin, not the cluster median. Corporate actions/splits and missing as-of factors must fail closed. No rule relaxation is justified by the nine premarket cases.

**Recommended next controlled research:** freeze this five-day set; then verify **RAW D1 first swing source / tick grid / date, valid-from and corporate-action provenance for these seven original cluster origins**, then run **read-only native M5 BPU1/BPU2** only on a validated point-in-time Shadow shortlist. Do not mix retrospective OHLC M5 with genuinely event-driven -30s TVX or infer fills. In parallel, test the unchanged shadow policy on an **independent date window** (e.g. 2024-04-08..2024-04-19) rather than optimizing repeatedly on the exact same five days. The default 5-day scan parameters remain unchanged; the current native Cloud version need not be reinstalled.

**Cloud action: NONE.** This last shadow `main.py` is native-verified. No change to `Qwct-LEAN-Test`, `Qwct-BSU-Research`, or the four supporting research Cloud files.


## 2026-10-15: NEXT EXPERIMENT IMPLEMENTED — D1-aware shadow Top10 (native run pending)

**Purpose:** the real native full50 run `5497a648495b409e7cea19ff98f21d85` on 2024-04-01..05 found **9 D1-only source-role+trend-qualified symbol-days from 7 distinct tickers among the top50**, but **all 9 were outside the original liquidity-first Top10**. This is evidence of a watchlist **coverage bottleneck** during this five-day sample, *not* evidence that any BSU/BPU/TVX trading signal or profit was missed.

**HISTORICAL Cloud instruction, completed successfully by native run `925f9cad...`:** the shadow experiment previously required replacing only [research/universe_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) in existing `Qwct-Universe-Research`. Do **not** change `Qwct-LEAN-Test` or `Qwct-BSU-Research`. The new shadow stage subsequently **ran in native LEAN successfully** (see current verified result at top), in addition to the preceding **369 GitHub tests**.

The added **`d1_shadow_shortlist(passed, max_results)`** uses the **same point-in-time daily Fundamental Top50**, **same one already proven batch of RAW native D1 TradeBars** and **already calculated** unmodified price / ATR / average share-volume stage2, confirmed historical minimum 2-touch D1 cluster, morning `valid_from`, <=1 native D1 ATR proximity, sided native SMA global+local trend, and strict **source support+long or resistance+short** evidence. **No re-ranking by pattern "strength" or historical returns.** It filters first and takes at most the original `cfg.screener_watchlist_limit=10` in existing highest-liquidity order (`rank`, then symbol). **If only 2 meet the D1-only criteria, shadow contains 2: it NEVER pads empty slots with unqualified names.**

**Crucial:** the **original** `watchlist=passed[:10]`, the actual QuantConnect **50-member Fundamental Universe** and all existing `QWCT UNIVERSE` Top10 / FULL50 logs remain **unchanged**. The shadow is only an extra Python list and printed report; it does **not** create a new LEAN Universe, add subscriptions, request additional History/M5/SEC, change canonical scenario/model/BSU semantics, turn on orders, or measure financial outcomes. The original D1 qualification uses RAW normalization, not guaranteed split-equivalent to primary Qwct's SCALED_RAW warmup. This is only a research candidate-list policy comparison.

**New native logs expected (counts are deliberately NOT assumed until real Cloud verifies them):**

- `QWCT SHADOW DAY YYYY-MM-DD legacy=N shadow=N overlap=N outside_legacy=N rank_tickers=SYMBOL:ORIGINAL_LIQUIDITY_RANK,...` — original Top10 vs filtered-before-top10 independent candidate list, per day.
- `QWCT SHADOW SUMMARY cap=10 days=5 nonempty_days=... shadow_symbol_days=... legacy_overlap_symbol_days=... outside_legacy_symbol_days=... unique_shadow_tickers=... unique_shadow_level_origins=... pick_rows_logged=...` — distinct tickers and source fingerprints kept separate from stock-days; **neither is number of completed trading signals**.
- `QWCT SHADOW PICK DATE SYMBOL liquidity_rank=N shadow_rank=N qualified_levels=N evidence=[(price, source_kind, direction, touches, strength, valid_from, formed_at), ...]` — up to **25** printed stock-day cases, up to **3** levels per case, with explicit total count; no unreported symbol should be inferred if log is truncated.
- Existing `QWCT UNIVERSE SUMMARY` and `QWCT UNIVERSE FULL50` should reproduce the last native counts **50/0 (legacy role aligned)** vs **227/9 (full50 stage2 / role aligned)**, subject to identical historical data.

**To review:** provide the final `QWCT UNIVERSE SUMMARY`, `QWCT UNIVERSE FULL50`, `QWCT SHADOW SUMMARY`, all `QWCT SHADOW DAY`, and available `QWCT SHADOW PICK` rows. The nine earlier D1-only cases are a **prediction for reproduction** in an unchanged historical simulation, *not yet measured by this new policy code*. Validate native history/cache behavior and the original 50-symbol cap before any future policy decision or event-driven M5 observer.


## LATEST ACTUAL LEAN — FULL50 confirms original Top10 liquidity cutoff masks D1 candidates

**Confirmed native LEAN 2.5.0.0.18179, run `5497a648495b409e7cea19ff98f21d85`, 2024-04-01..2024-04-05, finished 30.29 seconds, no orders.** This run tested exactly the **same as-of 50 liquidity-ranked stocks and historical D1/trend rules**, now counting *already screened* names outside Top10 without additional subscriptions or M5. The prior Top10 rows reproduced exactly.

| Stage / definition | Historical stock-day observations |
|---|---:|
| Fundamental Top50 membership | 250 across five days |
| Usable closed RAW D1 history | 246; 4 insufficient |
| Original Qwct stage2 price/ATR/volume pass | 227 |
| Original Top10 watchlist | 50 (=10 per day) |
| D1 two-touch source within 1×ATR (all stage2 pass names) | **42**, over **24 distinct tickers** |
| Close-relative Scenario side + SMA G/L match (full50) | **20** |
| Original native BSU support-long / resistance-short **AND** matching G/L, full50 | **9 symbol-days**, **7 distinct tickers** |
| Same BSU-role+trend preconditions inside original Top10 | **0** |
| Same BSU-role+trend preconditions **outside** original Top10 | **9**, all of them |

**Finding:** in this five-session sample, **100% (9/9) of D1-only role+trend-qualified stock-days were screened out by the fixed Top10 liquidity watchlist**. The original canonical D1 level/trend thresholds did not cause the *absence of all premarket D1 possibilities across Top50*. The Top10 cutoff was the decisive **coverage bottleneck at this screening stage in this sample**. This does **not** show Top10 is wrong in other periods, that D1-only candidates had M5 BPU1/BPU2, executable TVX, 4R/3R or any profitable trade.

**Eight of the nine symbol-days were printed** (log intentionally caps `QWCT UNIVERSE OUTSIDE10` at 8; do not invent the ninth): **UNH 4/1 + 4/2**, **MCD 4/1**, **MMM 4/2**, **PG 4/2 + 4/3**, **WMT 4/2**, **ABBV 4/4**. UNH and PG repeat across adjacent dates; *not* independent intraday signals. The ninth symbol-day and the seventh distinct symbol were not in the capped example lines. MCD and WMT display multiple nearby levels; their `role_aligned=1` is satisfied by the **resistance/short** level, not their logged **support/long** countertrend level.

**What to do next:** do **not** rerun these same five days solely to recount them, increase Top10 in the main trading algorithm, or relax D1/BPU rules. A **separate read-only shadow candidate selection** can now compare the existing fixed Top10 liquidity order with a *conditional, as-of, D1-qualified shortlist* from the same already fetched Top50. That prioritizes stocks with proven D1 provenance, nearby confirmed support-long or resistance-short and sided G/L trend while retaining a **10-stock cap and one historical data request**. Still **no M5, orders, TVX or trades** until that watchlist policy is specified and independently validated. Alternative: first reconcile D1 source labels and independently expert-annotated US-stock examples, then select an M5 cohort.

**HISTORICAL (before implementing shadow Top10):** the previous full50 report required no further Cloud updates; the NEW shadow version at top DOES require replacing only `main.py`. Existing `Qwct-BSU-Research` and `Qwct-LEAN-Test` untouched.


## 2026-10-15: REAL native BSU ROLE check complete — zero eligible in watchlist, next full50 check ready

Actual native **QuantConnect LEAN v2.5.0.0.18179 run `06f195f83e949fa1a1e65ca77885aed0`**, April 1–5 2024; 32.41s, no runtime errors or orders. **This confirms the previous role-audit code ran in genuine Cloud.** Prior funnel remained stable: stage1 **250 candidate-stock-days**, **246 D1 ready**, **227 stage2 passed**, **50 top-10 watchlist stock-days**, **3** near-level watchlist stock-days.

| Date, symbol | D1 close | Native historic cluster | Source role vs proposed bounce | SMA trend | Old Scenario direction aligned? | Native BSU source role + trend aligned? |
|---|---:|---|---|---|---|---|
| **2024-04-01 AMZN** | 180.3800 | **179.835 resistance, 2 touches** | `resistance` below close, Scenario suggests `long` | `+1/+1` | **YES** | **NO**: `BSU_ROLE_MISMATCH` |
| **2024-04-02 AMZN** | 180.9700 | **same 179.835 resistance** | same mismatch | `+1/+1` | **YES** | **NO**: `BSU_ROLE_MISMATCH` |
| **2024-04-05 AMD** | 165.8300 | **162.18 support, 2 touches** | `support` below close, Scenario suggests `long` | `0/0` (neutral) | **NO** | **NO**: source role consistent, **trend not aligned** |

**Native summary:** `watch_with_trend_aligned_bounce=2`, **`bsu_role_conflict_level_days=2`**, **`watch_with_bsu_role_aligned=0`**, **`bsu_role_aligned_level_days=0`**, `unique_bsu_role_aligned_tickers=0`. The two "aligned" hits are the **same AMZN level on two consecutive days**, not independent BSU signals. The Qwct two-touch D1 level, proposed bounce side, native `BsuDetector` source-side semantics and native SMA trend must not be conflated. No M5/BPU/TVX or profit is evaluated.

**Caveat:** zero in the top-10 watchlist for **five sessions** does **NOT** demonstrate zero D1 candidates elsewhere among the **177 stage2-qualified symbol-days excluded by top-10 capacity**, nor in other dates. Do NOT relax `allow_countertrend=False` or silently promote a resistance-below-price into confirmed `mirror/support`. The original Qwct `bsu_bridge.py` explicitly rejects an unverified `resistance+long` BSU link.

### NEXT minimum-cost controlled test — update ONLY main.py, same dates

A new GitHub version of [research/universe_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) preserves **all existing stock-selection rules and Top-10 outputs** and adds a **read-only full-50 vs top-10 diagnostic** using the **already fetched and classified** original 50 ticker candidates; there are **no extra History calls or extra subscriptions**.

Additional summary line `QWCT UNIVERSE FULL50` reports **stage2_symbol_days**, **near_symbol_days**, **scenario_aligned_symbol_days**, **bsu_role_aligned_symbol_days**, **outside10_near_symbol_days**, **outside10_bsu_role_aligned_symbol_days**, **unique_near_tickers**, **unique_bsu_role_aligned_tickers**. `QWCT UNIVERSE OUTSIDE10` logs only up to 8 concrete point-in-time D1 role+trend-aligned outside-10 ticker examples, if any; examples still **not M5 or actual trades**. The baseline summary should remain **identical** to run `06f195...` unless market data/research environment changes.

**HISTORICAL instruction, already COMPLETED in native Cloud run `5497a648...`:** The earlier full50 comparison required only `main.py` and the same five dates. Leave the other four Cloud files, `Qwct-BSU-Research`, and original `Qwct-LEAN-Test` unchanged. Paste **`QWCT UNIVERSE SUMMARY`**, **`QWCT UNIVERSE FULL50`**, and any **`QWCT UNIVERSE OUTSIDE10`** lines. Pure GitHub CI **365 tests passed**, but this new *full50 output* has **not** yet been confirmed in native Cloud.

**Next decision after that result:** If original role+trend D1 candidates exist outside top10, assess the existing screener capacity as a potential coverage bottleneck **without automatically expanding subscriptions**. If none exist, the small premarket period/sample or structural level/trend filters are the bottleneck; compare rules with independently labeled chart examples before modifying any canonical filter. Do not connect M5 to a zero-eligible day list.


## LATEST native LEAN 5-day outcome: dynamic screen CONFIRMED; BSU role mismatch next

**Actual QuantConnect LEAN v2.5.0.0.18179**, run `247db2a140c2ae2a6790fbee82ffb1a4`, April 1–5 2024, completed in 34.11s. Native typed `History[TradeBar]` with `list(symbols)` is **confirmed fixed in real Cloud**; the prior tuple overload problem is resolved. Orders off.

| Measurement | Real value | Proper interpretation |
|---|---:|---|
| Native Fundamental stage1 | 50 candidates × 5 sessions = **250 candidate-symbol-days** | Historical dynamic universe, not 250 separate tickers |
| Native D1 histories ready | **246 / 250** | Four rejected: `insufficient closed RAW D1` (historical factor/start-date warnings, no synthetic fallback) |
| Original Qwct stage2 pass | **227 / 246** | Candidate-symbol-day count across the full 50, not 227 independent setups |
| Original 10-stock watchlist | **50 symbol-days** | Up to 10 per day; not 50 unique tickers |
| Has a two-touch D1 level (any distance) | **50 / 50** | Such a level can be far away |
| Has D1 level within 1×ATR | **3 / 50** | **AMZN Apr 1**, **AMZN Apr 2**, **AMD Apr 5** |
| Close-relative Scenario bounce direction agrees with native SMA trend | **2 / 50** | **Same AMZN resistance 179.835 on TWO adjacent days**, **NOT two independent opportunities**, and still no BPU or model scoring |
| AMD 2024-04-05 | D1 near, trend neutral `G=0,L=0` | Not aligned |

**Important methodological issue in actual log:** the apparent two AMZN `trend_aligned` results are tagged **`resistance` at 179.835**, **below** prior-day closes **180.38** and **180.97**, and the earlier D1-only code calls the hypothetical bounce side `long` because it mirrors Qwct `ScenarioEvaluator` (position relative to close). But original independent `BsuDetector` maps **resistance → short** and **support → long**. A `resistance` below price may be a *role-reversal* hypothesis, but the existing `levels_for_session` had **not** labeled this level `mirror` (and D1 study expressly excludes confirmed mirrors). Therefore **those two counts cannot be presented as two candidate long BSU bounces without further source/role reconciliation**.

**NEXT code is already prepared — one-file diagnostic, no rule change:** [research/universe_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) still computes the exact **old** `watch_aligned` and `aligned_level_days`, and **adds** `BSU_ROLE_OK / BSU_ROLE_MISMATCH` to `EXAMPLE` rows. It additionally reports `watch_bsu_role_aligned`, `bsu_role_aligned_level_days`, `bsu_role_conflict_level_days`, **unique ticker** counts separately from ticker-day counts. `BSU_ROLE_OK` requires original `support+long` or `resistance+short` **and** the already required sided SMA alignment. `BSU_ROLE_MISMATCH` is a diagnostic, **not a new trade filter or rewritten canonical Qwct algorithm**.

**Historical role-test instructions (already completed natively; superseded by new full50 read-only audit above):** In the same project, the role-test code was loaded from [GitHub](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py), leave the other four files and other QuantConnect projects unchanged, rerun **2024-04-01..2024-04-05**. Paste `QWCT UNIVERSE SUMMARY` and `QWCT UNIVERSE EXAMPLE` (DAY lines optional). **This additional read-only role branch has passed pure GitHub tests but has not yet been verified in native Cloud**. Avoid adding M5 until we know whether there are any role-consistent premarket D1 candidates. The 4 insufficient-history rejections remain legitimate unknown data, not losing trades.


## 2026-10-15: REAL native LEAN first run — tuple-to-list typed History fix prepared

Actual LEAN Engine **v2.5.0.0.18179**, run `c9fdcf0711e0f00dd55768003c71ac2e`, 2024-04-01..2024-04-05, **successfully produced five daily Fundamental selections of 50 stocks each (250 candidate-days)**. However, `d1_ready=0`, `stage2_pass=0`, `watchlist_days=0` because **ALL FIVE** native batched D1 `History[TradeBar]` calls raised `No method matches given arguments for history: (<class 'tuple'>, ...)`. Thus **ZERO watchlist counts are a HISTORY OVERLOAD ERROR, NOT evidence that no historical stocks qualified**. No trades/orders were submitted.

**Root cause shown in source:** the project stored original top-50 picks as `tuple(selected)` and subsequently passed that Python **tuple** into LEAN's *typed* `self.history[TradeBar](symbols, 180, Resolution.DAILY, ...)`. The earlier successfully verified BSU project passes a **Python list** of Symbols (`[symbol]`) to the same typed API. LEAN overload binding rejected the tuple, before any D1 values could be examined.

**Minimal targeted patch committed:** the standalone [research/universe_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) now calls `self.history[TradeBar](list(symbols), 180, Resolution.DAILY, ...)`. Retains original selected *membership*, Fundamental ranking, 50/10 constraints, unchanged screener/levels/trend, RAW histories, date window, and **no orders**. New regression checks verify typed-history receives an actual list, not a tuple; **now native Cloud-verified by run 247db2a140c2ae2a6790fbee82ffb1a4 (see top)**.

**Historical instructions for the already verified tuple fix (superseded by the role-audit rerun above):** Previously the only Cloud change was `main.py`. Keep `strategy/__init__.py`, `strategy/config.py`, `strategy/indicators.py`, `strategy/levels.py` exactly as they are. Run Save → Build → Backtest with SAME April 1–5, 2024 dates. Paste `QWCT UNIVERSE DAY`, `QWCT UNIVERSE SUMMARY`, and any `QWCT UNIVERSE EXAMPLE`. If errors remain, examine the exact LEAN log rather than loosening screening gates or introducing an alternate API.


**Purpose:** Test how much wider dynamic universe screening increases the number of **original Qwct-compliant premarket D1 level + sided-trend opportunities**, without selecting retrospectively hand-picked mega caps or weakening any thresholds. **RESEARCH ONLY / ALL ORDERS DISABLED**. This does NOT search M5 BSU/BPU, place quotes, confirm TVX, simulate fills or calculate P&L.

## Ready-to-copy complete 5-file Cloud setup

In QuantConnect create a **new Python Algorithm** project named `Qwct-Universe-Research`. The existing `Qwct-BSU-Research` and original `Qwct-LEAN-Test` remain untouched. Create/reuse an actual `strategy/` folder for the following files (do NOT paste all source into one huge main.py).

| QuantConnect project path | Use exact GitHub source | Action |
|---|---|---|
| `main.py` | [Cloud main.py](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/main.py) | Replace starter file |
| `strategy/__init__.py` | [Cloud-ready package init](https://github.com/tbsonion/Qwct/blob/main/research/universe_cloud/strategy_init_cloud.py) | Create as **`strategy/__init__.py`**, not `strategy_init_cloud.py` |
| `strategy/config.py` | [Existing canonical config](https://github.com/tbsonion/Qwct/blob/main/strategy/config.py) | Add |
| `strategy/indicators.py` | [Existing canonical indicators](https://github.com/tbsonion/Qwct/blob/main/strategy/indicators.py) | Add |
| `strategy/levels.py` | [Existing canonical levels](https://github.com/tbsonion/Qwct/blob/main/strategy/levels.py) | Add |

`strategy/screener.py` **is NOT a sixth Cloud file**: its **unchanged original canonical functions** are already bundled inside the Cloud-ready `strategy/__init__.py`, matching the tested main Qwct Free-packager's reuse pattern. The repository's canonical `strategy/__init__.py` is **not identical** to this Cloud-ready file; **do not use the tiny upstream original for this project** or it will fail to import the screener. No additional imported `strategy/` modules are needed.

### Controlled smoke test

- Defaults **2024-04-01 through 2024-04-05**, **five US trading days**. QuantConnect parameter `scan_start` / `scan_end` if explicitly set will override defaults. Hard-coded `<=14 calendar days` horizon prevents expensive accidental sweeps in the Free instance.
- Read-only native LEAN **Fundamental Universe** using Qwct's **unchanged** `select_liquid_fundamentals(fundamentals, cfg)`: price >$5, positive daily volume/fundamental data, highest native historical dollar volume, at most **50**. It records the historical selected ticker list by algorithm-local day; no survivorship-biased modern static symbol list.
- At **09:29 ET** each equity session, fetch ONE batched native **RAW D1 History[TradeBar]** for that day's actual selected symbols and exclude bars of the current or future session. Recompute **native LEAN ATR(14), SMA(50), volume-SMA(20)** from those D1 TradeBar objects as-of last closed market day, **not** custom indicator math. Missing or inconsistent history does not pass screening.
- Stage 2 calls the unchanged original `passes_gerchik_screener` using the native D1 close, ATR and 20-day average share volume, then takes the top **10** by original 50-candidate liquidity rank.
- For those actual 10-or-fewer watchlist symbols, call original Qwct `levels_for_session` with true historical D1 swing confirmation, minimum 2 touches, strength, mirror exclusion, and source-valid-from. Find original levels no farther than 1×ATR from yesterday's close. Derive bounce direction exactly as in canonical `ScenarioEvaluator` relative to the prior daily close; `global_trend` and `trend_direction` must BOTH match that direction under unchanged original `allow_countertrend=False`. The tool logs **how many symbol-days** meet these **D1-only** conditions, **not** completed BPU or profitable trades.
- Fundamental universe selection and D1 checks intentionally happen on the same historical trading day. Do **not** treat the final universe membership table as investable if an event or a future bar appears: `missing_same_day_universe` or `same-day/future or invalid D1` must be diagnosed first.
- **Different price basis caveat:** This diagnostic intentionally uses RAW D1. The primary Qwct warmup uses SCALED_RAW indicator history; around corporate events they may diverge. Before promoting findings into the main system compare normalization and as-of split handling.
- The script does not import original `Qwct-LEAN-Test/main.py`, register a broker, subscribe to M5/second data, place orders, or alter prior BSU data. The engine's **five-day screen** is a ***measurement of opportunity coverage***, not a fully validated Gerchik backtest.

### Expected initial native Cloud logs

```text
QWCT UNIVERSE RESEARCH ACTIVE 2024-04-01..2024-04-05 ... NO ORDERS
QWCT UNIVERSE DAY 2024-04-01 candidates=... d1_qualified=... watchlist=... watch_near=... watch_aligned=...; NO M5 / NO ORDERS
...
QWCT UNIVERSE SUMMARY days=... candidate_days=... d1_ready=... stage2_pass=... watchlist_days=... watch_with_two_touch=... watch_with_near_level=... watch_with_trend_aligned_bounce=... unique_aligned_symbol_days=... rejects=...; NO M5 / NO SEC / NO ORDERS
QWCT UNIVERSE EXAMPLE ... (only examples with near D1 levels, up to 16)
```

**Important:** This is a **new research branch and is not yet native QuantConnect-verified**. GitHub CI tests prove standalone Python syntax, original gate reuse and no order method references, **not** that the Cloud Fundamental Universe callbacks/data quotas execute successfully. If the Cloud returns `missing_same_day_universe`, `native_history_error`, Python import failures, backtest timeout or insufficient data, submit exact logs and adjust the research-only harness, not canonical filters.

## Why this comes after the prior failed candidates

The previous **three** native PPHL-only strict+time events were **countertrend under the current Qwct two-SMA mandatory rule** and not original Qwct two-touch levels. Instead of weakening two separate gates to force those three cases into apparent trading signals, this research counts naturally occurring **point-in-time, canonical D1+trend-eligible** ticker-days across a broader universe. Whether any actual BPU1/BPU2/TVX triggers is a separate subsequent experiment.

Primary materials and remaining unverified expert labels: [Gerchik rule/source audit](https://github.com/tbsonion/Qwct/blob/main/docs/research/gerchik_rules_ground_truth_20261015.md). Official LEAN documentation: [Fundamental Universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes), [Liquidity Universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/liquidity-universes).

## Audit safety

No trades, no portfolio or paper execution, no 30-second TVX, no claim of 3R/4R actually filled, no strategy rule change. Stop and review the Cloud native outcome before enlarging the date range or attaching M5.
