"""LEAN on_data read-only SEC TradeBar bridge for Gerchik BPU2 TVX.

No native subscription or homemade feed here; main.py owns data. Never
use minute/fill-forward/synthetic data. LEAN invokes consolidation event
handlers before on_data; BPU1's completed M5 event can arm the window
before the following SEC TradeBars are delivered. A bar ENDING at
HH:MM:30 is complete; never use a prior Scheduled Event at that time.
"""
from .native_second_tvx import NativeSecondTvxWindow
from .preclose_review import review_preclose
from .corporate_action_guard import split_research_blocked
from .native_m5_validation import _duration_seconds


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
        if (_duration_seconds(getattr(bar, "period", None)) == 1
                and getattr(bar, "symbol", None) == symbol):
            self._native_sec_received += 1
        state = self._symbols.get(symbol)
        if (state is None or state.get("bsu_link") is None
                or split_research_blocked(state, self._session_date)):
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
        # A bar with EndTime=-30s that only arrives on a LATER
        # Slice can never be treated as a tradable -30s decision.
        # Native OnData callback time must equal the actual bar end.
        if time_index(self.time) != end_at:
            window.blocked_reason = "SEC_DELAYED_OR_FUTURE_SLICE"
            self._tvx_second_reasons[window.blocked_reason] += 1
            self._record(symbol, "TVX_SEC_BLOCKED", model="bounce",
                         reason=window.blocked_reason + "; NO ORDERS")
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
        # This counts genuine completed SEC cutoff windows, not TVX
        # acceptance, a BPU2 confirmation, or broker authorization.
        self._tvx_cutoff_samples += 1
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
                # This independent checkpoint is evaluated NOW using
                # frozen D1 and ALREADY CLOSED M5 through BPU1. The
                # subsequent closed BPU2 cannot be used retroactively
                # to approve a -30s risk or session decision.
                try:
                    decision = state.get("decision")
                    if decision is None or not decision.accepted:
                        raise ValueError("frozen accepted morning bounce missing")
                    d1 = self._frame(state["daily_rows"])
                    d1 = d1.loc[d1.index < sample.observed_at.replace(
                        hour=0, minute=0, second=0, microsecond=0)]
                    m5 = self._frame(state["m5_rows"])
                    m5 = m5.loc[m5.index <= sample.observed_since]
                    review = review_preclose(
                        decision=decision, link=state["bsu_link"],
                        detector_state=observed, sample=sample,
                        d1=d1, closed_m5=m5,
                        levels=state.get("session_levels"), cfg=self.cfg,
                        equity=float(self.portfolio.total_portfolio_value),
                        session_policy=self._session_policy)
                    state["preclose_review"] = review
                    status = ("OBSERVABLE_READY" if review.evidence_ready
                              else "BLOCKED")
                    self._record(
                        symbol, "TVX_PRECLOSE_REVIEW", model="bounce",
                        side=review.side, level=observed.level_price,
                        entry=review.limit_price, stop=review.stop_price,
                        risk=review.planned_risk_usd,
                        reason=(f"{status} at {sample.observed_at}; "
                                f"checks={dict(review.checks)}; "
                                f"blockers={'; '.join(review.blockers)[:240]}; "
                                "BROKER RISK UNKNOWN; NO ORDERS"))
                except (ValueError, AttributeError, TypeError, KeyError,
                        OverflowError, IndexError) as exc:
                    state["preclose_review"] = None
                    self._record(
                        symbol, "TVX_PRECLOSE_REVIEW", model="bounce",
                        reason="BLOCKED: unable to evaluate strictly as-of "
                               + str(exc)[:160] + "; NO ORDERS")
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
