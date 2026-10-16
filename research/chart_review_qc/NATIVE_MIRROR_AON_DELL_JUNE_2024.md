# QWCT 2.9 — Native QuantBook AON/DELL D1 mirror inventory

## 2026-10-15 — Actual native morning eligibility results (FOLLOW-UP, completed)

**Additional real QuantConnect Research output was provided.** These **are** observed results, not proposed test values.

**AON 2024-06-12**: `prior_close=293.70`, `ATR14=4.866`, `stage2=1`, `global_trend=-1`, `local_trend=-1`. Original `cfg.level_proximity_atr=1.0`. The five observed D1 mirrors are all **too far from prior close**; none qualifies for research shortlist even before asking whether it is a manually valid Gerchik BSU.

| Mirror price | New role from original source | Candidate side from prior close | Distance / ATR | Original proximity `near` | Role-aligned | Trend-aligned | Strength | Original morning eligibility |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **285.950** | resistance | long | **1.593** | 0 | 0 | 0 | 1 | **0** |
| **312.970** | resistance | short | **3.960** | 0 | 1 | 1 | 1 | **0** |
| **317.680** | support | short | **4.928** | 0 | 0 | 1 | 1 | **0** |
| **317.945** | resistance | short | **4.982** | 0 | 1 | 1 | 1 | **0** |
| **329.210** | support | short | **7.298** | 0 | 0 | 1 | 1 | **0** |

**DELL 2024-06-07**: `prior_close=133.96`, `ATR14=9.6386`, `stage2=1`, `global_trend=1`, `local_trend=1`; **0** existing automatically tagged mirror levels. No mirror eligible case could arise in this particular lookup.

**Conclusion narrowly scoped to two specific ticker-days:** The current cohort's exclusion of `kind='mirror'` is a **known methodological scope limitation**, but **it did not demonstrably suppress a mirror candidate that otherwise passed the original morning gates on either of these two days**. Five AON historical mirror proxies are NOT five lost trades. Do not widen proximity beyond the established **1.0 ATR**, retroactively move BSU levels to manufactured touches, or count 11 older original-pivot M5 straddles as BPU1. **0 mirror research candidates** here, NOT a conclusion across the other 17 calendar sessions or ~950 selected stock-days.

**Research priority now:** Put a short research-only **mirror eligibility census** beside the unchanged original morning screener over the existing PIT universe across other days/months (same native Fundamental callbacks, existing 1 ATR / Stage2/trend/role/strength criteria). Report eligible *symbol-day* counts separately from mere historical mirrors, then examine any positive cases with native RAW-as-of D1 source prices and actual M5. Do not run M5/SEC/TICK for mirror proxies that already fail the native morning eligibility gates. In parallel, unresolved Gerchik manual D1 BSU source specification (RAW original swing vs ATR-cluster median/floating zones) remains independent.


**Evidence:** user-submitted actual QuantConnect Research Notebook output for **AON on 2024-06-12** and **DELL on 2024-06-07**. Notebook `MIRROR_AON_DELL_ONE_CELL.py` uses 180 original RAW closed D1 TradeBars, native LEAN ATR(14)/SMA and the repository's existing `levels_for_session` + independent chronological `audit_mirror`. **No orders or BPU1 asserted.**

## Captured native results

- **AON 2024-06-12:** 180 frozen daily source bars, **9 algorithmic D1 levels**, of which **5 are `kind=mirror`** and independently report `status=PROXY_VERIFIED reason=CLOSED_D1_BREACH_RETEST_ASOF`. Native D1 median ATR-based clustering tolerance was **1.3060**.
- **DELL 2024-06-07:** 180 frozen daily source bars, **6 algorithmic D1 levels**, **0 automatically tagged mirror**. Native D1 cluster tolerance **0.5519**. This does not prove absence of manually drawn Gerchik mirror levels.

| AON automatically tagged mirror price | Original type inferred from source D1 bar | Chronologically observed separate close breach | Observed subsequent retest | `valid_from` | Independent D1 proxy status |
| ---: | --- | --- | --- | --- | --- |
| **285.950** | support → candidate new **resistance** | 2024-05-22 | 2024-06-04 | 2024-06-05 | PROXY_VERIFIED |
| **312.970** | support → candidate new **resistance** | 2024-04-11 | 2024-04-22 | 2024-04-23 | PROXY_VERIFIED |
| **317.680** | resistance → candidate new **support** | 2024-03-18 | 2024-04-05 | 2024-04-06 | PROXY_VERIFIED |
| **317.945** | support → candidate new **resistance** | 2024-04-04 | 2024-04-10 | 2024-04-11 | PROXY_VERIFIED |
| **329.210** | resistance → candidate new **support** | 2024-03-26 | 2024-04-01 | 2024-04-02 | PROXY_VERIFIED |

**Interpretation of `PROXY_VERIFIED`:** These are **five reproducible software D1 level-proxy classifications**, with a recorded source-side, a causal breach and separate retest dated before the target session. They are **not five Gerchik-certified tradeable BSUs or entries**. The check does **NOT** verify a precise original-source price versus off-grid cluster, proximity to the **actual prior close** or ATR threshold, current trend/side alignment, whether a mirror was later invalidated or aged out after its initial retest, any intraday BPU1/BPU2 setup, or the -30s TVX. No profitability inference is possible.

**Key implementation finding:** the existing `strategy/levels.py` *does* identify mirror role reversals. The **research cohort** `classify_snapshot` **excludes** `kind=mirror` from its ready-candidate shortlist, so the previous baseline counts never covered those five D1 proxies. But there is **not yet evidence** that any of these five should pass all OTHER morning criteria (nearby existing price, global/local trend agreement, direction, source/tick-grid validity, liquidity rank). **Do NOT report five missed eligible trades, or widen BPU1 tolerance.**

## Next minimal test, without re-running the existing June cohort

Read-only morning **eligibility diagnostic** for **only these actual mirrors**, ideally using the same native QuantBook session freeze:
1. Print the actual previous closed D1 **close, ATR14, 50-SMA/global/local trend**, and for each mirror its **signed distance in ATR units**, opposite-side role (`support→resistance`, `resistance→support`), and original `valid_from`.
2. Count separately: `MIRROR_SEEN`, `MIRROR_NEAR` (uses existing `cfg.level_proximity_atr`, no new threshold), `MIRROR_TREND_ALIGNED`, `MIRROR_ROLE_ALIGNED`, `MIRROR_FROZEN_ELIGIBLE` (all frozen gates), and `MIRROR_SOURCE_PRICE_UNKNOWN` if original confirmed swing/high/low and native tick are not proven.
3. Review any *genuinely eligible* mirror's raw source D1 and actual native M5 level geometry independently. If all AON mirrors were too distant or role-conflicted, the current `classify_snapshot` exclusion is a **scope omission but not empirically a missed viable candidate on this specific date**.
4. Only after independent positive/negative chart labels consider adding a **separately controlled mirror read-only research mode**, never automatically promote to production trading or classify a mere M5 range crossing as BPU1.

**Native AON/DELL original RAW BSU chart review** is separate, at [`NATIVE_VISUAL_REVIEW_AON_DELL_JUNE_2024.md`](./NATIVE_VISUAL_REVIEW_AON_DELL_JUNE_2024.md). Those original 2.8 source pivots did not produce exact-BPU1 wicks. User does **not** need to rerun identical charts for this mirror tally. Current original QuantConnect files remain unchanged.
