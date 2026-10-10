# BSU / BPU1 / BPU2 / TVX — corrected research-only contract

2026-10-10, branch `feat/schwab-protected-entry-preflight-20261009`,
inside draft PR #5. **No orders, no simulated fills, no Schwab access.**

## Ground truth

https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya (9 May 2024):

- BSU — historical bar that originated the level (may be well left of BPU1).
- BPU1 — precisely confirms/contacts that BSU level; it does NOT have
  to immediately follow BSU.
- BPU2 — the **next** candle after BPU1, on the same price plane,
  possibly missing the level by *no more than* a luft of 20% SL.
- BPU2 breaking BPU1's extreme destroys the model; false breakouts
  and misses beyond luft also invalidate it.
- TVX — planned limit order roughly **30 seconds BEFORE** BPU2's close,
  at the luft-adjusted level, rather than at BPU2 close or later.

The original web source does **NOT** provide an executable definition
of swing clustering, a stop-distance formula, tick-grid rounding,
or a broker-safe approach to provisional BPU2. Those remain
implementation assumptions, and are not called canonical Gerchik rules.

## Reviewed implementation

File: `strategy/patterns_bsu.py`.

- Requires an actual historical BSU timestamp and the symbol's native
  minimum tick size. It **does not** accept 5% of ATR as an 'exact
  touch' tolerance; half a native price tick is the float equality
  tolerance. Source data provenance still must be checked by caller.
- Validates finite positive OHLC, market-data timestamps with timezone,
  bars' time order, OHLC consistency and matching timeframes.
- Requires historical BSU bar to finish by the *start* of BPU1.
- Requires BPU2 close time exactly one native closed-bar interval after
  BPU1's close time; gaps/overnight transitions cannot be treated as
  proven contiguous without native exchange-calendar evidence.
- Checks BPU2 **high/low wick** against BPU1 extreme (not only close).
- Rejects BPU2 if it is too far from the intended level on the
  missing/touch side. For research, the existing configuration
  `stop_buffer_atr * native_ATR` estimates the stop-to-level distance;
  `luft_pct_of_stop` multiplies that distance. This is an explicit
  research convention pending a separately reviewed complete trade
  model, not a guarantee of real Gerchik stop placement.
- Closed BPU2 becomes `bpu2_confirmed` and is **not called TVX or fill**.
  OHLC of a subsequent bar is never used to retroactively claim a
  30-second-before-close entry or a market fill.
- An **optional, explicit** `observe_preclose` accepts a source tag
  `SEC`/`TICK`, native timestamp exactly 30 seconds before
  expected BPU2 close, externally sourced *cumulative* BPU2 OHLC with
  `observed_since` equal to BPU1 close, and last observed price.
  This is only a `preclose_candidate` and can be invalidated by
  the eventual BPU2 close.
- A single source tag and OHLC values **cannot prove that every
  underlying tick/sec was received**, that the provider did not
  forward-fill, that spread/queue/fees/halts allow a limit fill, or that
  the optional sample is genuinely native. Therefore
  `BsuState.can_submit` is permanently False.

## Verification

`tests/test_patterns_bsu.py` uses specified deterministic OHLC and
timestamp examples, including:

- long/short BPU1 beyond native tick tolerance;
- long/short BPU2 *wick* violations despite returning close;
- long/short misses by more than luft;
- missing/interleaved timeframes, duplicate bar, overlapping BSU/BPU1;
- invalid OHLC, missing timezone, unknown BSU time and missing tick size;
- closed BPU2 and subsequent price touching level **cannot** imply TVX;
- exact preclose timestamp, subminute source, post-BPU1 feasibility,
  and full-interval provenance requirements;
- provisional preclose candidate invalidated by later BPU2 data;
- no path where pure research can submit an order.

Tests were committed FIRST and failed against old code, then the
detector was rewritten and the Python CI re-run. Pure Python test
success DOES NOT constitute LEAN/Schwab execution certification.

## Still open — no misleading green status

1. **NOT wired into `main.py`:** the existing D1 swing-level scanner
   and M5 `_check_m5` are separate approximate rules. Merely fixing
   an unused detector does not prove main Qwct emits correct BSU signals.
   Before wiring, require actual BSU source-bar provenance, native tick
   size for the security, correct native closed-bar timestamps, and
   same-session vs cross-session native exchange-hours handling.
2. **No native second/tick research feed installed or validated:**
   the existing free-minute QuantConnect project cannot prove TVX
   at :30 seconds. A later native data source and verified observation
   subscription are required; do not synthesize half-minute prices.
3. **TVX stop/luft semantics and tick-aligned limit price:** The
   current planned stop is ATR-derived and not a verified broker stop.
   The source does not define a unique formula for rounding the
   '20% Stop Loss' into tick prices. Do not claim correct executable
   limit prices until this is resolved and verified.
4. **Core signal/risk issues from LEAN audit remain open**: 8 gates,
   scenario model evidence, native buying power/limits, report exports,
   and Schwab bracket/partial-fill protection are separate work.
5. **No backtest or profitability run for this change**. The latest
   user-provided Cloud LEAN smoke predated these BSU corrections.

Original source code remains unmerged in draft PR #5.
