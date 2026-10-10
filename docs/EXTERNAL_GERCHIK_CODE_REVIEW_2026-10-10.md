# External Gerchik implementations vs Qwct — independent comparison

Reviewed 2026-10-10. **Research only**. No external code ported or
copied into Qwct, no trading enabled, no Cloud LEAN backtest run.

## Confirmed reference implementations

1. **Authoritative pattern description**
   https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
   Explicit structure: BSU historical origin bar; BPU1 touches BSU
   exactly; BPU2 immediately follows BPU1 and remains in the same
   plane with max 20% stop-distance luft; TVX limit is placed
   approximately 30 seconds BEFORE BPU2 close; piercing BPU1 by
   BPU2 invalidates. Primary semantic reference for the BSU model.
2. **VibeFox BSU/BPU Levels (MT5, paid indicator, source NOT accessible)**
   https://www.mql5.com/ru/market/product/183947
   Describes fractal pivot BSU, subsequent confirming BPU touches,
   bounce and breakout markers. Describes an HTML report of
   level-entry screenshots. Does not demonstrate Gerchik's
   30-second TVX timing or prove the model's accuracy. No license
   or grounds for copying proprietary code.
3. **MLSS v3 + Alerts (open-source TradingView Pine indicator)**
   https://www.tradingview.com/script/7SmrJUtf-mlss-v3-alerts/
   Describes tick-tolerance limit-player levels, historical levels
   and mirror role-reversals. Useful as a reference for
   *level semantics*, not a certified complete trading bot.
4. **ATR Gerchik Light (open-source TradingView Pine indicator)**
   https://www.tradingview.com/script/47GwtmBg-ATR-Gerchik-Light/
   Describes short daily range ATR with exclusion of abnormally
   large/small bars. Compare with Qwct's native Wilder ATR(14);
   DO NOT silently swap, since the current StrategyConfig explicitly
   specifies native ATR(14) thresholds.
5. **ATR5 Gerchik & Co (open-source TradingView Pine indicator)**
   https://www.tradingview.com/script/9d7ayfpX-ATR5-Gerchik-Co/
   Describes average range of five completed D1 bars.
6. **mhs54/tradingview-indicator (actual GitHub Pine source)**
   https://github.com/mhs54/tradingview-indicator
   The repository's `strategy_v2.pine` includes multiple
   premarket, daily, hourly and monthly level sources and waits for
   confirmed intraday conditions; `sr_channels_v1.pine` clusters
   higher-timeframe pivots. This is the author's separate LTP
   (Levels+Trend+Patience Candle) strategy, **NOT Gerchik**.
   Avoid copying `request.security(...,lookahead_on)` without a
   detailed non-repainting/as-of audit.
7. **Gerchik + SMC God Mode (TradingView invite-only)**
   https://www.tradingview.com/script/epyXTsv4-SMC-God-Mode-PREMIUM-v13-0/
   Claims BSU/BPU, failed breakout and level-strength calculations.
   Its proprietary source and results are not verified.
8. **MLSS-style alternative: source available in MQL5 CodeBase**
   https://www.mql5.com/en/code
   A large generic indicator library, not an identified complete
   Gerchik algorithm. Do not equate a generic pivot detector with
   implementation of the whole business method.

**Search limit:** No verified complete, open-source, US-equities
QuantConnect LEAN + Schwab Gerchik/BPU strategy found in the sources
checked. This does NOT establish nonexistence elsewhere.

## Direct Qwct mismatches verified from repo source

### P0: the BsuDetector is not connected to the actual algorithm

`strategy/patterns_bsu.py` contains a `BsuDetector`, but the active
`main.py` imports `levels_for_session`, `ScenarioEvaluator` and
`build_intent`, not `BsuDetector`. No `BsuDetector.on_bar` call
is made in the runtime. Actual levels come from
`levels.py::detect_levels`, which clusters two or more confirmed
**swing-high/swing-low pivots**; this is not the documented
BSU/BPU1/BPU2 sequence of a source bar and two subsequent
confirmations. Thus the runtime does NOT trade/detect BSU/BPU2 TVX.

