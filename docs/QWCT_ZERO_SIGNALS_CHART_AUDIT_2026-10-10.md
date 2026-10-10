# Qwct zero-signal research diagnosis and LEAN charting (2026-10-10)

Status: DRAFT PR #6. This is native-API/source research, not a new
Cloud LEAN certification. Orders remain DISABLED.

## Reproduced evidence from last native LEAN Cloud backtest

- Window: 2024-01-01 through 2024-02-05;
  completed on LEAN 2.5.0.0.18178.
- 1,241,044 data points in 62.33 seconds.
- 10 screened liquid stocks per day, 18,240 native active-watchlist
  M5 callbacks, 456 evaluated M5 decisions.
- 6 D1 scenarios, 234 D1 REJECT events, 0 ERROR, 0 BSU proxies,
  0 completed BPU2 proxies, 0 research candidates, 0 orders.
- Flat $25,000 account **expected** for intentionally disabled trading.
- The screenshot was displaying `Strategy Equity`, not
  `Qwct Research`. Flat equity does not establish whether custom
  charts worked. An all-zero count chart still cannot inspect
  individual price-level behavior.

**Do NOT assert root cause from these counts alone.**
The prior summary had no model breakdown. It is possible that none
of the six D1 scenarios was a `bounce`, the only model eligible
for the standalone BSU observer. It is also possible that all
eligible bounces were blocked by source-level BSU checks.

## Verified source-level discrepancy: pivot vs cluster median

- `levels.py::detect_levels` clusters confirmed D1 swing highs/lows
  using **0.25 x MEDIAN of ready native D1 ATR snapshots**.
- A level price is the **median of all swing prices in its cluster**.
  This median can be a different price from the first actual native
  swing high/low.
- The old `bsu_bridge.py` rejected if `abs(native_first_pivot -
  cluster_median) > native_tick/2`. For a $0.01 min tick, a valid
  $100.00/$100.06 cluster (median $100.03) always failed, even
  though 3-cent separation is allowed by the ATR clustering rule.
- The bridge now keeps the *real originating D1 extreme* as
  `origin_price` (BsuDetector proxy level) and the separate
  screening `cluster_price`. No "exact BSU touch at the
  midpoint" is claimed. It rejects if that real pivot and cluster
  price disagree beyond the SAME validated historical native
  ATR-median tolerance as level construction.
- ATR used for BPU stop/luft remains the LATEST ready native
  daily ATR; ATR used for clustering remains historical-median.
  A regression test specifically checks that a temporary low
  current ATR cannot invalidate an otherwise confirmed cluster.
- The origin and cluster are **research proxies**, not certified
  discretionary Gerchik BSU/limit-player levels.
- No tick fill or 30-second-before-BPU2-close TVX is imputed.

## LEAN Chart API — exact documented pattern

Official native charting:
https://www.quantconnect.com/docs/v2/writing-algorithms/charting
and open Python LEAN source:
https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/CustomChartingAlgorithm.py

- Create chart with `Chart("Qwct Focus")`,
  `CandlestickSeries("M5", "$")`, and
  `Series(..., SeriesType.LINE/SCATTER, 0)`.
- Plot **native closed M5 TradeBar** using
  `self.plot("Qwct Focus", "M5", bar)`, not homemade OHLC
  or synthetic prices. Reuses the existing consolidated M5 callback.
- Single fixed stock: first qualifying watchlist stock from the
  first session, frozen for the whole run. This PREVENTS charting
  e.g. $200 TSLA then $50 NVDA on the same dollar-price axis.
  The ticker is displayed in `Qwct chart focus` runtime statistic.
- Separate three overlay series: nearest **frozen** daily level
  (or the actually accepted D1 scenario level for focus stock);
  BPU1 marker; BPU2 closed-proxy marker.
  BPU markers use the actual source swing pivot price, which may
  differ from the scenario's cluster-median level.
- Existing `Qwct Research` uses five series: Screener,
  D1 scenarios, Signal intents, Research candidates,
  Closed BPU2 proxies. Focus uses four more = **9 <=10**.
- On Cloud Free, 4,000 points per series. Native M5 candle
  plotting is limited to **3,500 points total**; the 25-day
  smoke (roughly <=2,000 per selected symbol) stays under quota.
  For one-year backtests the chart intentionally shows ONLY
  the first 3,500 M5 candles rather than silently exhausting
  the quota; the complete D1/M5 signals still run. No second
  ticker is mixed into that chart.
- The right-hand QuantConnect Select Chart selector must be
  switched from `Strategy Equity` to `Qwct Focus` for candles
  or `Qwct Research` for counters. Disabled orders imply
  flat Strategy Equity and no broker execution markers.

## Zero-signal diagnostics added

Counts distinguish:
- D1 accepted `breakout`, `bounce`, `false_breakout`;
- BSU proxy rejected due to explicit original `why` reason;
- native BPU1 touch observations vs completed BPU2 proxies;
- chosen chart ticker and charted M5 bar count;
- predominant BSU rejection and predominant M5 gate failure.

Final end-of-run log includes `D1 models=`, `BSU block reasons=`,
`native BPU1=`, `chart focus=`, `chart M5 drawn=`, and
`failed M5 gates=`. Critical aggregate numbers also appear
as native runtime statistics because LEAN Free logs may be
throttled or omitted from the terminal screenshot.

## Red-first tests, not speculative pass reports

1. Previously 5 tests failed against pre-fix Python code:
   cluster-median vs exact-tick, invalid cluster, short pivot,
   source chart declaration and absent diagnostics.
2. A second red-first test failed with a historical ATR-median
   cluster and anomalously low latest ATR.
3. After repairs and chart API cross-check, GitHub pure Python
   CI and `compileall` are expected to validate the new code;
   check their real completion status and count.
4. GitHub CI cannot run the user's QuantConnect Cloud LEAN
   subscribed US-equity market-data backtest or confirm that
   candlesticks render on the UI. That requires ONE scoped
   Cloud integration check when code is otherwise verified.

## Remaining known limitations

- Native BPU1/BPU2 observation only for accepted D1 bounce
  scenarios; it is not a full discretionary Gerchik scanner.
- A one-month cloud smoke cannot prove higher-timeframe
  strategy quality, missing risk manager, spread/queue behavior,
  30-second preclose TVX or profitability.
- Source-level tests assert intended chart API and state; they do
  not certify LEAN runtime visualization. No live order path
  is enabled.
- `Qwct Focus` is only ONE stock; a full multi-stock graphical
  gallery would require a separate research notebook or export
  system and may violate the Free chart-series quota.
