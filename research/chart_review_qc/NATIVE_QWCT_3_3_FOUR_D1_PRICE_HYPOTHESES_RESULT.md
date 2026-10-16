# QWCT 3.3 — Native QuantConnect four-case D1 BSU-price hypotheses (2024-06-03)

**Evidence:** User-provided original QuantConnect Research Notebook console output and FOUR actual D1 figures for **AMAT, NFLX, SRPT, MSFT**. This is a **successful rerun** after fixing native LEAN D1 nonmidnight index vs `YYYY-MM-DD` source/breach/retest event lookup. It is **not a second M5 replay**, not a broker simulation and NOT evidence that a specific historical price has been independently approved as a real Gerchik BSU. All candles and price hypotheses below existed **before 2024-06-03 09:29 ET**.

Script: [`GERCHIK_3_3_D1_LEVEL_EVIDENCE_ONE_CELL.py`](./GERCHIK_3_3_D1_LEVEL_EVIDENCE_ONE_CELL.py). Author-evidence rules: [`QWCT_3_3_GERCHIK_BSU_SOURCE_DECISION_RU.md`](./QWCT_3_3_GERCHIK_BSU_SOURCE_DECISION_RU.md). Previous real native M5 check: [`NATIVE_JUNE03_RAW_SOURCE_M5_RESULT.md`](./NATIVE_JUNE03_RAW_SOURCE_M5_RESULT.md). **No M1/M5 requested in 3.3**.

## 1. Real original RAW-as-of D1 source price comparison

All four cases reproduce the exact frozen original QWCT 3.0 first-day candidate mirrors, including three `research_eligible=1` LONG rows and one `research_eligible=0` MSFT negative control. Every D1 causal mirror has `PROXY_VERIFIED`; this means *software source/breach/retest chronology*, not manual BSU validity.

| 2024-06-03 | Original old→new D1 mirror role | FIRST confirmed RAW swing high | LAST confirmed RAW swing high | Software ATR cluster median | Historical D1 role-retest LOW | FIRST→LAST Δ, current $0.01 ticks | FIRST→MEDIAN Δ | FIRST→RETEST Δ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **AMAT LONG** | resistance→support | **214.255** (Mar07; OFF native grid) | **214.460** (Apr15) | **214.460** | **212.140** (May20) | **+20.5** | **+20.5** | **−211.5** |
| **NFLX LONG** | resistance→support | **634.540** (Mar21) | **633.010** (Apr12) | **633.775** (OFF native grid) | **630.000** (May23) | **−153.0** | **−76.5** | **−454.0** |
| **SRPT LONG** | resistance→support | **124.510** (Sep28 2023) | **125.500** (Mar08) | **125.000** | **124.745** (Mar22, OFF native grid) | **+99.0** | **+49.0** | **+23.5** |
| **MSFT negative control** | resistance→support; inferred SHORT rejected, `role_ok=0, trend_ok=0` | **415.320** (Jan31) | **415.860** (Feb23) | **415.590** | **412.800** (Mar15) | **+54.0** | **+27.0** | **−252.0** |

**Grid warnings use current symbol `minimum_price_variation=$0.01` as seen by QuantBook, not a certified historical exchange tick for all old sessions.** Example: AMAT original $214.255, NFLX software median $633.775 and SRPT D1 retest LOW $124.745 are off that current penny grid; **this is not proof of invalid historical quotes or ineligibility by itself**. Three different kinds of price can be off-grid; the cluster median is nonetheless an unapproved *software* price even when it falls on-grid.

## 2. Actual closed D1 chronology and retest candles — NOT automatically BPU1

The level-proxy code requires a prior D1 close-through breach, then a separate D1 reversal-side retest, with mirror `valid_from` on the following calendar day. These events were already causally dated in QWCT 3.0; 3.3 now reproduces **their actual native RAW OHLC** for comparison:

| Ticker | D1 close-through breach date + OHLC (O,H,L,C) | D1 role-retest date + OHLC (O,H,L,C) | Mirror valid from |
| --- | --- | --- | --- |
| **AMAT** | **May15** (212.43, 217.61, 210.85, 217.49) | **May20** (212.15, 221.75, 212.14, 219.95) | **May21** |
| **NFLX** | **May20** (620.4, 644.37, 619.64, 640.82) | **May23** (642.34, 642.97, 630.00, 635.67) | **May24** |
| **SRPT** | **Mar20** (124.37, 126.11, 122.52, 126.08) | **Mar22** (125.14, 128.15, 124.745, 127.54) | **Mar23** |
| **MSFT** | **Mar14** (420.8, 427.83, 417.97, 425.22) | **Mar15** (418.99, 422.72, 412.8, 416.42) | **Mar16** |

On the two selected screen-chart rows with big deviations, **AMAT D1 retest LOW 212.14 was $2.115 below first source 214.255**, while **NFLX retest LOW 630 was $4.54 below first source 634.54**, but retest days still closed on the support side. This shows why **software D1 'breach + retest = mirror' is insufficient alone to approve a precise Gerchik fixed BSU at either source first high or cluster median**. These were *D1 reversal bars*, not the intended next-day M5 BPU1. Do not backfit to alternate D1 retest lows because the early-Jun M5 might cross them.

## 3. Outcome and strict next decision

- **Native technical task succeeded:** 4/4 frozen `SOURCE`, `HISTORICAL EVENTS`, four `D1 CANDIDATE` price alternatives and D1 charts printed without the former timestamp lookup exception. Three frozen positive morning candidates retained original Stage2/near/role/trend/strength; MSFT negative failed role and trend exactly as planned.
- **FOUR price hypotheses are not four equally author-supported fixed BSUs:** only FIRST and LAST arise from confirmed original side swing-extreme bars; CLUSTER MEDIAN is arithmetic, and D1_ROLE_RETEST is a prior D1 wick confirming software chronology. No primary Gerchik example has yet selected the correct reference for any of these four exact stock dates.
- **Do not declare “original FIRST is wrong” or “LAST is correct” by looking at Jun03 M5.** In the previous independently frozen 3.1 real native M5 study, 0 exact original-source relevant long-low wick touches were observed across the three positive and one control cases; 38 source-range straddles were NOT exact BPU1. This discrepancy alone does not certify a different price.
- **Manual labels remain** `author_BSU_fixed_price=UNKNOWN, price_reference=UNKNOWN, fixed_or_floating=UNKNOWN, status=INDETERMINATE` for **all four**. This is a genuine unresolved *source specification question*, NOT a native feed or D1 timeline error, trading signal or performance result.

**Stop / exit criterion:** Before implementing mirror trade patterns, a knowledgeable reviewer must establish a **specific reproducible Gerchik-compliant fixed price definition on as-of D1 using author-grounded examples**, or mark a case floating/untradeable, and record the decision **without referencing later M5 trade outcomes**. Do not widen tolerance to convert 38 straddles to BPU1, automatically select a favorable FIRST/LAST/median/retest or run all 92 M5 days again. If definition remains indeterminate, hold trading mirror branch and focus on making the existing D1 candidate labeling reviewable/transparent rather than adding new algorithmic gates.

Original 2.8/3.0/3.2 native backtest files, source Level detector, BsuDetector, rules, thresholds and actual trading integrations **untouched**.