### P0: BPU2 invalidation checks close rather than touched extreme

`BsuDetector._pierced_bpu1` tests `bar.close < BPU1.low`
(long) or `bar.close > BPU1.high` (short). The original method
invalidates if BPU2 *crosses the BPU1 value*, not only when it
**closes** beyond it. Example: BPU1 low=100; BPU2 low=99.90,
close=100.10, level=100, luft=0.20. Qwct's close-only test passes
and `_beyond_luft` also passes, yet the BPU1 low was broken.

### P0: TVX price touch can be claimed when price never traded there

In `BsuDetector.on_bar`, the `tvx_armed` long case uses only
`bar.low <= entry_price`; e.g. entry=100.20, whole bar
low=99.00/high=99.50 -> **Qwct returns touched** despite
high < entry. Short path analogously uses only
`bar.high >= entry_price`. At minimum a closed OHLC interval
must straddle the intended level (and even this would not
establish an order fill, due to spread and queue position).

### P0: TVX timing is not the official 30-seconds-before close

Official Gerchik says the limit entry is placed ~30 seconds BEFORE
BPU2 closes. The source-only Qwct detector transitions to
`tvx_armed` only AFTER accepting the entire BPU2 bar, then
checks for a hit in the **following** bar. This is a
different strategy. The code's `tick` precision label does not
fix the missing timing state transition and must not claim exact
TVX compatibility.

### P1: BPU1 exact-touch tolerance is not based on tick size

Current `bpu_tick_tol_atr=0.05` means 5% of ATR, not one or two
price ticks. For ATR=$8 the tolerance is $0.40, which is
40 ticks for a $0.01-quoted US stock. This conflicts with an
"exact touch" requirement and cannot be corrected by relabeling.

### P1: required immediate BPU2 sequence is not timestamp-checked

`BsuDetector._bpu2_expected_ts` is assigned `None` but never used.
The detector accepts the next *delivered* `Bar` regardless of the
elapsed interval or skipped/missing candle. It has no robust
invalidation for delayed/missing BPU2.

### P1: M5 breakout and bounce checks do not implement BSU/BPU

`signals._check_m5` accepts breakout simply if last close is on
the breakout side; bounce simply if last high-low straddles a
level and close is on the desired side. They do not require
BPU1/BPU2 geometry, prior-day scenario provenance, execution
timing, spread or no-chase checks.

### P1: no-chase and risk approval still incomplete

`max_entry_distance_atr`, `max_spread_bps`, native
portfolio exposure/cash/risk-manager constraints remain
unwired in the decision chain. `risk_approved=True` means
preliminary affordability with `risk_mgr=None`, not
authorization to trade or a broker-protected entry.

### P1: ATR methodology is unresolved, not interchangeable

Qwct uses 14-period native Wilder true range. Multiple open
Gerchik-labelled TradingView indicators describe a 5-D1
range variant, sometimes with abnormal-bar exclusions. Changing
ATR changes every ATR-based threshold and position geometry.
Neither external code nor the brand label alone establishes which
parameterization the owner intended; preserve current config until
the source specification resolves the choice.

## Safe next steps WITHOUT making the user the test runner

1. Write pure unit tests that **FAIL on present code** for the
   BPU2 wick-piercing, TVX no-cross price-touch, exact tick
   tolerance and missing-bar immediate-sequence cases.
   Keep tests as evidence before proposing a patch.
2. Resolve D1 BPU pattern vs M5 confirmation boundaries and
   the source's 30-second TVX instruction. Minute backtests
   cannot be represented as validating a 30-second preclose
   signal; do not invent intraminute prices or fills.
3. Compare open Pine code and license constraints; port only
   independently tested, relevant algorithms, not a third
   party's entire broker integration or a proprietary strategy.
4. Establish a documented ATR variant for the Gerchik setup
   while preserving current explicit Qwct ATR(14) contract
   until an authorized decision to change it.
5. One single scoped native LEAN research run after source-level
   blockers have been independently addressed; zero orders.

Nothing here certifies a full strategy, a useful signal, or a
safe Schwab execution path.
