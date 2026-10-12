# Gerchik BSU → BPU1 → BPU2 → −30s TVX: LEAN SECOND research

**PR #7, 2026-10-11. Research code only.** No trades, no mock orders,
no backtested performance, and no native Cloud backtest claimed.

## Verified existing components before implementation

Original Gerchik BPU rules: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
- Exact tick-level BPU1 hit; BPU2 immediate next M5 does not
  pierce BPU1 extreme; BPU2 allowable luft 20% of stop.
- **TVX is evaluated 30 seconds before BPU2 CLOSE.**
- D1 swing proxy is not identical to a discretionary original BSU.

Official LEAN APIs (not custom feed/consolidators):
- https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
  — US Equity supports `Resolution.SECOND` TradeBars, default fill-forward.
- https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
  — native 5-minute Consolidate from a SECOND source.
- https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events
  — Scheduled Events execute **before** consolidators and on_data;
  a scheduled 09:34:30 callback cannot read that second's new bar.
  This code observes the actual completed SEC bar in on_data instead.
- https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings
  — `UniverseSettings.Resolution` applies to members of Fundamental Universe.

External ready-made Gerchik code inspected as reference only, NOT
copied or presented as a verified intrabar TVX:
- Apache 2.0 levels https://github.com/BulatNS31/SwingTraderAI/blob/main/swingtraderai/indicators/bsu_bpu_levels.py
  — ATR-tolerant historical BSU/BPU touch counts, no preclose TVX;
  it cannot replace native original-pivot/tick-level precision.
- https://github.com/jhnbek/botArtjahan/blob/main/knowledge_bot/scn003_bsu_bpu_m5_backtest.py
  — D1/M5 level selection, BPU1+BPU2, 20% luft, but **simulates
  fills** after reviewing complete M5 and cannot prove original TVX
  30 seconds early. Its trade simulator was NOT imported.
- https://github.com/LeonidCharikov/MyTradingBot/blob/master/analyzer.py
  — BPU2 **postclose** detection, no exact intrabar TVX.

## Native Qwct approach

Default runs use existing `Resolution.MINUTE` Fundamental Universe,
the same previously tested LEAN native M5/D1 consolidators, and
**do not claim** any 30-second TVX observation.

**Opt-in for dense one-second research backtest:** add a QuantConnect
project parameter `tvx_seconds=true` before starting a Cloud backtest.
Then the **native universe** uses `Resolution.SECOND` for its existing
members; **existing native** `self.consolidate(symbol, timedelta(minutes=5), ...)`
produces completed M5 bars and `self.consolidate(symbol, Resolution.DAILY, ...)`
produces D1. No second subscription for an already-subscribed symbol.

**2026-10-11 documentation audit correction:** SEC mode now
explicitly limits the native universe to the top
`StrategyConfig.screener_watchlist_limit` (10) liquidity candidates
rather than the usual 50-minute universe members, to bound Cloud load.
**Trade-off:** narrowing from 50 to 10 BEFORE stage-2 D1 screening
can miss valid setups further down the original candidate list. This is
an opt-in research subset, not a like-for-like universe backtest.
The manually subscribed clock symbol now ALSO requests
`Resolution.SECOND` when SEC mode is enabled, avoiding an overlapping
minute-only clock feed if the anchor belongs to the universe.
Even ten symbols of SEC data may overwhelm Cloud Free, and historical
SEC dataset subscription access/latency have not been validated in a
native LEAN Cloud run. Do not claim 30-second signal detection is
operational on actual market data until such a run passes.

The `main.py::on_data(Slice)` handler calls
`strategy/second_runtime.py::process_second_slice`. Only symbols
selected for the day's D1 watchlist with a native BSU proxy
(and BPU1 already closed) are inspected. For other symbols no
intrabar price signal is fabricated.

