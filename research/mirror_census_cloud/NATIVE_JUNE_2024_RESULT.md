# QWCT 3.0 — Actual native LEAN June 2024 mirror census result

**Source:** user-provided 51-line markdown export of a real native QuantConnect Cloud Backtest log, engine **2.5.0.0.18184**, analysis ID **f3bfd88e2caf06f53ff02c353b76d27f**. Code source: [QWCT 3.0 all-50 PIT mirror census](./main.py). This is read-only research, not a trade/P&L backtest; logs explicitly state NO ORDERS and NO M1/M5. All figures below are **actual tool output from the user**, not forecasts or expected counts.

## Confirmed cohort coverage

| Scope | QWCT 2.8 baseline | QWCT 3.0 actual |
| --- | ---: | ---: |
| Market-day scans | 19 | **19** |
| Observed Fundamental callbacks | 20 | **20** |
| Weekend Fundamental callbacks | 5 | **5** |
| Trading sessions processed | 19 | **19** |
| Same-day PIT callbacks | 14 | **14** |
| Verified next-session PIT callbacks | 5 | **5** |
| Frozen Fundamental selected stock-days | 950 | **950** |
| Valid native closed RAW D1 frames | 949 | **949** |
| Stage2-qualified stock-days | 861 | **861** |

The observed **19 daily `QWCT MIRROR DAY`** rows sum to **950 members, 1,431 mirror proxies, 323 distance-near mirror proxies, and 92 morning-ready mirror proxies**, matching the June summary exactly. The five next-session callback events are visible for June 3, 10, 17, 20 (Juneteenth), 24. (All five are logged; historical exchange membership is supplied by native LEAN.)

## Actual mirror-level D1 screening funnel

| Metric | Observed count | Unit / interpretation |
| --- | ---: | --- |
| Mirrored stock-days | **689** | Selected ticker-day histories containing ≥1 automatically tagged mirror |
| Total historical mirror records | **1,431** | Mirror **level × ticker-day**, may repeat same underlying level across dates |
| Causally verified mirror records | **1,427** | Proven `PROXY_VERIFIED` original type, breach and retest; four remain ambiguous |
| Stage2-passing mirror records (marginal) | **1,293** | Count before geometric proximity |
| Original strength-passing mirror records | **1,431** | Count before other gates |
| Near previous close (≤1 ATR), marginal | **323** | Regardless of Stage2 |
| Stage2 + strength + near | **289** | Accumulated original filters |
| Plus correct mirrored support/resistance role | **152** | Accumulated original filters |
| Plus native local/global trend direction | **92** | Accumulated original filters |
| Plus independent causality proof | **92** | **D1 morning-eligible *proxy records***; NOT BSU/BPU/TVX, not executions or distinct trades |
| Marginal role alignment across all mirrors | **843** | Not additive to marginal trend or near |
| Marginal local/global trend alignment across all mirrors | **944** | Not additive to other marginals |
| Rejects | **4 ambiguous original type, 1 D1 insufficient** | Not converted to zero-candidate days or signals |

**Important interpretation:** The method `classify_snapshot` in original QWCT 2.8 excluded `kind='mirror'`, but in this census **92 automatically-tagged mirrored D1 level × stock-day records did pass the frozen original morning gates**, across 19 historical sessions. This demonstrates potentially significant **coverage omission** in the previous *research candidate pipeline*, **not 92 certified Gerchik trades, not 92 unique companies/setups and not 92 positive BPU1 signals**. Deduplicating repeated levels and validating exact BSU source still required. Do not add them to production screener, relax strict BPU1 equality or infer P&L.

## Earliest predeclared first-day candidates for chart-source inspection

The first session June 3 had `ready=3`, and the near samples in the log show exactly **three** original-gate fully positive rows. These are *candidate examples* for follow-up; we inferred eligibility from all printed filter flags and causal proof, not from a missing `QWCT MIRROR READY` row in the supplied export:

| Date | Ticker | Algorithmic **cluster median** | Previous closed D1 price | Native ATR14 | Distance/ATR | Reversed role and inferred side | Stage2/strength/role/trend and proof |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| **2024-06-03** | **AMAT** | **$214.4600** | $215.0800 | $5.8564 | **0.106** | **support → LONG** | all 1; `PROXY_VERIFIED`; `valid_from=2024-05-21` |
| **2024-06-03** | **NFLX** | **$633.7750** | $641.6200 | $15.5205 | **0.505** | **support → LONG** | all 1; `PROXY_VERIFIED`; `valid_from=2024-05-24` |
| **2024-06-03** | **SRPT** | **$125.0000** | $129.8600 | $5.7427 | **0.846** | **support → LONG** | all 1; `PROXY_VERIFIED`; `valid_from=2024-03-23` |

These three first-day examples minimize hindsight selection because they were selected by **the first calendar day's frozen screening flags**, not by any observed later M5 price outcomes.

## Known limitations / possible confounders

1. **RAW/SCALED_RAW adjusted basis**: two QuantConnect history factor-file warnings were printed June 6. They are not itself proof of failure, but frozen original D1 source price and timestamp (and split/dividend continuity) must be audited separately before claiming precise valid limit orders. Earlier 2.8 observed 10 **REBASED** of 17 source probes.
2. **No manual Gerchik BSU ground truth**: a D1 `PROXY_VERIFIED` label only verifies code-level prior breach/retest chronology on **median ATR-cluster** levels, not author-equivalent BSU zone, fixed RAW tick-level or a valid trade setup.
3. **No actual BPU1 or BPU2 screening**: This run fetched NO M1/M5. **Do not infer 92 BPU1, signals, trade entries or win rates**.
4. **Repetition and uncertainty**: `mirrors` and `eligible_proxies` are **level×stock-day**, so they can include the same price and ticker over multiple mornings. The log exported only a subset of 40 `NEAR` samples and no `READY` sample lines, despite an unambiguous summary. The summary and consistent per-day aggregate are the authoritative counts.
5. **Dataset limits**: 50 equities/day in Jun2024, no out-of-sample months or statistical trading performance. An eligibility-only pass does not prove the omitted research arm would pass strict raw source wick equality or other later rules.

## Next single test — only three first-session stocks, NO full-month rerun

1. **AON/DELL work is done.** Freeze a new read-only QuantBook Research comparison for **AMAT / NFLX / SRPT, on 2024-06-03 only** (a priori first-day positive mirror proxies above). For each original RAW 180 closed D1 input, show confirmed original swing high/low **price and source date** versus **cluster median**; independent mirror breach/retest; native minimum tick and RAW/SCALED_RAW origin-basis observations; adjusted/nonadjusted consistency.
2. Only after a source-valid as-of mirror is confirmed, fetch true native M1 and examine closed **M5 high/low** for exact source-pivot wick touching separately from mere range crossing. Mark `BPU1/BPU2 NOT VERIFIED` until the actual original detector is applied. Keep false positives and no-candle cases.
3. First compare the smallest **positive** group with a same-day role-conflicted **negative** group (e.g. MSFT or TSLA), to avoid labeling every crossing as success.
4. Depending on chart labels, decide if a **separate mirror-only observational cohort arm** is justified. No production changes and no broker integration yet.

No extra 3.0 backtest is needed to confirm the 92 number. The last native run already fully matches expected coverage.
