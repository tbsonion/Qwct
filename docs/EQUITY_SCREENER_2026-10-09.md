# Qwct automatic US-equity screener — official LEAN documentation check

Checked: 2026-10-09. Work on a separate feature branch; **not executed
inside a real LEAN instance and not merged** at the time of this note.

## User's Gerchik LMS filter

Source of truth: `docs/strategy_spec.md` §2 and
`strategy/config.py`: liquid US stocks, prior D1 price > $5,
daily ATR(14) >= $1, average daily share volume over 20 D1 sessions >=
500,000. Manual/familiar stock knowledge cannot be inferred from price data.
Strategy limit/money management is *not part of* this screener.

## Why native LEAN, not another stock-scanning service

Official QuantConnect APIs provide:
1. **Current Fundamental Universe** `self.add_universe(self._select_screen_universe)`
   with `Fundamental.price`, `Fundamental.volume`,
   `Fundamental.dollar_volume`, `Fundamental.symbol`,
   `has_fundamental_data`. LEAN manages constituent subscriptions.
2. `self.on_securities_changed(changes)` for new/removed symbols.
3. `self.history[TradeBar](symbols, n, Resolution.DAILY)` for history
   warmup when constituents are added.
4. `AverageTrueRange(14, MovingAverageType.WILDERS)` and
   `SimpleMovingAverage(20)` for ATR and 20-day mean share volume.
   The SMA is updated on **daily bar.volume**, not on prices and not
   on dollar volume.
5. `self.on_data` receives daily bars for daily-resolution symbols.
6. `UniverseSettings.Resolution = Resolution.DAILY`; keep bounded
   subscriptions. `asynchronous=False` avoids stale mutation issues
   because this initial implementation updates the universe rank.

Official references:
- Fundamental Universes (new API, not deprecated CoarseFundamental two-stage):
  https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes
- US Equity Coarse Universe data fields:
  https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-coarse-universe
- Universe event handling:
  https://www.quantconnect.com/docs/v2/writing-algorithms/universes/key-concepts
- Universe Settings (daily data, asynchronous caveats, normalization):
  https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings
- ATR manual native indicator:
  https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/average-true-range
- Native manual indicators:
  https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/manual-indicators

## How the selection works TODAY

- First (daily LEAN Fundamental feed): require
  `f.has_fundamental_data`, `f.price > 5`,
  `f.volume >= 500_000`, finite positive `f.dollar_volume`.
  Sort descending by dollar volume and take maximum **50** symbols.
  This is a **conservative one-day-volume prefilter**, not an exact
  marketwide 20-day-average-volume screen. A stock with 450k volume on the
  latest session but 800k 20-day average will be excluded.
- Next (native closed daily bars per subscribed stock):
  update native ATR(14) and native SMA(20) of *daily share volume*.
  Check **latest closed D1 price > $5, ATR>=1.0, V20>=500k**.
  Reject NaN, infinite, missing, unready or stale history; no
  guessed indicator value.
- At premarket `_prepare_session`: rank qualifying symbols using native
  universe liquidity order, print top **10** with price, ATR and V20,
  expose the actual `screen_watchlist` tuple of LEAN `Symbol` objects.
  This is **not a ranking of Gerchik setups**; D1 level + M5 gate scoring
  is separate.
- The original anchor symbol (`symbol` param, default AAPL) still runs
  the existing **single-symbol Gerchik signal-only path**. Scanned symbols
  are **not** yet wired into that per-symbol signal evaluation.
- The same manually added minute-resolution anchor must never feed M1
  bars into daily ATR; its daily consolidated bar handles that ticker.

## Known limitations — do not claim full ready

- **Native LEAN integration test absent.** The GitHub tests verify pure
  filtering only; real `Fundamental` event schema, daily history/
  `on_securities_changed` sequencing, split handling and close timing
  need runtime smoke verification.
- `has_fundamental_data` may exclude stocks/ETFs without associated
  corporate fundamentals; user may want separate ticker allowlist.
- Universe caps (50 candidates, 10 watchlist) are **operational defaults**,
  not rules from the training course. Need observe actual hit rates and
  resource usage before changing.
- Fundamental's single prior-session volume prefilter is intentionally
  stricter than exact 20-day average across all US stocks.
- No M5 subscriptions or signals for watchlist members, no automatic
  ticker substitution into existing D1/M5 logic, no dynamic sector/news,
  spread/stale-quote screener, no "familiar instrument" allowlist.
- Corporate-action adjustment compatibility with `SPLIT_ADJUSTED`
  D1 indicator warmup needs actual LEAN verification.
- No transactions, stop/TP changes, broker credentials, or risk engine.
  The strategy remains signal-only.

## Acceptance for next agent

1. Native LEAN runtime shows daily universe candidate changes and
   an ET pre-open watchlist with real price / ATR / V20.
2. Validate that **all inputs came from closed D1 data**; no live
   intraday/future values in scan criteria.
3. Test removals/re-additions, no data, splits and price/volume thresholds.
4. Only then connect selected symbols to **per-symbol Gerchik** D1/M5
   analysis; keep order execution disabled until broker-native protective
   behavior is separately verified.
5. Do not copy obsolete `CoarseFundamental` two-function universe APIs,
   create another API client, calculate ATR manually, or write an OMS.
