"""Gerchik D1 / M5 multi-equity signal research using native LEAN APIs.

Execution is HARD DISABLED. No entries, custom broker adapter, fill simulator,
software OCO or shadow portfolio. Native EOD cancellation/liquidation is
prepared but gated off until a reviewed Schwab-compatible execution solution
exists. Schwab requires order cancel confirmations BEFORE market liquidation.
"""
from AlgorithmImports import *
from datetime import datetime, timedelta
from collections import Counter
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.levels import levels_for_session
from strategy.scenarios import ScenarioEvaluator
from strategy.bsu_bridge import create_bsu_research_observer
from strategy.patterns_bsu import Bar as ResearchBpuBar
from strategy.sessions import SessionPolicy
from strategy.signals import build_intent
from strategy.research_trace import SetupTrace, summarize_traces
from strategy.screener import select_liquid_fundamentals, passes_gerchik_screener
from strategy.protected_entry import review_schwab_protected_entry
from strategy.reporting import (
    SIGNAL_FIELDS, ORDER_FIELDS, TRADE_FIELDS, csv_rows,
    native_order_event_row, native_closed_trade_rows, summary_json
)


ET = ZoneInfo("America/New_York")


def _time_index(ts: datetime) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


class QwctGerchikAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.cfg = StrategyConfig()
        self.set_cash(self.cfg.starting_equity)
        self.set_time_zone("America/New_York")

        # The anchor is a clock only. All actual Gerchik decisions use
        # independently warmed symbols selected by the native universe.
        anchor = (self.get_parameter("clock_symbol") or "SPY").strip().upper()
        self.symbol = self.add_equity(anchor, Resolution.MINUTE).symbol
        self.securities[self.symbol].set_data_normalization_mode(
            DataNormalizationMode.SPLIT_ADJUSTED)

        self._scenario_evaluator = ScenarioEvaluator(self.cfg)
        self._session_policy = SessionPolicy(self.cfg)
        self._screen_ranks = {}
        self._symbols = {}
        self.screen_watchlist = ()
        self._session_date = None
        self._signals_open = False

        # NO runtime parameter can turn on trading. This is an explicit
        # source-level kill switch until protective entries are independently
        # verified with the LEAN/Schwab brokerage integration.
        self._native_exit_enabled = False
        # QuantConnect Cloud Free organizations cannot write ObjectStore.
        # Keep signal research usable without misleading export errors.
        # This is a SOURCE-LEVEL research setting, not a trading toggle.
        self._object_store_export_enabled = False
        # LEAN defaults to FILL_TO_FILL, which is not a full position
        # round-trip. Use its official FLAT_TO_FLAT TradeBuilder grouping.
        self.set_trade_builder(TradeBuilder(
            FillGroupingMethod.FLAT_TO_FLAT, FillMatchingMethod.FIFO))
        self._signal_rows = []
        self._order_event_rows = []
        # Research-only diagnostics: count actual M5 evaluations and failed
        # gates; no virtual orders, fills or portfolio are inferred.
        self._m5_bars_seen = 0
        self._m5_checks = 0
        self._intent_missing_atr = 0
        self._gate_failures = Counter()
        self._d1_models = Counter()
        self._bsu_block_reasons = Counter()
        self._bpu_invalid_reasons = Counter()
        # In-memory evidence of the first accepted D1 setups; stop
        # growing trace memory on 1-year Cloud Free research windows.
        self._setup_traces = []
        self._setup_traces_omitted = 0
        self._bsu_proxy_armed_count = 0
        self._bsu_bpu1_count = 0
        self._bsu_proxy_bpu2_count = 0

        # A single fixed selected symbol, NOT mixed-ticker data on one
        # price axis. One LEAN Focus chart = 4 series; Qwct Research = 5.
        # Free Cloud quota: 10 series, 4,000 points/series. Only draw
        # up to 3,500 M5 bars to avoid silently exceeding that limit.
        self._chart_symbol = None
        self._focus_m5_plotted = 0
        focus_chart = Chart("Qwct Focus")
        focus_chart.add_series(CandlestickSeries("M5", "$"))
        focus_chart.add_series(Series("D1 Level", SeriesType.LINE, 0))
        focus_chart.add_series(Series("BPU1", SeriesType.SCATTER, 0))
        focus_chart.add_series(Series("BPU2", SeriesType.SCATTER, 0))
        self.add_chart(focus_chart)

        # Native Fundamental Universe owns stock membership and data feeds.
        # Minute resolution is required for real M5 consolidators on *each*
        # selected stock, not only on the anchor or first watchlist stock.
        self.universe_settings.resolution = Resolution.MINUTE
        # By default LEAN forward-fills bars when there are no trades.
        # Gerchik M5 confirmation must not be inferred from those
        # previously observed prices as if a real fresh bar arrived.
        self.universe_settings.fill_forward = False
        self.universe_settings.asynchronous = False
        self.universe_settings.data_normalization_mode = (
            DataNormalizationMode.SPLIT_ADJUSTED)
        self._screen_universe = self.add_universe(self._select_screen_universe)

        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_open(self.symbol, 1),
            self._prepare_session)
        # Two-stage EOD is mandated by documented Schwab cancellation lag.
        # First cancel broker orders, then check confirmed cancellations;
        # never submit Liquidate while contingent orders remain pending.
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_close(
                self.symbol, self.cfg.flatten_before_close_min + 3),
            self._cancel_before_close)
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_close(
                self.symbol, self.cfg.flatten_before_close_min),
            self._end_session)
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_close(self.symbol, 1),
            self._verify_flat_before_close)
        # Avoid the per-symbol OnEndOfDay callback for daily report
        # checkpointing; run after the actual exchange close instead.
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.after_market_close(self.symbol, 1),
            self._checkpoint_reports)

        self.debug("Qwct: multi-symbol Gerchik signal-only; ALL ORDERS DISABLED")

    def _record(self, symbol, kind, model="", side="", level="",
                score="", entry="", stop="", risk="", gates="", reason=""):
        self._signal_rows.append({
            "time_et": str(self.time), "symbol": symbol.value,
            "type": kind, "model": model, "side": side, "level": level,
            "score": score, "entry": entry, "stop": stop,
            "risk_per_share": risk, "gates": gates, "reason": reason
        })

    def _select_screen_universe(self, fundamentals):
        # Never call History/Portfolio/Transactions inside universe selection.
        selected = select_liquid_fundamentals(fundamentals, self.cfg)
        self._screen_ranks = {symbol: i for i, symbol in enumerate(selected)}
        return selected

    def on_securities_changed(self, changes: SecurityChanges) -> None:
        for security in changes.removed_securities:
            symbol = security.symbol
            state = self._symbols.get(symbol)
            if state is None:
                continue
            if security.invested or self.transactions.get_open_orders(symbol):
                self.error(f"Universe removal but position/order remains: {symbol}")
                # Never silently forget a currently owned security.
                continue
            for consolidator in (state["daily_consolidator"],
                                 state["m5_consolidator"]):
                self.subscription_manager.remove_consolidator(symbol, consolidator)
            del self._symbols[symbol]

        new_symbols = []
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol in self._screen_ranks and self._register_symbol(symbol):
                new_symbols.append(symbol)
        # Official LEAN performance guidance: batch symbols in ONE typed
        # History[TradeBar] call. A typed multi-symbol enumerable yields bars,
        # not a pandas DataFrame; avoid 50 separate history requests.
        self._warm_symbols(new_symbols)

    def _register_symbol(self, symbol) -> bool:
        """Subscribe native D1/M5 handlers once per selected LEAN Symbol."""
        if symbol in self._symbols:
            return False
        state = {
            "atr": AverageTrueRange(
                self.cfg.atr_period, MovingAverageType.WILDERS),
            "sma": SimpleMovingAverage(self.cfg.trend_sma),
            "volume": SimpleMovingAverage(self.cfg.volume_lookback_days),
            "daily_rows": [], "m5_rows": [],
            "last_date": None, "last_price": None,
            "decision": None, "qualified_today": False,
            "session_levels": None,
            "bsu_link": None,
            "focus_level": None,
            "setup_trace": None,
        }
        self._symbols[symbol] = state
        # Native LEAN consolidators must be removed on universe removal.
        state["daily_consolidator"] = self.consolidate(
            symbol, Resolution.DAILY, self._on_daily)
        state["m5_consolidator"] = self.consolidate(
            symbol, timedelta(minutes=5), self._on_m5)
        return True

    def _warm_symbols(self, symbols) -> None:
        if not symbols:
            return
        try:
            # Official LEAN multi-symbol typed History returns one
            # TradeBars (Symbol -> TradeBar) collection per time slice,
            # NOT one TradeBar per outer iteration.
            for bars in self.history[TradeBar](
                    symbols, 180, Resolution.DAILY,
                    data_normalization_mode=DataNormalizationMode.SPLIT_ADJUSTED):
                for symbol, bar in bars.items():
                    if _time_index(bar.end_time).date() < self.time.date():
                        self._append_daily(bar)
        except Exception as exc:
            # No synthetic fallback. Without D1 warmup signal rejects.
            self.error(f"Native typed history failed for {len(symbols)} "
                       f"symbols: {exc}")

    def _append_daily(self, bar: TradeBar) -> None:
        state = self._symbols.get(bar.symbol)
        if state is None:
            return
        trading_day = _time_index(bar.time).normalize()
        if state["last_date"] is not None and trading_day <= state["last_date"]:
            return
        state["atr"].update(bar)
        state["sma"].update(bar.end_time, bar.close)
        state["volume"].update(bar.end_time, bar.volume)
        state["last_date"] = trading_day
        state["last_price"] = float(bar.close)
        state["daily_rows"].append({
            "date": trading_day,
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume),
            # Store the native LEAN end timestamp, not an invented 16:00
            # close, so the D1 origin can be traced in BPU research.
            "bar_end": _time_index(bar.end_time).to_pydatetime(),
            f"atr{self.cfg.atr_period}": (
                float(state["atr"].current.value)
                if state["atr"].is_ready else float("nan")),
            f"sma{self.cfg.trend_sma}": (
                float(state["sma"].current.value)
                if state["sma"].is_ready else float("nan")),
        })
        state["daily_rows"] = state["daily_rows"][-240:]

    def _on_daily(self, bar: TradeBar) -> None:
        self._append_daily(bar)

    @staticmethod
    def _frame(rows):
        return (pd.DataFrame(rows).set_index("date").sort_index()
                if rows else pd.DataFrame())

    def _refresh_screen_watchlist(self) -> None:
        qualifying = []
        for symbol, rank in self._screen_ranks.items():
            state = self._symbols.get(symbol)
            if state is None or state["last_date"] is None:
                continue
            age = (self.time.date() - state["last_date"].date()).days
            if not 0 < age <= 7:
                continue
            if not state["atr"].is_ready or not state["volume"].is_ready:
                continue
            a, v = (float(state["atr"].current.value),
                    float(state["volume"].current.value))
            p = state["last_price"]
            if passes_gerchik_screener(p, a, v, self.cfg):
                qualifying.append((rank, symbol, p, a, v))

        qualifying.sort(key=lambda item: (item[0], item[1].value))
        qualifying = qualifying[:self.cfg.screener_watchlist_limit]
        self.screen_watchlist = tuple(row[1] for row in qualifying)
        detail = ", ".join(
            f"{s.value}(P={p:.2f},ATR={a:.2f},V20={v:.0f})"
            for _, s, p, a, v in qualifying)
        self.debug(f"SCREEN {self.time.date()}: "
                   f"{len(qualifying)} qualified: {detail or 'none'}")

    def _prepare_session(self) -> None:
        self._session_date = self.time.date()
        self._signals_open = True
        # A manually subscribed clock stock may already exist before the
        # fundamental universe selects it and won't necessarily appear in
        # added_securities. Use the same native setup path, once.
        if self.symbol in self._screen_ranks:
            if self._register_symbol(self.symbol):
                self._warm_symbols([self.symbol])
        self._refresh_screen_watchlist()
        # Freeze the focus Symbol on the FIRST qualifying trading day.
        # Do not dynamically switch prices between TSLA/NVDA/etc. on
        # a single chart with a deceptive shared dollar-price axis.
        if self._chart_symbol is None and self.screen_watchlist:
            self._chart_symbol = self.screen_watchlist[0]
            self.debug(f"Qwct Focus chart fixed symbol: {self._chart_symbol.value}")
        for state in self._symbols.values():
            state["qualified_today"] = False
            state["decision"] = None
            state["session_levels"] = None
            state["bsu_link"] = None
            state["focus_level"] = None
            state["setup_trace"] = None
            state["m5_rows"] = []

        for symbol in self.screen_watchlist:
            state = self._symbols[symbol]
            d1 = self._frame(state["daily_rows"])
            if not d1.empty:
                d1 = d1.loc[d1.index < _time_index(self.time).normalize()]
            if len(d1) < max(80, self.cfg.trend_sma + 26):
                self._record(symbol, "REJECT", reason="insufficient closed D1")
                continue
            try:
                levels = tuple(levels_for_session(d1, self._session_date, self.cfg))
                # Freeze exactly the D1 levels used to rank the morning
                # scenarios. Recalculate neither their kind nor their
                # next-level distances while a live M5 is arriving.
                state["session_levels"] = levels
                if symbol == self._chart_symbol and levels:
                    # Draw the closest D1 level only when in the same
                    # neighbourhood as the previous closed D1 price.
                    # The chart line is context, NOT an entry decision.
                    chart_price = float(d1["close"].iloc[-1])
                    chart_atr = float(state["atr"].current.value)
                    closest = min(levels, key=lambda l: abs(l.price - chart_price))
                    if (chart_atr > 0 and
                            abs(closest.price - chart_price) <= 2 * chart_atr):
                        state["focus_level"] = float(closest.price)
                decision = self._scenario_evaluator.evaluate(
                    symbol.value, self._session_date,
                    _time_index(self.time).to_pydatetime(), d1, None, levels)
                state["decision"] = decision
                if decision.accepted:
                    self._d1_models[decision.model] += 1
                    # A bounded scenario->M5 replay trace survives native
                    # universe removal and does not claim fills/orders.
                    if len(self._setup_traces) < 30:
                        trace = SetupTrace.from_decision(
                            decision, d1_close=float(d1["close"].iloc[-1]),
                            native_atr=float(d1[f"atr{self.cfg.atr_period}"].iloc[-1]),
                            level_count=len(levels))
                        state["setup_trace"] = trace
                        self._setup_traces.append(trace)
                        trace.set_bsu(False, "not eligible: model is not bounce")
                    else:
                        self._setup_traces_omitted += 1
                    # On the single-ticker plot, show the accepted
                    # morning scenario level rather than an unrelated
                    # nearby context level. No intraday recalculation.
                    if symbol == self._chart_symbol:
                        state["focus_level"] = float(decision.level.price)
                if decision.accepted and decision.model == "bounce":
                    # Native symbol properties (never a guessed USD 0.01)
                    # and actual as-of D1 origin are mandatory. A confirmed
                    # D1 swing is only a BSU PROXY, not a discretionary BSU.
                    native_tick_size = float(
                        self.securities[symbol].symbol_properties.minimum_price_variation)
                    link, why = create_bsu_research_observer(
                        decision, d1, native_tick_size, self.cfg)
                    state["bsu_link"] = link
                    if state["setup_trace"] is not None:
                        state["setup_trace"].set_bsu(
                            link is not None,
                            f"native swing proxy linked at {link.origin_time}"
                            if link is not None else why)
                    if link is not None:
                        self._bsu_proxy_armed_count += 1
                    else:
                        self._bsu_block_reasons[why] += 1
                        self._record(symbol, "BSU_PROXY_BLOCKED", reason=why)
                if decision.accepted:
                    self._record(
                        symbol, "SCENARIO", decision.model, decision.side,
                        decision.level.price, decision.score,
                        reason="D1 setup only; awaiting closed M5")
                else:
                    self._record(
                        symbol, "REJECT", reason="; ".join(
                            decision.rejected_reasons)[:500])
            except Exception as exc:
                state["decision"] = None
                self._record(symbol, "ERROR", reason=str(exc))
                self.error(f"Scenario error {symbol}: {exc}")

        # One D1 snapshot per trading day. Makes accepted setups visible
        # even when free-plan logs are throttled.
        self.plot("Qwct Research", "Screener", len(self.screen_watchlist))
        self.plot(
            "Qwct Research", "D1 scenarios",
            sum(1 for symbol in self.screen_watchlist
                if self._symbols[symbol]["decision"] is not None
                and self._symbols[symbol]["decision"].accepted))

    def _on_m5(self, bar: TradeBar) -> None:
        symbol = bar.symbol
        if (not self._signals_open or
                symbol not in self.screen_watchlist or
                _time_index(bar.end_time).date() != self._session_date):
            return
        state = self._symbols.get(symbol)
        if state is None:
            return
        self._m5_bars_seen += 1
        state["m5_rows"].append({
            "date": _time_index(bar.end_time),
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume)})
        state["m5_rows"] = state["m5_rows"][-80:]
        focus_charted_this_bar = (
            symbol == self._chart_symbol and self._focus_m5_plotted < 3500)
        if focus_charted_this_bar:
            # QuantConnect official CandlestickSeries accepts the native
            # completed TradeBar directly; no synthetic OHLC data.
            self.plot("Qwct Focus", "M5", bar)
            if state["focus_level"] is not None:
                self.plot("Qwct Focus", "D1 Level", state["focus_level"])
            self._focus_m5_plotted += 1
        # Observe closed native M5 BPU1/BPU2 for D1 swing proxies
        # independently of M5 gate scoring. This is NO TVX signal:
        # the original method requires 30 seconds BEFORE BPU2 close.
        link = state["bsu_link"]
        if link is not None:
            try:
                if link.detector.state.phase == "invalidated":
                    link.detector.reset()
                before_phase = link.detector.state.phase
                observed = link.detector.on_bar(ResearchBpuBar(
                    ts=_time_index(bar.end_time).to_pydatetime(),
                    open=float(bar.open), high=float(bar.high),
                    low=float(bar.low), close=float(bar.close),
                    timeframe="M5", volume=float(bar.volume)))
                if (observed.phase == "invalidated"
                        and before_phase != "invalidated"):
                    self._bpu_invalid_reasons[observed.reason] += 1
                    if state["setup_trace"] is not None:
                        state["setup_trace"].add_bpu_failure(observed.reason)
                if observed.phase == "bpu1" and before_phase != observed.phase:
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
                    self._record(
                        symbol, "BSU_PROXY_BPU2_CLOSED",
                        model="bounce", side=observed.side,
                        level=observed.level_price,
                        reason=(
                            f"{link.provenance}; D1 origin={link.origin_time}; "
                            "BPU2 completed on native closed M5; "
                            "NO 30s TVX observation, NO ORDERS OR FILLS"))
            except Exception as exc:
                # Do not hide broken native D1/M5 integration as a signal.
                state["bsu_link"] = None
                self._record(symbol, "ERROR", reason=f"BPU bridge: {exc}")
                self.error(f"BPU research error {symbol}: {exc}")
        decision = state["decision"]
        if state["qualified_today"] or decision is None or not decision.accepted:
            return
        market = MarketData(
            symbol.value, self._frame(state["daily_rows"]),
            self._frame(state["m5_rows"]),
            session_levels=state["session_levels"])
        try:
            self._m5_checks += 1
            intent = build_intent(
                decision, market, _time_index(bar.end_time).to_pydatetime(),
                self.cfg, equity=float(self.portfolio.total_portfolio_value))
            if intent is None:
                self._intent_missing_atr += 1
                if state["setup_trace"] is not None:
                    state["setup_trace"].missing_intent += 1
                return
            if state["setup_trace"] is not None:
                state["setup_trace"].observe_m5(
                    _time_index(bar.end_time).to_pydatetime(),
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
                        intent.model, _time_index(bar.end_time).to_pydatetime())
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
                intent.model, _time_index(bar.end_time).to_pydatetime())
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

    def _cancel_before_close(self) -> None:
        # Stop issuing signals before starting any native broker lifecycle.
        self._signals_open = False
        if not self._native_exit_enabled:
            return
        # Schwab may reject a new market exit while the cancelled stop
        # still counts as open exposure. Give the broker 3 scheduled minutes.
        self.transactions.cancel_open_orders()

    def _end_session(self) -> None:
        self._signals_open = False
        if not self._native_exit_enabled:
            # Plot only one point per market day, not one per M5 bar.
            # This diagnostic cannot create orders or change gates.
            self.plot("Qwct Research", "Signal intents",
                      sum(row["type"] == "INTENT" for row in self._signal_rows))
            self.plot("Qwct Research", "Research candidates",
                      sum(row["type"] == "RESEARCH_CANDIDATE"
                          for row in self._signal_rows))
            self.plot("Qwct Research", "Closed BPU2 proxies",
                      self._bsu_proxy_bpu2_count)
            return
        # Fail closed on unresolved cancellations; do not invent an
        # OCO/OMS cancellation workaround. Alert that FLAT is NOT proven.
        if self.transactions.get_open_orders():
            self.error("EOD CRITICAL: open/cancel-pending orders remain. "
                       "No overlapping liquidation orders submitted; NOT FLAT.")
            return
        if self.portfolio.invested:
            # LEAN native liquidation of ALL holdings. Schwab still
            # may reject/partially fill a market exit, so verify separately.
            self.liquidate(tag="GERCHIK EOD FLAT")

    def _verify_flat_before_close(self) -> None:
        if not self._native_exit_enabled:
            return
        if self.portfolio.invested or self.transactions.get_open_orders():
            self.error("EOD CRITICAL: NOT FLAT; investigate in broker! "
                       "No invented retries or orders.")
        else:
            self.log("EOD confirmed: no positions and no open LEAN orders")

    def on_order_event(self, event: OrderEvent) -> None:
        # LEAN OrderEvent is authoritative, not a synthetic fill or ledger.
        order = self.transactions.get_order_by_id(event.order_id)
        tag = str(order.tag) if order is not None else ""
        row = native_order_event_row(event, tag)
        self._order_event_rows.append(row)
        self.log(f"LEAN OrderEvent {row}")

    def _checkpoint_reports(self) -> None:
        # The native after-market-close scheduled event is anchored to the
        # exchange calendar, not per-symbol OnEndOfDay timing. In a backtest
        # only save once at algorithm end to avoid rewriting every bar day.
        if self.live_mode:
            self._write_reports()

    def on_end_of_algorithm(self) -> None:
        self._write_reports()

    def _write_reports(self) -> None:
        # Official native LEAN runtime statistics survive backtest logging
        # throttling and are available in the result view on Cloud Free.
        counts = Counter(row["type"] for row in self._signal_rows)
        for stat, kind in (("Qwct D1 setups", "SCENARIO"),
                           ("Qwct intents", "INTENT"),
                           ("Qwct rejects", "REJECT"),
                           ("Qwct errors", "ERROR")):
            self.set_runtime_statistic(stat, counts[kind])
        self.set_runtime_statistic(
            "Qwct research candidates", counts["RESEARCH_CANDIDATE"])
        self.set_runtime_statistic("Qwct D1 bounce", self._d1_models["bounce"])
        self.set_runtime_statistic("Qwct D1 breakout", self._d1_models["breakout"])
        self.set_runtime_statistic("Qwct D1 false",
                                   self._d1_models["false_breakout"])
        self.set_runtime_statistic("Qwct BSU proxy blocked",
                                   sum(self._bsu_block_reasons.values()))
        self.set_runtime_statistic("Qwct native BPU1", self._bsu_bpu1_count)
        self.set_runtime_statistic(
            "Qwct BPU invalidations", sum(self._bpu_invalid_reasons.values()))
        self.set_runtime_statistic(
            "Qwct chart focus", self._chart_symbol.value
            if self._chart_symbol is not None else "none")
        self.set_runtime_statistic(
            "Qwct focus M5 plotted", self._focus_m5_plotted)
        top_bsu = (
            self._bsu_block_reasons.most_common(1)[0]
            if self._bsu_block_reasons else None)
        top_gate = (
            self._gate_failures.most_common(1)[0]
            if self._gate_failures else None)
        self.set_runtime_statistic(
            "Qwct top BSU blocker",
            (f"{top_bsu[0][:60]} ({top_bsu[1]})" if top_bsu
             else ("no D1 bounce" if self._d1_models["bounce"] == 0
                   else "none")))
        self.set_runtime_statistic(
            "Qwct top M5 gate",
            f"{top_gate[0]}:{top_gate[1]}" if top_gate else "none")
        self.set_runtime_statistic(
            "Qwct BSU swing proxies armed", self._bsu_proxy_armed_count)
        self.set_runtime_statistic(
            "Qwct closed M5 BPU2 proxies", self._bsu_proxy_bpu2_count)
        self.set_runtime_statistic("Qwct M5 bars", self._m5_bars_seen)
        self.set_runtime_statistic("Qwct M5 checks", self._m5_checks)
        self.set_runtime_statistic(
            "Qwct traced D1 setups", len(self._setup_traces))
        self.set_runtime_statistic(
            "Qwct trace M5 checks",
            sum(t.m5_checks for t in self._setup_traces))
        self.set_runtime_statistic(
            "Qwct traced setups without M5",
            sum(t.m5_checks == 0 for t in self._setup_traces))
        # One human-readable line for EACH accepted setup (capped), not
        # thousands of per-candle logs that QuantConnect throttles.
        # These are real observations, not fabricated outcomes.
        for line in summarize_traces(self._setup_traces, limit=20):
            self.log(line)
        if self._setup_traces_omitted:
            self.log(
                f"QWCT TRACE memory cap: {self._setup_traces_omitted} "
                "additional accepted D1 setups not retained")
        if not self._object_store_export_enabled:
            # The Free cloud plan has no ObjectStore write permission.
            # Emit only a short end-of-run count; DO NOT claim the complete
            # decision journal was saved (it remains in-memory only).
            reject_reasons = Counter(
                "insufficient D1" if row["reason"] == "insufficient closed D1"
                else "no nearby levels" if "нет уровней рядом" in row["reason"]
                else "model score below threshold" if "скор " in row["reason"]
                else "other" for row in self._signal_rows
                if row["type"] == "REJECT")
            self.log(
                "Qwct research summary: "
                + ", ".join(f"{key}={counts[key]}" for key in
                            ("SCENARIO", "RESEARCH_CANDIDATE", "INTENT",
                             "REJECT", "ERROR"))
                + f"; M5 bars={self._m5_bars_seen}, "
                  f"M5 bar checks={self._m5_checks}, "
                  f"unready={self._intent_missing_atr}"
                + "; D1 models=" + str(dict(self._d1_models))
                + "; BSU block reasons=" +
                  str(dict(self._bsu_block_reasons.most_common(7)))
                + f"; native BPU1={self._bsu_bpu1_count}"
                + "; BPU invalid reasons=" +
                  str(dict(self._bpu_invalid_reasons.most_common(5)))
                + f"; chart focus={self._chart_symbol.value if self._chart_symbol else 'none'}"
                + f"; chart M5 drawn={self._focus_m5_plotted}"
                + "; daily rejects=" + str(dict(reject_reasons))
                + "; failed M5 gates=" +
                  str(dict(self._gate_failures.most_common(8)))
                + "; ObjectStore DISABLED: decision CSV/JSON NOT saved."
            )
            return
        # LEAN TradeBuilder owns the realized P&L and round-trip grouping.
        trades = native_closed_trade_rows(self.trade_builder.closed_trades)
        outputs = {
            "signal_decisions.csv": csv_rows(self._signal_rows, SIGNAL_FIELDS),
            "native_order_events.csv": csv_rows(
                self._order_event_rows, ORDER_FIELDS),
            "native_closed_trades.csv": csv_rows(trades, TRADE_FIELDS),
            "summary.json": summary_json(
                self._signal_rows, self._order_event_rows, trades,
                self.portfolio.invested),
        }
        # LEAN ObjectStore: save at algorithm end to avoid constant writes.
        # A unique AlgorithmId avoids overwriting another backtest's results.
        prefix = f"{self.project_id}/{self.algorithm_id}/gerchik"
        for filename, body in outputs.items():
            try:
                if not self.object_store.save(f"{prefix}/{filename}", body):
                    self.error(f"ObjectStore could not save {filename}")
            except Exception as exc:
                self.error(f"ObjectStore error saving {filename}: {exc}")
        self.log(f"Gerchik journal and trade report: {prefix}")