`strategy/m5_runtime.py::process_m5` after a native-validated M5 BPU1
arms one `NativeSecondTvxWindow`, ending at `BPU1_end + 5min - 30s`.
`strategy/native_second_tvx.py` is a **strict observation window**,
not a feed or consolidator. Native SECOND data are **sparse**:
QuantConnect may not publish a TradeBar for a one-second interval
without any qualifying price-setting trades. The revised window
accepts genuinely observed completed `Time`, `EndTime`, `Period=1s`
bars and sums *actual* traded highs, lows and latest prices. It
permits at most a **10-second unobserved interval** between received
bars (conservative research default, not an original Gerchik number).
It counts missing seconds and never creates fake prices for them.
A genuine traded one-second bar ending **exactly 30s before close**
is still mandatory; without that precise observation, no preclose
signal is authorized. Gaps over 10s, duplicates, delayed bars,
fill-forward, wrong symbols, zero-volume, bad OHLC, or a minute
subscription fail closed. The 10s tolerance balances false negatives
from legitimate sparse prices with the risk of undetected feed stalls,
which must be tested on real Cloud SEC data. It is NOT an assurance
that an omitted bar could not represent a provider outage.

At the completed SECOND bar ending exactly at `HH:MM:30`,
`BsuDetector.observe_preclose(...source="SEC", observed_since=BPU1_end)`
runs immediately. It evaluates the existing tick-level BPU1 extreme,
the 20% luft rule, and records `TVX_SEC_PRE_CLOSE` ONLY as
**provisional evidence**, with `can_submit=False`.

On the subsequent completed native M5 BPU2, the existing
`BsuDetector.on_bar` checks the final high and low also contain
the previously observed partial SEC extremes, and that final M5
has not pierced BPU1 or missed allowable luft. Only then are both
`TVX_SEC_PRE_CLOSE` and `BSU_PROXY_BPU2_CLOSED` counted as
reconciled. A violating closed M5 invalidates prior preliminary
research evidence. If SEC mode was off/unavailable, it produces
a closed BPU2 PROXY record but explicitly says no verified −30s TVX.

**Critical:** a native SEC −30s sample is NOT an order, limit fill,
proof of actual entry price or complete Gerchik BSU. The existing
D1 swing proxy, missing Schwab protective-stop and partial-fill
guarantees, full trade risk gates and split normalization remain
separate validation blockers.

All native orders remain source-level disabled; nothing changed in
native EOD cancellation, liquidation or ticket state management.

## Tests / validation

`tests/test_native_second_tvx_integration.py` drives **the same
extracted M5 and SECOND Slice handlers used by main.py**, with
deterministic native-shaped SEC observations. It checks exact
preclose timestamp, allowing missing trade-free seconds with bounded
gaps but never fabricating data, no future M5, final M5 consistency,
disabled mode, excessive 10s gaps, and absent cutoff bar,
zero-volume/fill-forward/wrong-period, other-symbol contamination,
duplicate and early input, mid-BPU2 price penetration and invalidation
surviving the next completed M5. Reports count provisional and
reconciled research events separately.

GitHub Python tests are deterministic fixtures, NOT a native LEAN
Cloud run; a real SEC historical backtest on an explicitly limited
universe/period is still required to validate data availability,
timestamp conversions, BPU2 time, calendar and normalization.


## Documentation-based audit corrections (2026-10-11)

Official `get_parameter("tvx_seconds")` returns a string by default
(https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters);
`Slice.bars.items()` is the supported LEAN Python API
(https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/python-and-lean).
The event ordering remains Schedule -> Consolidators -> OnData.
A scheduled callback at `10:39:30` must NOT fetch the still-undelivered
native 10:39:30 SEC candle. The SEC adapter uses actual OnData only.

On a BPU2 M5 close with a missing exact -30s bar, the runtime now
emits `SEC_PRECLOSE_CUTOFF_NOT_OBSERVED` and counts a failure,
even if the preceding 269 seconds were complete. It never
reconstructs the missing sample from full M5 future OHLC.
Consecutive traded seconds are stricter than actual minimum necessary
market observation and can produce false negatives when no real trade
occurs in a one-second bucket. No 0-volume synthetic fillers allowed.

**Full model versus legacy bounce gate:** `signals.py::_check_m5`
still exposes the original two-bar *price-action proxy* for regression
and other research. However a `bounce` trade intent's
`m5_confirmed` gate may no longer use it to claim a complete Gerchik
setup. `strategy/bpu_tvx_evidence.py::BpuTvxEvidence` binds **the
same symbol, morning D1 level, session, long/short, BPU1 end, observed
native SEC cutoff and subsequent reconciled BPU2 M5 end**. Without
this exact proof, the eighth-gate strategy remains blocked.
An existing `BsuResearchLink` with a historical swing origin is
still explicitly *a proxy*, not a verified discretionary BSU.

