# Native LEAN PPHL → D1 Qwct mandatory gates (2026-10-15)

**Evidence:** User-provided QuantConnect real LEAN 2.5.0.0.18179 backtest log, ID `61c134f14f24691fce277aac8730bf3e`, **2024-03-16 through 2024-04-26**. Project: **Qwct-BSU-Research** (not original `Qwct-LEAN-Test`). Three fixed symbols MSFT/AMZN/AAPL, **ALL ORDERS DISABLED**. This log verifies the previous `strategy/__init__.py` workaround actually loaded and `BSU D1 BRIDGE` emitted three rows. It is not trading/backtest P&L evidence.

## Original observed native logs — three distinct PPHL-only episodes

| Native BPU2 | Side | BSU | D1 origin | 2-touch Qwct eligible | Yesterday proximity | Qwct trend | Global / Local | Theoretical 4R room | Theoretical 3R room | Nearest next D1 | Native SEC at -30s |
|---|---|---:|---|---|---|---|---|---|---|---:|---|
| **AMZN 2024-03-21 13:15** | short | 179.5300 | 2024-03-14 | **FAIL** | PASS | **FAIL** | `+1/+1` (up/up, opposite short) | PASS, **7.06R** | PASS | 171.8650 | **UNKNOWN**; no last TradeBar exactly 13:14:30 |
| **AAPL 2024-04-03 12:20** | long | 170.2800 | 2024-03-15 | **FAIL** | PASS | **FAIL** | `-1/-1` (down/down, opposite long) | **FAIL, 3.18R** | PASS | 173.5550 | retrospective limited-rule PASS; **not executable** |
| **AAPL 2024-04-12 12:25** | long | 175.8200 | 2023-08-25 | **FAIL** | PASS | **FAIL** | `-1/-1` (down/down, opposite long) | PASS, **4.36R** | PASS | 180.1700 | retrospective limited-rule PASS; **not executable** |

All three `origin=PASS`: the historical pivot OHLC/time agrees with the reported RAW daily as-of history; all three `proximity=PASS`: yesterday's close is within the configured Qwct 1×ATR threshold. **None is approved by Qwct**: `cluster2touch=FAIL` and `trend=FAIL` everywhere, model score remains **UNKNOWN**, no real-time orders or SEC TVX. These are **partial historical D1 diagnostics only**.

### Precisely what failed and what we should NOT infer

1. **Two-touch cluster:** `PPHL-only` is the research subset of native PPHL pivot origins that are *not* original accepted two-touch cluster origins. Consequently `cluster2touch=FAIL` is **expected by the experiment's selection design**, not new independent evidence that three supposedly Qwct-valid levels were invalidated. A single historic BSU bar confirmed by BPU1 can be valid in the published Gerchik BSU/BPU *pattern definition*, but Qwct separately mandates prior daily `min_touches=2`, cluster tolerance, strength and valid-from. Comparing these is a **strategy-specification question**, not reason to silently relax a gate.
2. **Trend gate:** in canonical Qwct `strategy/signals.py`, mandatory `trend_aligned` with `allow_countertrend=False` requires both `global_trend` and `trend_direction` to match **the proposed side**, not merely one another. The native D1 values unambiguously fail this exact mechanical requirement: AMZN short is up/up, both AAPL longs are down/down. This is a **second, independent rejection**, and flipping the cluster requirement alone cannot make these examples admissible.
3. **Proximity PASS** is not a full model score, breakout/bounce selection or plan. It is only as-of yesterday's close vs raw source pivot and native daily ATR.
4. **4R / 3R columns** are *theoretical distance to the next observed historic Qwct D1 level* using proposed `entry=BSU±luft` and the detector's stop. No actual limit fill or available bid/ask was demonstrated. The research `room3R=PASS` tests available *level-to-level space*, whereas the canonical `target_at_least_3r` gate in `strategy/signals.py` computes whether the strategy-specified target is at least `cfg.min_rr=3` in units of risk. **Those are NOT identical definitions**, and the log does not prove `target_at_least_3r=PASS` or execution.
5. **SEC:** `RETROSPECTIVE_RULE_PASS` (2 AAPL) is a historical 1-second TradeBar extrema reconstruction by cutoff, not an actual event-driven preclose TVX, submitted order, quote, transaction or P&L. `NO_TRADE_AT_EXACT_CUTOFF` (AMZN) is UNKNOWN, not fail/pass. D1 filter check is retro at end using only already closed past D1 bars, still no trading.
6. **No evidence of a profitable strategy**: zero trades, zero fills. Events are structural research observations, not wins or trade-count denominator.

## External rule-source cross-check (do not mix markets)

- Official [Gerchik BSU/BPU article, May 9 2024](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya) explicitly defines historical BSU, exact BPU1 touch, immediate BPU2, luft 20% of stop and TVX at -30 seconds. It does **not** state that the algorithm must first find *two separate confirmed D1 swing pivots* to create a candidate BSU; the Qwct two-touch requirement is an additional implementation/spec choice.
- Official [Gerchik “Отбой от уровня”](https://gerchik.com/journal/instrukczii/otboi-ot-urovnya/) explains D1-level, M5 BPU/TVX, at-least-3:1 target, and explicitly mentions risk reduction for countertrend in that article, **not blanket equivalence of countertrend to standard aligned trades**.
- A separate [Gerchik FORTS algorithm (PDF)](https://gerchik.com/pdf/algoritm_forts.pdf) says bounce aligned with **local** trend, but explicitly states its algorithm applies to **FORTS futures only**, not US equities. Do **not** transplant its rules into Qwct to overturn the user's frozen `allow_countertrend=False` / `global+local` filter.
- Canonical **Qwct** original authoritative `strategy/config.py` and `strategy/signals.py` remain unchanged; docs: [strategy specification](../../docs/strategy_spec.md) and [source](../../strategy/signals.py).

## Prioritized next step — not another blind backtest

**P0 methodological decision before implementation:** obtain independently date-labelled **positive AND negative Gerchik example charts with their intended daily level drawn BEFORE the M5 signal**, verify whether an initially single-swing source can be a D1-qualified bounce level without the extra cluster formation requirement, and determine what trend rule applies to the target US equity model. Need **at least 10–20 examples** before sensitivity claims. Do not force any of the above three countertrend observations to become valid by weakening filters.

**Reuse-first, if broader coverage is wanted after rule reconciliation:** use the already-existing dynamic Qwct screener / QuantConnect Fundamental Universe and `PivotPointsHighLow` observer, under read-only Free constraints. Evaluate a **larger point-in-time universe** for candidates passing original trend and level prerequisites rather than extending MSFT/AMZN/AAPL date windows repeatedly. Separate screening evidence from trade approval.

**Current Cloud action: NONE.** This last true native D1 run succeeded; all original trading components unchanged; no more user backtest necessary to explain these specific three failures.
