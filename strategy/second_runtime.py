"""LEAN on_data read-only SEC TradeBar bridge for Gerchik BPU2 TVX.

No native subscription or homemade feed here; main.py owns data. Never
use minute/fill-forward/synthetic data. LEAN invokes consolidation event
handlers before on_data; BPU1's completed M5 event can arm the window
before the following SEC TradeBars are delivered. A bar ENDING at
HH:MM:30 is complete; never use a prior Scheduled Event at that time.
"""
from .native_second_tvx import NativeSecondTvxWindow


def process_second_slice(self, data, time_index):
    if not (getattr(self, "_tvx_seconds_enabled", False)
            and self._signals_open):
        return
    bars = getattr(data, "bars", None)
    if bars is None:
        return
    for symbol, bar in bars.items():
        if symbol not in self.screen_watchlist:
            continue
        state = self._symbols.get(symbol)
        if state is None or state.get("bsu_link") is None:
            continue
        window = state.get("tvx_sec_window")
        if not isinstance(window, NativeSecondTvxWindow):
            continue
        if window.complete or window.blocked_reason:
            continue
        end_at = time_index(bar.end_time)
        if end_at.date() != self._session_date:
            continue
        if not (window.bpu1_end < end_at <= window.cutoff):
            continue
        before_block = window.blocked_reason
        sample = window.accept(
            bar, symbol=symbol, end_at=end_at.to_pydatetime())
        if window.blocked_reason and not before_block:
            self._tvx_second_reasons[window.blocked_reason] += 1
            self._record(
                symbol, "TVX_SEC_BLOCKED", model="bounce",
                reason=window.blocked_reason + "; NO ORDERS")
            continue
        if sample is None:
            continue
        detector = state["bsu_link"].detector
        try:
            if (detector.state.phase != "bpu1" or
                    detector.state.bpu1_ts != sample.observed_since):
                raise ValueError("BPU1_PRE_CLOSE_STATE_STALE")
            observed = detector.observe_preclose(
                observed_at=sample.observed_at,
                bpu2_end=sample.bpu2_end,
                observed_low=sample.observed_low,
                observed_high=sample.observed_high,
                last_price=sample.last_price,
                source=sample.source,
                observed_since=sample.observed_since)
            if observed.phase == "preclose_candidate":
                self._tvx_preclose_count += 1
                self._record(
                    symbol, "TVX_SEC_PRE_CLOSE", model="bounce",
                    side=observed.side, level=observed.level_price,
                    entry=observed.entry_price,
                    stop=observed.stop_price,
                    risk=abs(observed.entry_price - observed.stop_price),
                    reason=(
                        f"native {sample.observed_bars} traded SEC bars "
                        f"({sample.unobserved_seconds} seconds without a bar); "
                        f"actual last SEC trade={sample.last_price}; "
                        f"real cutoff={sample.observed_at}; "
                        f"BPU2 ends {sample.bpu2_end}; "
                        "risk/broker authorization UNKNOWN; "
                        "provisional only; NO ORDERS OR FILLS"))
            else:
                self._tvx_second_reasons[observed.reason] += 1
                self._record(
                    symbol, "TVX_SEC_INVALIDATED", model="bounce",
                    reason=observed.reason + "; NO ORDERS")
        except (ValueError, TypeError, AttributeError) as exc:
            detector._invalidate("TVX_NATIVE_PRECLOSE_ERROR: " + str(exc)[:120])
            self._tvx_second_reasons["TVX_NATIVE_PRECLOSE_ERROR"] += 1
            self._record(symbol, "TVX_SEC_INVALIDATED", model="bounce",
                         reason=str(exc)[:150] + "; NO ORDERS")
