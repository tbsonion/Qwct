# Native LEAN → Gerchik BSU/BPU research integration (2026-10-10)

**Integration scope:** The previously isolated `BsuDetector` is now
actually called from Qwct `main.py` for closed **native M5**
observations on selected D1 **bounce** scenarios. This is **NOT**
a fully certified or executable Gerchik TVX strategy.

## Research and API evidence

- Original pattern: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
  BPU1 exact level touch; BPU2 immediately next, no piercing BPU1;
  luft at most 20% stop; TVX limit ~30 seconds BEFORE BPU2
  closes. No claim that a later closed M5 demonstrates TVX.
- LEAN native symbol tick size:
  https://www.quantconnect.com/docs/v2/writing-algorithms/securities/key-concepts
  `self.securities[symbol].symbol_properties.minimum_price_variation`.
  The value comes from LEAN, not a hard-coded $0.01.
- LEAN time-period consolidation:
  https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
  Native `self.consolidate(symbol, timedelta(minutes=5), ...)`
  yields completed M5 TradeBars; end_time used. Does not
  provide a verified price 30s before completion.
- US equity resolution matrix:
  https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
  SECOND and TICK exist as separate source subscriptions.
  Existing Qwct UniverseSettings remains MINUTE, which cannot
  prove an intraminute :30 preclose event. No new data feed
  or ad hoc timer was added.

## Native input → explicit provenance

1. `main.py::_append_daily` now preserves actual LEAN D1
   `bar.end_time` in each `daily_rows` as `bar_end`; never guess
   market close from a hard-coded clock.
2. The morning D1 scanner freezes `levels_for_session(...)`
   and selects a D1 scenario. For an accepted bounce on
   support/long or resistance/short, the bridge validates:
   **(a)** level.source=`swing_cluster`, first and last
   distinct confirmed D1 swing indices, valid_from <= session,
   formed_at matching last source date;
   **(b)** actual originating D1 low/high within half of the
   native LEAN price tick of the detected level;
   **(c)** native timezone-aware first and latest D1 close
   timestamps both earlier than the 09:29 decision;
   **(d)** native D1 ATR snapshot ready and native tick positive.
   It fails closed if evidence is absent or inconsistent.
3. This traced D1 swing is explicitly named
   `D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU`.
   An algorithmic cluster of pivots is NOT the same as a
   human-labelled Gerchik BSU. It is a **research hypothesis**
   with genuine source-bar evidence, not fabricated history.
4. A separate BsuDetector per symbol, reset every session,
   consumes actual native 5-minute completed OHLCV bars via
   `BsuDetector.on_bar(ResearchBpuBar(...))`.
   Bar order, interval, exact native price touch and wick
   invalidation are checked by the already tested detector.
5. When completed BPU2 is observed, the journal records
   `BSU_PROXY_BPU2_CLOSED` with source time and explicit
   `NO 30s TVX observation, NO ORDERS OR FILLS`. A separate
   statistic/chart tracks these observations.
6. The existing `RESEARCH_CANDIDATE` shortcut now explicitly
   **excludes bounce**: a simplified two-bar M5 bounce must
   not be treated as a fully validated BSU/BPU/TVX opportunity.
   Risk approval still returns UNKNOWN without actual native
   RiskManager checks, so no approved trade is submitted.

## Deterministic test coverage

`tests/test_bsu_native_bridge.py` tests:
- actual D1 source bar_end and native tick origin matching;
- long support and short resistance compatibility;
- closed BPU1→BPU2 progression without imaginary preclose;
- mismatched median level price vs actual originating swing;
- missing/malformed native time, ATR and tick;
- unconfirmed/future level and erroneous origin date;
- rejecting the other two D1 models and mismatched sides;
- static main.py actual import, native tick accessor and M5 callback;
- source hard-coded trading kill switch and no preclose generation.

Known earlier tests in `tests/test_patterns_bsu.py` also prove
wick failures, out-of-sequence bars and exact 30s observation
requirements.

## Open blocking issues (not quietly solved)

- **30-second TVX is NOT wired**: would need verified native
  SECOND or TICK subscription and actual BPU2 cumulative price
  range with correct start/end provenance. That is a separate
  research feature, not equivalent to a minute History bar
  or LEAN scheduled event. Must validate provider access,
  market-data callback timing, coverage and cost before enabling.
- **True BSU identity**: the current D1 origin is a strict
  confirmed-swing proxy with exact native price association,
  not a reviewed discretionary BSU classification. Origin
  ambiguities and split-adjusted historical prices can cause
  legitimate candidates to be skipped, by design.
- **No real LEAN Cloud integration evidence** for this commit;
  pure Python CI and main.py source checks do not prove
  the native consolidator emits the expected data at runtime.
- **Full position/risk limits, Schwab stop/partial-fill semantics,
  spread/no-chase, report export, and profitability** have not
  been certified here. No orders, no merge, no broker connection.

**Do not claim full Gerchik implementation or backtest success.**
