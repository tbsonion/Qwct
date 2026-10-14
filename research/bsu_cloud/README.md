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

After a successful native LEAN scan of **2024-03-16 through 2024-04-26** (verified below), the current **new-project** `research/bsu_cloud/main.py` now defaults to the **next nonoverlapping 2024-04-27 through 2024-06-07** window. It still scans only **MSFT / AMZN / AAPL**, and no parameter UI is necessary. If Cloud project parameters `scan_start` / `scan_end` are already set, they override these defaults. `Qwct-LEAN-Test` is unchanged.

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
