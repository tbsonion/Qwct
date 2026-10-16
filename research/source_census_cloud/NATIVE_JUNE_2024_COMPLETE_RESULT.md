# QWCT 3.2 — Actual completed native LEAN June 2024 D1 source census

**Evidence:** User-supplied complete QuantConnect Cloud LEAN native backtest log (44 lines), engine **2.5.0.0.18184**, analysis ID **`72525e4a13533ad65dd156a1cfc70073`**, June 1–30 2024. The previous 3.2 log hit a 10 KB log cap; this **corrected subsequent run finished normally** and printed final counters. It took **89.13 s** and processed **392,878 data points**. This is a read-only historical **D1 data provenance** census — **no M1/M5 or orders, no strategy P&L**.

## Reproducible historical membership — exact prior native 3.0 parity

| Measure | Actual QWCT 3.2 | Prior QWCT 3.0 |
| --- | ---: | ---: |
| scans / days | **19 / 19** | 19 / 19 |
| Fundamental callbacks / weekend callbacks | **20 / 5** | 20 / 5 |
| strict same-day / verified next-session | **14 / 5** | 14 / 5 |
| selected stock × session | **950** | 950 |
| closed RAW D1 ready | **949** | 949 |
| stage2 ready | **861** | 861 |
| mirror-bearing stock × session | **689** | 689 |
| automatic D1 mirror level × session records | **1,431** | 1,431 |
| D1 morning-eligible mirror level × session records | **92** | 92 |

Exact gate counts also reproduced: 1,427 causal, 1,293 stage2 at mirror record level, 1,431 strong, 323 near, 843 role, 944 trend, cumulative strong=1,293, near=289, role=152, trend=92, causal=92. Prior 3.0 all-50 cohort thus **matched exactly**, so the new D1 source classifications are comparable without a time/membership disclaimer.

## Actual original confirmed source and price-basis results

| Source-data evidence | Native result | Correct meaning |
| --- | ---: | --- |
| Original D1 swing price/date confirmed | **92/92** | All 92 selected software mirror level-day records have a confirmed original source index and consistent causal D1 chronology |
| Original RAW swing on current native tick grid | **87/92** | Historical original extreme fits *current* symbol minimum price variation |
| Historical RAW swing off current native tick grid | **5/92** | Source requires historical tick/corporate-action review, not automatically fabricated or bad quote |
| SCALED_RAW original source + latest closed D1 both matched RAW | **65/92** | `basis=MATCH` only checks RAW/SCALED price-basis agreement at two dates, not Gerchik BSU correctness |
| Historical original price differs RAW vs SCALED_RAW | **26/92** | `basis=REBASED_SOURCE_HISTORY` (possible corporate-action adjustment; cannot infer a feed defect) |
| Latest closed D1 price differs RAW vs SCALED_RAW | **1/92** | `basis=LATEST_CLOSE_DIFFERENCE`; actual example UNH 2024-06-17; investigate before absolute price comparison |
| Meets combined grid ON + basis MATCH + original RAW source confirmed | **65/92** | Merely **data-consistent historical level×day proxy records**; **NOT** 65 verified BSUs, BPU1s, trades, or unique lineages |
| Distinct original software source-lineage keys | **35** | Strict composite fingerprint ticker, original high/low side, first and last swing days, mirror valid-from, original RAW price |
| Repeated software lineage-day records | **57** | 92 original level-day rows include 57 repeat appearances under same strict lineage key; **not** 92 independent setups |
| Source lineages with more than one cluster-median price over time | **1** | Mirror **median** can drift even when strict first/last swings and original source fingerprint remain the same |
| Source consistency counters | **ready_records_match=1, unique_group_records=92, seen_matches_confirmed_sources=1** | All 92 original morning records accounted for and grouped; no silent dropped source records |

Log end includes original selection rejects: **4 `ORIGINAL_KIND_AMBIGUOUS` mirror proxies** outside 92 ready, **1 `D1_INSUFFICIENT_CLOSED_RAW`** ticker-day. These were already rejected by original morning logic and **not** smuggled into the valid-source census.

## Predeclared first examples in actual capped native result

- **AMAT Jun03** original source high **214.255**, automatic median **214.460**, **OFF_GRID / REBASED**, lineages audited even though not grid-and-basis-consistent.
- **NFLX Jun03** source **634.54**, median **633.775**, **ON_GRID / MATCH**; **SRPT Jun03** source **124.51**, median **125.00**, **ON_GRID / MATCH**.
- **JPM Jun04** source **200.48**, median **200.71**, **ON_GRID / REBASED**; **MSFT Jun05** source **415.32**, median **415.59**, **ON_GRID / REBASED**.
- **V Jun13** source **273.445**, median **273.445**, **OFF_GRID / REBASED** (a matching median can STILL have subpenny/historical price basis concerns).
- **UNH Jun17** source **496.00**, median **496.0625**, **ON_GRID / LATEST_CLOSE_DIFFERENCE**. This is the **single latest-close mismatch** in 92; no diagnosis of dividend/split/source defect from the output alone.

## Meaning and NEXT minimal experiment

The native evidence answers the whole 3.2 question: **the earlier 92 morning-ready software mirror proxies consist of 35 distinct recorded source lineages, 57 repeated lineage-day observations; 65 level-day records have matching RAW/SCALED basis and original on-grid swing prices; 27 do not satisfy that combined conservative data-consistency marker**. The 27 flagged rows are NOT proven unusable; historical corporate-action RAW/SCALED price basis differences and off-grid original historical extremes require separate interpretation.

**Crucial missing research is no longer to re-run this June D1 census or widen to 92 M5 tests. It is to define what a valid fixed Gerchik BSU should be for software `kind='mirror'`: original confirmed D1 RAW swing extreme, later cluster median, a fixed post-reversal retest reference, or a true author-approved price zone.** Current code tests only original swing vs median. Actual native 3.1 on first AMAT/NFLX/SRPT plus MSFT negative confirmed **0 exact original-source relevant M5 wick touches**, with nonexact straddles; that does NOT imply there are no tradable manual textbook mirror levels.

**Next focused 3.3 recommendation:** Before implementation of any production mirrors, prepare a human-labeled **small fixed sample of distinct source lineages** (some `ON_GRID+MATCH`, at least one `OFF_GRID/REBASED`, and one negative role/trend control), plotting source D1 high/low, software median, causal breach candle, retest candle, and subsequent regular-session 5m geometry. Use primary Gerchik annotated examples/lessons to explicitly select the expected fixed or zone BSU reference. Label with status `MANUAL_UNVERIFIED` until an actual supported price-reference standard is decided. Do **not** reinterpret all nonexact M5 range crosses as BPU1, loosen BPU1 half-tick criterion, or claim profit/execution.

No further QWCT 3.2 native Backtest required. Production, original 2.8, 3.0, 3.1 research files remain unchanged. The only native result established here is **D1 source provenance/basis and repeat lineage**, not TVX or trades.
