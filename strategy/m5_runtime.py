"""M5 native LEAN research callback implementation. No orders. """
from .data import MarketData
from .native_m5_validation import validate_m5_tradebar
from .patterns_bsu import Bar as ResearchBpuBar
from .signals import build_intent, GateResult
from .lean_risk_observer import review_native_lean_risk
from .protected_entry import review_schwab_protected_entry
from .native_second_tvx import NativeSecondTvxWindow
from .bpu_tvx_evidence import BpuTvxEvidence
from .corporate_action_guard import split_research_blocked

def process_m5(self, bar, time_index):
    symbol = bar.symbol
    if (not self._signals_open or
            symbol not in self.screen_watchlist or
            time_index(bar.end_time).date() != self._session_date):
        return
    state = self._symbols.get(symbol)
    if state is None or split_research_blocked(state, self._session_date):
        return
    # LEAN event callbacks can be repeated or delayed. A repeated
    # completed candle must never count as a second BPU or a new
    # research candidate (and delayed out-of-order evidence cannot
    # rewrite earlier M5 state). This check precedes all pattern logic.
    native_end = time_index(bar.end_time)
    if (state["m5_rows"]
            and native_end <= state["m5_rows"][-1]["date"]):
        self._m5_input_rejections["M5_DUPLICATE_OR_OUT_OF_ORDER"] += 1
        return
    # M5 OHLCV is real data evidence, never an interpolation. Reject a
    # zero-volume, fill-forward or malformed native candle BEFORE feeding
    # either BSU/BPU research or the regular two-bar signal proxy.
    valid_m5, rejection = validate_m5_tradebar(
        bar, native_end.to_pydatetime())
    if not valid_m5:
        self._m5_input_rejections[rejection] += 1
        return
    self._m5_bars_seen += 1
    state["m5_rows"].append({
        "date": time_index(bar.end_time),
        "open": float(bar.open), "high": float(bar.high),
        "low": float(bar.low), "close": float(bar.close),
        "volume": float(bar.volume)})
    state["m5_rows"] = state["m5_rows"][-80:]
    breakout_observer = state.get("breakout_retest")
    if breakout_observer is not None:
        try:
            phase_before = breakout_observer.phase
            outcome = breakout_observer.on_m5(
                at=native_end.to_pydatetime(),
                open_price=float(bar.open), high=float(bar.high),
                low=float(bar.low), close=float(bar.close),
                volume=float(bar.volume))
            if outcome.phase != phase_before:
                self._breakout_retest_counts[outcome.phase] += 1
                self._record(
                    symbol, "BREAKOUT_STAGE", model="breakout",
                    side=outcome.side, level=outcome.level_price,
                    reason=outcome.reason + "; research only; NO ORDERS")
        except Exception as exc:
            # No observer evidence means the breakout M5 gate stays FALSE.
            state["breakout_retest"] = None
            self._record(
                symbol, "ERROR", reason="Breakout M5 research error: "
                + str(exc)[:200])
            self.error(f"Breakout research error {symbol}: {exc}")
    focus_charted_this_bar = (
        symbol == self._chart_symbol and self._focus_m5_plotted < 3500)
    if focus_charted_this_bar:
        # QuantConnect official CandlestickSeries accepts the native
        # completed TradeBar directly; no synthetic OHLC data.
        self.plot("Qwct Focus", "M5", bar)
        if state["focus_level"] is not None:
            self.plot("Qwct Focus", "D1 Level", state["focus_level"])
        self._focus_m5_plotted += 1
    # Observe closed native M5 BPU1/BPU2 independently of breakout.
    # A native SECOND source (when opted in) supplies a separate
    # preliminary -30s TVX. M5 after the cutoff only reconciles it.
    link = state["bsu_link"]
    if link is not None:
        try:
            # Measure every native M5 extreme against the exact traced
            # historical BSU pivot, not the clustered D1 median. Neither
            # a wick crossing nor an approximate price is a BPU1 touch.
            audit = state.get("touch_audit")
            if audit is not None:
                audit.observe(
                    time_index(bar.end_time).to_pydatetime(),
                    low=float(bar.low), high=float(bar.high),
                    close=float(bar.close))
                if getattr(self, "_case_scan", False):
                    # Bounded as-of scan ranking; uses only completed
                    # native RAW M5 candles already passed to BPU.
                    case = (abs(audit.closest_gap), symbol.value,
                            str(self._session_date), audit.level,
                            audit.closest_extreme, audit.closest_gap,
                            audit.nearest_time[11:16], audit.touches)
                    self._bsu_scan_best = sorted(
                        (r for r in self._bsu_scan_best
                         if r[1:3] != case[1:3]), key=lambda r: r[0])
                    self._bsu_scan_best.append(case)
                    self._bsu_scan_best.sort()
                    self._bsu_scan_best = self._bsu_scan_best[:5]
            if link.detector.state.phase == "invalidated":
                sec_window = state.get("tvx_sec_window")
                # A failed pre-close SEC check must NOT be erased by a
                # M5 reset at the very BPU2 close that it invalidated.
                if (sec_window is None or
                        native_end.to_pydatetime() > sec_window.bpu2_end):
                    link.detector.reset()
                    state["tvx_sec_window"] = None
                    state["bsu_tvx_evidence"] = None
            # LEAN supplies no TradeBar for a second without trades.
            # If the exact -30s source candle never arrived, record
            # that gap only when the genuine M5 BPU2 closes. Never
            # reconstruct it using BPU2's future complete OHLC.
            win = state.get("tvx_sec_window")
            if (getattr(self, "_tvx_seconds_enabled", False)
                    and isinstance(win, NativeSecondTvxWindow)
                    and native_end.to_pydatetime() == win.bpu2_end
                    and not win.complete and not win.blocked_reason
                    and link.detector.state.phase == "bpu1"):
                win.blocked_reason = "SEC_PRECLOSE_CUTOFF_NOT_OBSERVED"
                self._tvx_second_reasons[win.blocked_reason] += 1
                self._record(
                    symbol, "TVX_SEC_BLOCKED", model="bounce",
                    reason=win.blocked_reason + "; NO ORDERS")
            before_phase = link.detector.state.phase
            observed = link.detector.on_bar(ResearchBpuBar(
                ts=time_index(bar.end_time).to_pydatetime(),
                open=float(bar.open), high=float(bar.high),
                low=float(bar.low), close=float(bar.close),
                timeframe="M5", volume=float(bar.volume)))
            if (observed.phase == "invalidated"
                    and before_phase != "invalidated"):
                self._bpu_invalid_reasons[observed.reason] += 1
                if state["setup_trace"] is not None:
                    state["setup_trace"].add_bpu_failure(observed.reason)
            if observed.phase == "bpu1" and before_phase != observed.phase:
                if getattr(self, "_tvx_seconds_enabled", False):
                    # Arm exactly when the native consolidated BPU1
                    # closes. Next 270 traded SEC seconds must be
                    # observed through LEAN on_data, without History.
                    state["tvx_sec_window"] = NativeSecondTvxWindow(
                        native_end.to_pydatetime())
                self._bsu_bpu1_count += 1
                if state["setup_trace"] is not None:
                    state["setup_trace"].bpu1_count += 1
                if focus_charted_this_bar:
                    self.plot("Qwct Focus", "BPU1", observed.level_price)
                self._record(
                    symbol, "BSU_PROXY_BPU1", model="bounce",
                    side=observed.side, level=observed.level_price,
                    reason=f"{link.provenance}; native closed M5 BPU1; NO ORDERS")
            if observed.phase == "bpu2_confirmed" and before_phase != observed.phase:
                if focus_charted_this_bar:
                    self.plot("Qwct Focus", "BPU2", observed.level_price)
                self._bsu_proxy_bpu2_count += 1
                if state["setup_trace"] is not None:
                    state["setup_trace"].bpu2_count += 1
                if observed.preclose_seen:
                    self._tvx_preclose_reconciled += 1
                    win = state.get("tvx_sec_window")
                    if (isinstance(win, NativeSecondTvxWindow)
                            and win.complete and not win.blocked_reason
                            and win.last_at == win.cutoff
                            and link.provenance == (
                                "D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU")):
                        state["bsu_tvx_evidence"] = BpuTvxEvidence(
                            symbol=str(getattr(symbol, "value", symbol)),
                            session=self._session_date,
                            side=observed.side,
                            d1_level_price=link.cluster_price,
                            native_origin_price=link.origin_price,
                            native_tick_size=link.tick_size,
                            entry_price=observed.entry_price,
                            stop_price=observed.stop_price,
                            preclose_last_price=win.last_price,
                            bpu1_end=observed.bpu1_ts,
                            preclose_at=win.cutoff,
                            bpu2_end=native_end.to_pydatetime(),
                            origin_provenance=link.provenance)
                self._record(
                    symbol, "BSU_PROXY_BPU2_CLOSED",
                    model="bounce", side=observed.side,
                    level=observed.level_price,
                    reason=(
                        f"{link.provenance}; D1 origin={link.origin_time}; "
                        "BPU2 completed on native closed M5; "
                        + ("native SEC -30s candidate RECONCILED; "
                           if observed.preclose_seen else
                           "NO verified SEC -30s TVX; ")
                        + "NO ORDERS OR FILLS"))
        except Exception as exc:
            # Do not hide broken native D1/M5 integration as a signal.
            state["bsu_link"] = None
            state["tvx_sec_window"] = None
            state["bsu_tvx_evidence"] = None
            self._record(symbol, "ERROR", reason=f"BPU bridge: {exc}")
            self.error(f"BPU research error {symbol}: {exc}")
    decision = state["decision"]
    if state["qualified_today"] or decision is None or not decision.accepted:
        return
    market = MarketData(
        symbol.value, self._frame(state["daily_rows"]),
        self._frame(state["m5_rows"]),
        session_levels=state["session_levels"],
        breakout_retest=(
            state["breakout_retest"].evidence
            if state.get("breakout_retest") is not None else None),
        bpu_tvx=state.get("bsu_tvx_evidence"))
    try:
        self._m5_checks += 1
        intent = build_intent(
            decision, market, time_index(bar.end_time).to_pydatetime(),
            self.cfg, equity=float(self.portfolio.total_portfolio_value))
        if intent is None:
            self._intent_missing_atr += 1
            if state["setup_trace"] is not None:
                state["setup_trace"].missing_intent += 1
            return
        native_risk_read_ok = False
        if intent.gates["m5_confirmed"].passed is True:
            # Partial *native* LEAN evidence, for research ONLY. Missing
            # closed-trade ledger, period starts, cashflows and stop risk
            # remain UNKNOWN. No preview may turn risk_approved=True.
            if intent.shares > 0:
                try:
                    preview = review_native_lean_risk(
                        self, symbol, intent,
                        time_index(bar.end_time).to_pydatetime(), time_index)
                    failed = preview.mechanical_pass is False
                    blocked = next(
                        (r for r in preview.blockers
                         if not r.startswith("unknown native")),
                        "native loss / risk history not verified")
                    intent.gates["risk_approved"] = GateResult(
                        "risk_approved", False if failed else None,
                        "NATIVE PARTIAL RESEARCH; " + blocked[:150])
                    # Promote only AFTER the full native preview is read
                    # and interpreted without error.
                    native_risk_read_ok = True
                except Exception as exc:
                    intent.gates["risk_approved"] = GateResult(
                        "risk_approved", None,
                        "native risk observer failed closed: "
                        + str(exc)[:130])
            self._m5_true_by_model[intent.model] += 1
            # A valid M5 event is NOT enough for a signal. Preserve
            # the separate independent gates that prevent a candidate.
            for name, gate in intent.gates.items():
                if name != "m5_confirmed" and gate.passed is not True:
                    self._m5_true_other_blockers[name] += 1
        if state["setup_trace"] is not None:
            state["setup_trace"].observe_m5(
                time_index(bar.end_time).to_pydatetime(),
                {name: (gate.passed, gate.reason)
                 for name, gate in intent.gates.items()},
                # Native consolidated price evidence already captured
                # in the same M5 callback. Do NOT retrieve new/future
                # History bars or synthesize unobserved candle prices.
                closed_bars=state["m5_rows"][-2:])
        if not intent.all_gates_passed:
            # Distinguish a research-worthy setup from an approved trade:
            # missing native portfolio/Schwab risk approval is NEVER
            # sufficient to issue an INTENT or any broker order.
            research_ready = (
                # An approximate 2-bar bounce cannot stand in for
                # Gerchik's explicit BPU/TVX pattern. A CLOSED BPU2
                # observation still cannot prove the 30s entry.
                intent.model != "bounce"
                and native_risk_read_ok
                and intent.gates["risk_approved"].passed is None
                and intent.shares > 0
                and intent.limit_price > 0
                and intent.shares * intent.limit_price <=
                    float(self.portfolio.total_portfolio_value)
                and all(gate.passed is True for name, gate in intent.gates.items()
                        if name != "risk_approved")
            )
            if research_ready:
                window_ok, _ = self._session_policy.is_entry_allowed(
                    intent.model, time_index(bar.end_time).to_pydatetime())
                if window_ok:
                    state["qualified_today"] = True
                    if state["setup_trace"] is not None:
                        state["setup_trace"].candidate = True
                    gates = ",".join(
                        f"{name}:{gate.passed}" for name, gate in intent.gates.items())
                    self._record(
                        symbol, "RESEARCH_CANDIDATE", intent.model, intent.side,
                        intent.level_price, decision.score,
                        intent.limit_price, intent.stop_price,
                        intent.risk_per_share, gates,
                        "PRELIMINARY ONLY: native risk/buying-power and "
                        "protected brokerage entry NOT approved; NO ORDERS")
            # Counts are per evaluated M5 bar (not distinct trades).
            for name, gate in intent.gates.items():
                if gate.passed is not True:
                    self._gate_failures[name] += 1
            return
        window_ok, _ = self._session_policy.is_entry_allowed(
            intent.model, time_index(bar.end_time).to_pydatetime())
        if not window_ok:
            return
        state["qualified_today"] = True
        # The risk estimate alone is NOT proof of a working broker stop.
        # Native Bracket/OTO waits for complete entry fill; Schwab has
        # no OUO for partial exit protection. Review only, no orders.
        protection = review_schwab_protected_entry(
            side=intent.side, shares=intent.shares,
            limit_price=intent.limit_price, stop_price=intent.stop_price,
            target_r=self.cfg.tp_r,
            max_risk_usd=(
                float(self.portfolio.total_portfolio_value)
                * self.cfg.risk_per_trade_pct / 100.0))
        gates = ",".join(
            f"{name}:{gate.passed}" for name, gate in intent.gates.items())
        self._record(
            symbol, "INTENT", intent.model, intent.side,
            intent.level_price, decision.score,
            intent.limit_price, intent.stop_price,
            intent.risk_per_share, gates,
            "NO ORDERS SENT; NATIVE PROTECTION BLOCKED: "
            + "; ".join(protection.blockers))
        self.debug(
            f"SIGNAL {symbol.value} {intent.model}/{intent.side}"
            f" entry={intent.limit_price:.2f}"
            f" stop={intent.stop_price:.2f} [NO ORDER]")
    except Exception as exc:
        self._record(symbol, "ERROR", reason=str(exc))
        self.error(f"Signal error {symbol}: {exc}")

