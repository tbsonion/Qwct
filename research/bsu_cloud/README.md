# Qwct-BSU-Research — separate empty QuantConnect Cloud Python project

**Status (2026-10-14): first native LEAN Cloud smoke successful** on 2024-03-16–2024-04-26 with real M5 data. It observed **8 BPU1**, **3 closed-M5 BPU2**, **5 invalid BPU2 attempts**, **416 candidate level-days** across MSFT/AMZN/AAPL and **0 orders**. This does not prove -30s TVX, profitability, or a fully validated Gerchik setup. The main trading project `Qwct-LEAN-Test` remains unchanged.

## What to do in the empty project

In the new **Qwct-BSU-Research** project, replace the default `main.py` and create the `strategy` folder with the following six **unchanged, canonical Qwct** modules (7 Python files total):

| Cloud path to create/replace | Ready-to-copy GitHub link | Why |
|---|---|---|
| `main.py` | [research/bsu_cloud/main.py](https://github.com/tbsonion/Qwct/blob/main/research/bsu_cloud/main.py) | New read-only LEAN orchestrator |
| `strategy/__init__.py` | [strategy/__init__.py](https://github.com/tbsonion/Qwct/blob/main/strategy/__init__.py) | Python package |
| `strategy/config.py` | [strategy/config.py](https://github.com/tbsonion/Qwct/blob/main/strategy/config.py) | Original frozen config |
| `strategy/indicators.py` | [strategy/indicators.py](https://github.com/tbsonion/Qwct/blob/main/strategy/indicators.py) | Native ATR series reader |
| `strategy/levels.py` | [strategy/levels.py](https://github.com/tbsonion/Qwct/blob/main/strategy/levels.py) | Same confirmed as-of D1 swing/cluster detector |
| `strategy/patterns_bsu.py` | [strategy/patterns_bsu.py](https://github.com/tbsonion/Qwct/blob/main/strategy/patterns_bsu.py) | **Same** exact-native-tick BPU1, immediate BPU2 and 20%-stop luft |
| `strategy/native_m5_validation.py` | [strategy/native_m5_validation.py](https://github.com/tbsonion/Qwct/blob/main/strategy/native_m5_validation.py) | Verify actual LEAN consolidated M5, timestamps and observed volume |

**Do not paste the old 24-file Cloud bundle into this new project**; it would run a different algorithm and consume unnecessary Free quota. New project uses only 7 files plus the editor's optional template `research.ipynb`.

For the current native PPHL A/B smoke test, default dates are back to **2024-03-16 through 2024-04-26**, with fixed MSFT/AMZN/AAPL. Cloud scan parameters override the defaults if set. Do not change Qwct-LEAN-Test.

## Latest native PPHL OHLC proof (Cloud run f06cb8adcd437c8d647d99f01ee5fd88)

Run succeeded on LEAN v2.5.0.0.18179, 2024-03-16..2024-04-26, same MSFT/AMZN/AAPL RAW D1 + native M5. The added independent evidence confirmed **3 distinct symbol+day+side+original RAW origin episodes** (not merely three repeated M5 passes), all **strict BPU1**, immediately following **closed-M5 BPU2**, within the current 12:00–13:30 ET bounce window. **It did not verify SEC preclose, D1 trend/strength/room, orders or returns.** Original Qwct baseline stayed 6 strict BPU1 / 1 strict-followed BPU2 / zero in-window.

| Symbol & session | Source pivot / confirmed (ET) | BSU | BPU1 close (ET) | BPU1 relevant extreme | BPU2 close (ET) | BPU2 relevant extreme | BPU2 stop / luft |
|---|---|---:|---|---:|---|---:|---|
| **AMZN 2024-03-21 short** | 2024-03-14 / 2024-03-19 | **179.53** | 13:10 | high **179.53** | **13:15** | high **179.50** | 180.41 / 0.176 |
| **AAPL 2024-04-03 long** | 2024-03-15 / 2024-03-20 | **170.28** | 12:15 | low **170.28** | **12:20** | low **170.345** | 169.46 / 0.164 |
| **AAPL 2024-04-12 long** | 2023-08-25 / 2023-08-30 | **175.82** | 12:20 | low **175.82** | **12:25** | low **175.83** | 175.02 / 0.160 |

These source dates precede the respective BPU1 by several days or months. The oldest AAPL source deserves additional manual D1 quality/relevance review rather than being assumed tradeable.

Off-grid: **87 pivot×day exclusion observations arise from only 3 unique original RAW daily pivots**: AMZN 2024-03-08 resistance 178.785, AAPL 2023-09-20 resistance 179.695, AAPL 2023-12-04 support 187.455, with reported native reference minimum tick 0.01. They are **not evidence of 87 independent bad bars** and are not silently rounded. Subpenny historical trade extrema can exist; investigate market-data basis before labeling defective.

**Next gate:** request **real historical one-second TradeBars** from the official LEAN History API for only the three confirmed patterns, reconstruct *retrospective* preclose trade-price extrema up to **30 seconds before BPU2 closes** with no fill-forward, and report an explicit **UNKNOWN / NO DATA** if no exact cutoff observation is available. This is *not* a simulated live timestamped order or execution, and no independent D1/model eligibility can yet be concluded. Do not connect trading code. Exact SEC access on Cloud Free still unverified.

## Native PPHL Cloud test: CONFIRMED / strict-and-window cases found

The user's actual QuantConnect **LEAN Engine v2.5.0.0.18179** log, **2024-03-16 through 2024-04-26**, run `c87716354f4706f73666bf18add82885`, confirms the first end-to-end **native PivotPointsHighLow(3,3,100)** A/B research run:

| Observed item | Count |
|---|---:|
| Qwct clustered level-days (unchanged baseline) | 416 |
| PPHL pivot level-days | 2,819 |
| Overlap (identical original RAW pivot/side/time) | 416 |
| PPHL-only level-days | 2,403 |
| Distinct PPHL-only pivot origins over run | 100 |
| PPHL-only native M5 checks | 187,434 |
| PPHL-only detector BPU1 / strict BPU1 | 28 / 22 |
| PPHL-only closed-M5 BPU2 / BPU2 after strict BPU1 | 8 / 6 |
| **PPHL-only strict BPU2 within 12:00–13:30 ET** | **3** |
| Original Qwct strict BPU1 / strict BPU2 after BPU1 | **6 / 1**, unchanged |
| Native PPHL **off-grid RAW origin rejections** | **87** (not Python binding failures) |
| Trading orders / actual -30s SEC TVX | **0 / not measured** |

**This is the first observation of research patterns passing strict BPU1 + M5-closed BPU2 + historical fixed time-window together.** They do **not** yet pass the rest of the original Qwct filters for a real trade (D1 strength, model choice, trend, available 4R/3R room, risk, SEC/tick preclose). The 2,403 PPHL-only level-days include repeated observations of historical single pivot sources; they are NOT 2,403 unique tradable opportunities. The 3 pattern events could share an origin/day. Their unique symbol-date-source count is not known from the first log.

**First named in-window observation**: AMZN **2024-03-21 BPU1 closed 13:10 ET → BPU2 closed 13:15 ET**, historical RAW PPHL resistance **179.53**, confirmed on **2024-03-19 16:00 ET**. This is a read-only event, NOT SEC 13:14:30 price confirmation. Other two time-window observations were hidden by the first five-event live log cap, not disproved.

**Data-quality distinction:** `pphl_errors={'off-grid native PPHL origin': 87}` reports refused original pivot prices that do not lie on the declared tick grid. It is a research exclusion counter, NOT fatal errors; native LEAN completed successfully, and the original Qwct `rejects={}` remains unchanged. The excluded prices' unique origin count and raw values must be reported before changing any tick rounding.

### Narrow next patch: evidence only, not more signal generation

**Update only standalone `Qwct-BSU-Research/main.py`** from the GitHub link in the table below. The new proof-only logging retains **all** strict PPHL BPU2 events in the current time window independently of the first-five live log cap. It reports:

- `BSU PPHL EVIDENCE`: total strict in-window M5-closed events, count of **unique `symbol + day + side + original RAW origin`** episodes, off-grid rejection count and count of unique excluded origins.
- `BSU PPHL WINDOW PROOF` and `BSU PPHL WINDOW OHLC`: each BPU1/BPU2 actual completed M5 pair, original BSU price/time, later confirmation time, strict price gap in native ticks, stop and luft. Limit 12 displayed pair details; omissions explicitly counted.
- `BSU PPHL OFFGRID`: up to three actual original RAW pivot examples that were excluded from native tick-grid equality **without rounding or feeding them to the detector**.

The new proof logging **does not alter** the PPHL candidate list, original detector, time window, D1 strategy gates, M5 bars, or order execution. The current evidence-log patch still needs a native Cloud backtest; source-level tests and the first native PPHL version are not proof of this updated version.

**Run:** keep **2024-03-16..2024-04-26**, replace ONLY standalone research `main.py`, then run `Save → Backtest` and share `BSU PPHL EVIDENCE`, all `BSU PPHL WINDOW PROOF/OHLC`, any `BSU PPHL OFFGRID`, plus `BSU PPHL COMPARE`, `BSU RESEARCH SUMMARY` and `BSU RESEARCH ELIGIBILITY`. This is the final short targeted proof step before deciding whether to use more symbols. Keep trading completely disabled.

## CURRENT Cloud task: native LEAN PPHL versus existing Qwct pivots (research-only)

**Update only the new research project's main.py:** [Cloud-ready research main.py](https://github.com/tbsonion/Qwct/blob/main/research/bsu_cloud/main.py). Defaults are **2024-03-16 to 2024-04-26** (a previously tested window, deliberately replayed for an A/B comparison). Leave the six strategy modules and Qwct-LEAN-Test untouched.

The new shadow uses LEAN's **actual PivotPointsHighLow(3,3,100)**, manually updated on sequential already-closed historical **RAW daily TradeBars** at 09:29 ET. Each native pivot event is recorded **only after the third right-hand daily bar has closed**, preserving both original D1 pivot price/time and the later confirmation time. It compares original RAW swing origins against the existing two-touch Qwct cluster-origin list. Only PPHL-only origins are separately observed on the same native, already validated M5 bars with the existing read-only BsuDetector. A split quarantines both branches. Original Qwct signal rules, session hours, half-tick tolerance, and orders are unchanged.

**Bring back the lines:** BSU PPHL COMPARE, BSU RESEARCH SUMMARY, BSU RESEARCH ELIGIBILITY, and any BSU PPHL ONLY BPU1/BPU2 entries. The PPHL summary separately reports pivot level-days, unique original pivots, overlap, PPHL-only observations, exact M5 BPU1, closed BPU2 and time eligibility, as well as PPHL Python binding/data failures. It must show a nonempty native PPHL denominator with no failure. The already-native-verified baseline from this window should stay at BPU1_strict=6 and BPU2_with_strict_BPU1=1.

**Historical status:** native PPHL is now Cloud-verified by run c87716354f4706f73666bf18add82885. **The newer read-only proof log patch is pending Cloud verification.** The tests use a mock native pivot event to check pivot/confirmation chronology; they do not certify the QuantConnect binding. Do not infer complete Gerchik pattern, SEC TVX, live execution or returns. Reusing the same three tickers isolates the pivot change; a subsequent separate experiment will compare point-in-time native Qwct/Universe.Top(50) screening rather than mixing both changes here.

**Source links:** [PPHL documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/pivot-points-high-low), [native PPHL implementation](https://github.com/QuantConnect/Lean/blob/master/Indicators/PivotPointsHighLow.cs), [original Gerchik BSU definition](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya), [time-of-day guide](https://gerchik.com/journal/fondovye-rynki/torgovyj-algoritm-aleksandra-gerchika/).

## Research mechanics

1. Subscribe to real US Equity **RAW** minute bars with `fill_forward=False`.
2. At **09:29 ET**, request already closed **RAW daily TradeBars** for each subscribed symbol; compute each day's ATR14 through LEAN's built-in `AverageTrueRange` updated exclusively from historical daily TradeBars (no homemade ATR).
3. Reuse Qwct `levels_for_session` and `native_cluster_tolerance` to select **all confirmed as-of support/resistance swing clusters** (`swing_cluster`, at least 2 touches, minimum level strength). **No model selector and no Bounce Score ≥4 requirement.**
4. Use each swing cluster's **original RAW bar high/low** as BSU origin, **never** the potentially fractional-price median; fail closed on missing origin, tick-grid misalignment and origin/cluster provenance.
5. Use LEAN's native `consolidate(symbol, timedelta(minutes=5), handler)` and Qwct's existing `validate_m5_tradebar` to process only completed, observed-volume, regular-session M5 TradeBars. Pass these bars to the *unchanged* `BsuDetector`.
6. Print capped `BSU RESEARCH BPU1`, `BSU RESEARCH BPU2`, `BSU RESEARCH NEAREST` and `BSU RESEARCH SUMMARY` rows. This independent research project's BPU2 is **close-of-bar evidence only**: no pre-close -30s TVX validation, no risk approval or order execution.

Native split events invalidate current day's observers. Historical price normalization/corporate actions are **not fully certified** by this first scan; cross-split cases require separate as-of factor-file validation. BPU1/BPU2 must not be treated as production signals or backtest trades.

## First native Cloud results and next evidence gate

**Verified from actual LEAN Engine 2.5.0.0.18179 output** for 2024-03-16..2024-04-26:

| Item | Native result |
|---|---|
| Symbols | MSFT, AMZN, AAPL |
| Symbol/day warmups | 87 |
| Structural BSU level-days | 416 |
| Native M5 consolidated bars | 6,786 |
| M5 × BSU case checks | 32,448 |
| Native BPU1 events | 8 |
| Closed-M5 BPU2 proxy events | 3 |
| Invalid subsequent attempts | 5 |
| Native errors / rejects | No reported rejects; run completed |
| TVX -30s | **Not tested** |
| Trading orders | Disabled |

Three **reported completed-candle** pairs:

1. **AMZN 2024-03-25:** BPU1 **15:00 ET** → BPU2 closed **15:05 ET**, RAW original resistance BSU **180.14**.
2. **AMZN 2024-03-26:** BPU1 **11:50 ET** → BPU2 closed **11:55 ET**, BSU **180.14**.
3. **AAPL 2024-04-10:** BPU1 **11:15 ET** → BPU2 closed **11:20 ET**, RAW support BSU **167.63**.

**Critical:** Qwct's current configurable Gerchik bounce session window is **12:00–13:30 ET**. All three BPU2 timestamps are **outside that window**. They are interesting *structural* BPU2 observations, **not tradable/eligible Qwct signals**. We must not override session rules to make trades.

Additional data-quality observation: AMZN M5 on 2024-03-26 at 11:55 has **high 180.135**, half a cent below 180.14 (0.5 of a $0.01 reference tick). This is the **BPU2 time**, not evidence that BPU1 occurred at 180.135. LEAN's RAW minute aggregates can contain such values; investigate provenance rather than rounding, labeling it exact, or altering detector tolerance.

### Native proof-log rerun now verified; next strict BPU audit

A second real QuantConnect LEAN Cloud backtest of the original proof-log implementation **completed successfully** on 2024-03-16..2024-04-26 with all 3 `BSU RESEARCH PROOF` and `BSU RESEARCH OHLC` pairs. Same 8 detector BPU1 / 3 detector BPU2. Exact native BPU1 extreme comparison:
- AMZN 2024-03-25, BPU1 15:00 resistance BSU 180.1400, actual M5 high **180.1450** = **+0.5 native tick**, *not strict equal*. BPU2 15:05 (outside allowed 12:00–13:30 ET window).
- AMZN 2024-03-26, BPU1 11:50 resistance 180.1400, actual M5 high **180.1450** = **+0.5 native tick**, *not strict equal*. BPU2 11:55 (outside allowed window).
- AAPL 2024-04-10, BPU1 11:15 support 167.6300, actual M5 low **167.6300** = **0 ticks**, strict equal. BPU2 11:20 (outside allowed window).

The 180.145 AMZN candles pass `BsuDetector._touch_exact` because its original half-tick comparison is intentionally unchanged. They are genuine **detector observations** but not demonstrated *strict-equality* BPU1. Do **not** change detector threshold by editing the main production strategy or manufacture extra BPU2.

**The current GitHub research `main.py` differs from the Cloud version used in that proof-log rerun.** It adds **read-only strict-vs-half-tick counters** `BPU1_detector`, `BPU1_strict`, `BPU1_half_tick`, `BPU2_detector`, `BPU2_with_strict_BPU1`, `strict_in_bounce_window` to the final `BSU RESEARCH ELIGIBILITY` line, and compares the bounce window to the **hypothetical 30-second-preclose clock**. It still does not enable native second data or orders. GitHub pure checks **336 passed** after a one-line regression test fix; this amended `main.py` **has not yet been verified in LEAN Cloud**.

Replace **only** the new research project's `main.py` with the GitHub link in the first table, run the same dates, and paste the new `BSU RESEARCH ELIGIBILITY` line. Leave 6 shared `strategy/` modules and `Qwct-LEAN-Test` unchanged.

### Historical proof-only implementation notes (now Cloud-verified)

To verify the reported BPU2 candidates without rewriting detection, update **only new-project `main.py`** from the GitHub link above. The added end-of-run **read-only** logs show:

- `BSU RESEARCH PROOF`: observed BPU1/BPU2 timestamps, actual historical RAW D1 origin date, cluster median vs original pivot, exact BPU1 distance in ticks, and whether BPU2 was within the **existing** bounce session window.
- `BSU RESEARCH OHLC`: observed closed-M5 BPU1 and BPU2 open/high/low/close, reported original stop/luft, and off-tick-grid distance of BPU2's relevant extreme.
- `BSU RESEARCH ELIGIBILITY`: how many observed BPU2 completions fell inside the original bounce session window. This is **not** risk approval or a TVX/entry signal.

This does not change detector logic, score, the universe, or orders. **The first proof-only version was successfully Cloud-tested. A newer strict-versus-half-tick summary version currently on GitHub still needs its own native Cloud test**. Re-run the same dates and share its log. Further native SEC preclose verification should only follow audit of the actual completed M5 evidence.

## Native LEAN scan 2024-06-08..2024-07-19: observed

Actual LEAN run completed without errors. MSFT/AMZN/AAPL, 445 level-days, 6,444 M5 bars, 34,134 checks; BPU1=0, BPU2=0, eligible=0, rejects={}. AAPL 2024-06-10 nearest BSU=192.94 high=192.93 (one tick short).

Across the three completed windows, there were 9 strict BPU1 and 3 close-of-M5 BPU2 following a strict BPU1, but zero inside the original 12:00-13:30 ET time window. Two completed observations occurred at the same AAPL BSU on the same date. These are research observations, not trade signals.

Pause date changes now. Next: compare independently labeled Gerchik examples to as-of native RAW swing origins, examine universe coverage and the session-time restriction. Leave all QuantConnect files unchanged.

## Native LEAN scan 2024-04-27 through 2024-06-07: verified

Actual LEAN 2.5.0.0.18179 log confirmed `candidate_level_days=424`, `checks=33072`, `BPU1_detector=4`, `BPU1_strict=3`, `BPU1_half_tick=1`, `BPU2_detector=3`, `BPU2_with_strict_BPU1=2`, `strict_in_bounce_window=0`, `rejects={}`; all orders disabled.

Two strict BPU2 episodes **AAPL 2024-04-29 14:20 and 14:30 ET** use the **same** RAW origin `174.3800` from 2024-03-11. They are distinct observed M5 pairs but not independent level-days. The other BPU2, **AAPL 2024-05-14 11:15**, follows a half-tick BPU1 (`187.0650` versus `187.0600`). All three are outside the existing 12:00–13:30 ET bounce window.

Combined two-window research, 2024-03-16 through 2024-06-07: **9 strict BPU1**, **3 closed BPU2 following strict BPU1**, and **zero strict BPU2 inside the configured bounce window**. No proof of SEC -30s, fills, or P&L.

**Next Cloud date window: 2024-06-08 through 2024-07-19.** Update only new project `Qwct-BSU-Research/main.py` from the link above. The standalone source's **default dates** now reflect this next window; if Cloud `scan_start`/`scan_end` parameters exist, those take precedence. The six unchanged dependencies and main `Qwct-LEAN-Test` are not updated. New-window results are **not yet native LEAN-verified**.

## 2026-10-14: Strict audit Cloud VERIFIED; next backtest configuration

**Third native LEAN v2.5.0.0.18179 run, 2024-03-16 through 2024-04-26, succeeded.** Full log includes:

```text
BSU RESEARCH SUMMARY symbols_warmed=87 candidate_level_days=416 M5=6786 checks=32448 BPU1=8 BPU2_closed=3 invalid=5 rejects={}; NO ORDERS
BSU RESEARCH ELIGIBILITY BPU1_detector=8 BPU1_strict=6 BPU1_half_tick=2 BPU2_detector=3 BPU2_with_strict_BPU1=1 strict_in_bounce_window=0; NO SEC TVX / NO ORDERS
```

- Six **strictly equal native BPU1 observations** versus eight original half-tick-detector observations; **two** AMZN BPU1 extrema were $180.145 against $180.140 and were not strict-equal.
- One **strict-BPU1 → closed-M5 BPU2 pair**, AAPL 2024-04-10 at 11:15→11:20 ET. This occurred **outside** the strategy's 12:00–13:30 ET bounce window.
- **Zero** qualified *strict pattern + hypothetical preclose session window* observations. **Zero** SEC -30s samples, actual orders, or P&L evidence.
- AMZN 2024-03-25 14:25 also had **strict exact BPU1** $180.140, but did not produce a confirmed closed-BPU2; this is why **BPU1_strict=6** must not be reported as six completed patterns.

**Next action:** paste **only** [new research `main.py`](https://github.com/tbsonion/Qwct/blob/main/research/bsu_cloud/main.py) into Cloud project `Qwct-BSU-Research/main.py` and rerun. The only source changes for the next test are the **default date strings**:

```text
scan_start = 2024-04-27
scan_end = 2024-06-07
```

Expected: `BSU RESEARCH ACTIVE 2024-04-27..2024-06-07`, a new `BSU RESEARCH SUMMARY`, and a new `BSU RESEARCH ELIGIBILITY`. **No native Cloud results for this next window have been observed yet.** All six shared `strategy/` modules remain unchanged. No strategy rule or detector tolerance changed.

## What success looks like

Start of logs: `BSU RESEARCH ACTIVE 2024-03-16..2024-04-26 MSFT,AMZN,AAPL; ALL ORDERS DISABLED`.

End of logs: `BSU RESEARCH SUMMARY symbols_warmed=... candidate_level_days=... M5=... checks=... BPU1=... BPU2_closed=... rejects=...; NO ORDERS`.

An `exact` touch is only when the actual M5 high (resistance) or low (support) equals the **original RAW swing price** within half the security's native tick. A gap of $0.04 on a $0.01-tick stock is **not exact**. A `BPU2_closed` result is not proof the price met TVX **30 seconds before BPU2 closed**.

If a result is blocked by RAW D1 history or data quality, bring the actual LEAN Cloud logs back for debugging. **GitHub CI does not verify QuantConnect API binding/runtime here.**

## Readiness and reproducibility

- Research source: `research/bsu_cloud/main.py`.
- Original Qwct detector and levels are **imported**, not rewritten.
- Pure source tests: `tests/test_separate_bsu_cloud_research.py`.
- Official LEAN API references:
  - [Time-period TradeBar consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators)
  - [Typed History with normalization modes](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests)
  - [Native ATR indicator](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/average-true-range)
  - [US equity corporate actions](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)
