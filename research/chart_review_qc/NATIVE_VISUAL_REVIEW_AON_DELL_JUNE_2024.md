# QWCT 2.9 — User's real QuantBook chart evidence: AON and DELL (2024-06)

**Evidence:** user-provided screenshots of **actual QuantConnect Research `QuantBook` notebook execution** (2026-10-15), showing printed RAW source checks, D1-as-of prior session chart and minute-derived closed M5 chart, first crossing table. Not downloaded external vendor bars. Provenance of the independently frozen cohort: LEAN Cloud run `4b787847b9e5d2405b2fd97a541fa71e`.

**Limitations:** These are screen-rendered technical plots, **not an expert Gerchik manual label**. The actual bar values in the screenshot are transcribed below for the first crossed candle and its immediate next candle. No unobserved D1 source details, intra-M5 trade path, 30-second TVX, broker orders or profitability can be inferred.

## Primary measured results

| Session / proposed side | Historical source + original RAW pivot | Grouped D1 median | Native RAW D1 source matches earlier run? | Native M1 tradebars / theoretical 390 | M5 time buckets | All five source M1 in M5 buckets | Exact original wick touches | Original source-level M5 **range crossings** | First range cross M5 close ET |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| AON 2024-06-12 / short | 2024-05-10 / **293.5900** | **293.8175** | **Yes** | **389 / 390** | 78 | **77/78** | **0** | **2** | **09:35** |
| DELL 2024-06-07 / long | 2024-05-14 / **128.7500** | **128.6750** | **Yes** | **390 / 390** | 78 | **78/78** | **0** | **7** | **14:15** |

The actual prior Cohort 2.8 run and the notebook agree exactly on two original source prices, these source dates are simply historical **May 2024** D1 extrema. Both exact original-pivot wick touches remain zero; range crossings are OHLC observations only. **AON caveat:** older notebook printed `FULL 78 M5: True` even though only 77 of 78 5-minute bins contain five native minute tradebars; its previous validator checked only the **final** bin, not all bins. This misleading status is now corrected in the updated [single-cell notebook source](./BSU_D1_M5_ONE_CELL.py). It **does not prove a feed outage**; one minute may simply have no traded bars when `fill_forward=False`. The missing minute bucket's ET timestamp is NOT visible in the supplied screenshot; don't guess it or assert first source crossing was affected. AON strict completeness is **PENDING / false**, DELL strict completeness **PASS**.

## Direct chart/OHLC interpretation — first crossed bar ONLY

**AON Jun12 first source crossing (M5 closed 09:35 ET):**

| M5 close ET | Open | High | Low | Close | Actual M1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 09:35 | **293.920** | **293.920** | **292.340** | **292.400** | 5 |
| 09:40 | 292.745 | 293.460 | 292.370 | 292.370 | 5 |
| 09:45 | 292.350 | 292.630 | 292.320 | 292.555 | 5 |

Relative to original RAW 293.5900, **09:35 open was ABOVE** and **09:35 close BELOW**; the 09:35 candle **traversed the level downward**, with relevant `high=293.920` **not equal** to original 293.5900. This is an **opening range penetration/downward break**, not a certified exact-*wick* BPU1 `short` bounce off resistance. The immediately next 09:40 bar also closed below and its high **293.460 < 293.590**, failing exact BPU1. A later distinct range crossing is observed in the 2-case aggregate but its OHLC was not printed in this screenshot, so don't make claims about its detailed pattern. Neither 09:35 nor 09:40 authorizes a trade.

**DELL Jun7 first source crossing (M5 closed 14:15 ET):**

| M5 close ET | Open | High | Low | Close | Actual M1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 14:10 | 130.120 | 130.270 | 130.020 | 130.170 | 5 |
| 14:15 | **130.225** | **130.225** | **128.520** | **128.520** | 5 |
| 14:20 | 128.530 | 129.260 | 128.250 | 128.670 | 5 |
| 14:25 | 128.675 | 129.090 | 128.360 | 128.700 | 5 |

Relative to RAW support **128.750**, the 14:15 candle opened **ABOVE** and closed **BELOW** the level, with actual `low=128.520` **not equal** to 128.750. The next 14:20 bar's low `128.250` broke even farther below. This is a **support penetration/downward break in the first crossed candle**, not a demonstrated exact `long` BPU1 or immediately successful BPU2. Subsequent M5 crosses and the plotted broader path may warrant separate false-break/retest study, but **the count of 7 range crosses is not 7 BPU1 events** and mirror-type D1 validity is not demonstrated by these price crossings.

## Reviewer label (what evidence currently justifies)

| Label field | AON | DELL |
| --- | --- | --- |
| Original RAW source price/date reproduced | **MATCH** | **MATCH** |
| Original-source *exact* BPU1 wick observed anywhere in 78 M5 bars | **NO** | **NO** |
| First raw-source crossing is a clean exact-BPU1 bounce | **NO** | **NO** |
| Gerchik-approved D1 BSU fixed level (independent manual teaching examples) | **INDETERMINATE** | **INDETERMINATE** |
| Algorithmic mirror provenance and `mirror.valid_from` on this day | **UNTESTED** | **UNTESTED** |
| SEC/TICK -30s TVX observation | **UNVERIFIED** | **UNVERIFIED** |
| Source M1 coverage complete for all 78 buckets | **NO: 77/78** | **YES: 78/78** |

### Next precise decision

**Do not edit BPU1 tick equality, misclassify those range crosses, or rerun the full June2.8 backtest.** The first-cross screenshot already demonstrates why two candidate stock-days had no exact-BPU1 count even though original RAW prices were crossed.

To close the source-label question, the *remaining* missing research is genuine chart markup against an actual Gerchik D1 example with full author source context, and separately running the notebook's independent **mirror-as-of inventory**; **neither** has been established by the submitted two charts. AON's one missing 1m candle calls for a tagged partial minute coverage diagnostic only, not retroactive fabrication of absent data.

**Current conclusion:** QWCT 2.8 geometry classification appears directionally consistent with the two visible M5 first crossing OHLC records; automatic `swing_cluster.first_idx` provenance is not yet author-certified, and original exact-wick `BpuDetector` should remain unchanged. AON/DELL screenshots do not prove any live/tradable setup.