**Limit / stop pricing audit:** prior bounce intent calculation used
the approximate D1 cluster median as entry price. The native
BPU observer instead calculates the Gerchik limit offset of **20% of
the origin-level-to-stop distance** from the actual source BPU level,
for BOTH long and short. New native TVX evidence contains the
observer's actual `entry_price`, `stop_price` and actual last
observed **-30s SEC price**. Upon a matching M5-final-reconciled
candidate, both `TradeIntent` sizing and the mechanical entry/stop/
risk gates use those same evidenced prices; no-chase compares to the
real last -30s SEC close, not the final BPU2 close 30 seconds later
(which would be look-ahead for the proposed earlier limit entry).
Any different `luft_pct_of_stop` configuration from 20% fails closed.

**Risk and provenance still unresolved:** QuantConnect's
`DataNormalizationMode.SPLIT_ADJUSTED` rewrites historical
price scales; the native market's `minimum_price_variation` reflects
the real tradable tick grid. Historical D1 origin and today M5 prices
need a real LEAN test around splits and tick rounding before declaring
the source BSU price reliable. The protective Schwab stop / actual fill
availability is UNKNOWN, never approved. Research gate success is not
proof of live entry, realized P&L or adherence to all discretionary
Gerchik rules.


## Critical second review: level identity and sparse feeds

A day-scoped D1 `swing_cluster` median is NOT necessarily the
same price as the originating native D1 swing extreme used to
recognize a Gerchik BPU1. The detector can still report exploratory
swing candidates at nearby clustered prices. But
`BpuTvxEvidence.matches` now **fails closed** if the cluster median
differs from the actual originating pivot by more than half of the
native minimum price variation. A backtest must never call these
different prices one valid BSU/BPU level merely because the D1
clustering tolerance is 0.25 ATR.

A historical D1 source extreme that does not fall on the current
native tick grid also fails closed in the BSU bridge, to reduce false
exact-touch claims in `SPLIT_ADJUSTED` history. This is a conservative
partial safeguard only: a split-adjusted historical value can
coincidentally land on the grid and STILL not represent an actual
price that traded at the historical date. Full correct normalization
requires a single as-of price basis through D1 history, streaming
M5/SEC, and corporate-action changes, and a native Cloud trial.
We have NOT quietly switched to `RAW`, which can make rolling D1
ATR/trend history discontinuous across actual splits unless
split handling/warmup resets are also implemented and validated.

The observed preclose candidate is available **before** BPU2 close,
but the complete eight-gate `m5_confirmed` evidence is produced
only at the subsequent BPU2 M5 close, **30 seconds later**. This is a
post-event reconciliation and CANNOT be used as the original
executable Gerchik limit-entry authorization without a separate
as-of-preclose (risk, level, broker protection) approval stage.
All Qwct order submission remains hard-disabled.


## Native tick rounding audit

A direct `0.2 * stop_distance` entry and `ATR * stop_buffer`
stop need not land on any exchange price increment, even if the
origin BSU is on the official native tick grid. Research-only
`BsuDetector` now rounds the stop **outward** from the BSU origin
(floor long, ceil short), recomputes the allowable 20% luft from
that conservative actual stop distance, and rounds the theoretical
limit to the nearest native tick. Both hypothetical limit and stop
must lie on this grid for `BpuTvxEvidence.matches` to pass;
the 20% equality is checked within half a native tick to allow
unavoidable rounding error, not exactly one floating-point cent.
Deterministic long/short tests include ATR=1.234, which previously
produced a non-tradable fractional-cent stop/limit.

**No price is represented as an actual executable broker quote**:
native tick rounding is necessary but not sufficient; spread, bid/ask,
venue tick rules, gaps, fills and Schwab stop protection remain
unverified. As of this review, there is no standalone preclose
eight-gate risk authorization at the original Gerchik TVX moment;
the final bounce gate is only an M5 retrospective reconciliation.
