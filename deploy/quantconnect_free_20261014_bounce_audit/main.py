"""Gerchik D1 / M5 multi-equity signal research using native LEAN APIs.

NO ORDERS: broker, fills and EOD liquidation disabled.
"""
from AlgorithmImports import *
from datetime import datetime, timedelta
from collections import Counter
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.levels import levels_for_session
from strategy.scenarios import ScenarioEvaluator
from strategy.bsu_bridge import create_bsu_research_observer, audit_bsu_price_basis, resolve_raw_bsu_evidence
from strategy.breakout_retest import BreakoutRetestObserver
from strategy.sessions import SessionPolicy
from strategy.research_trace import SetupTrace, BpuTouchAudit
from strategy.reporting import native_order_event_row
# QuantConnect Free bundles these modules into strategy and reporting.
try:
    from strategy import choose_focus
    from strategy import select_liquid_fundamentals, passes_gerchik_screener
    from strategy.reporting import write_reports
except ModuleNotFoundError as exc:
    if exc.name not in ("strategy.focus", "strategy.screener", "strategy.runtime_reporting"):
        raise
    from strategy import choose_focus, select_liquid_fundamentals, passes_gerchik_screener
    from strategy.reporting import write_reports
from strategy.m5_runtime import process_m5
from strategy.second_runtime import process_second_slice
from strategy.corporate_action_guard import (
    process_native_split_events, rewarm_split_symbols, split_research_blocked)


ET = ZoneInfo("America/New_York")


def _time_index(ts: datetime) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


class QwctGerchikAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        # Optional bounded Cloud research window; default smoke unchanged.
        start = datetime.strptime(
            self.get_parameter("scan_start") or "2024-03-16", "%Y-%m-%d")
        end = datetime.strptime(
            self.get_parameter("scan_end") or "2024-04-26", "%Y-%m-%d")
        if end < start or (end - start).days > 45:
            raise ValueError("scan window must span 0-45 calendar days")
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self._case_scan = True
        self._bsu_scan_best = []
        self.cfg = StrategyConfig()
        # Opt-in SEC feed: tvx_seconds=true; high Cloud data cost.
        self._tvx_seconds_enabled = (
            (self.get_parameter("tvx_seconds") or "").strip().lower() == "true")
        self.set_cash(self.cfg.starting_equity)
        self.set_time_zone("America/New_York")

        # independently warmed symbols selected by the native universe.
        anchor = (self.get_parameter("clock_symbol") or "SPY").strip().upper()
        # RAW subscriptions; SCALED_RAW is used only to warm native D1.
        self._equity_normalization_mode = DataNormalizationMode.RAW
        # Anchor can be in universe: use SECOND here in SEC mode too.
        self.symbol = self.add_equity(
            anchor, (Resolution.SECOND if self._tvx_seconds_enabled
                     else Resolution.MINUTE), fill_forward=False,
            data_normalization_mode=self._equity_normalization_mode).symbol
        self.securities[self.symbol].set_data_normalization_mode(
            self._equity_normalization_mode)

        self._scenario_evaluator = ScenarioEvaluator(self.cfg)
        self._session_policy = SessionPolicy(self.cfg)
        self._screen_ranks = {}
        # Don't exhaust it with daily ten-symbol universe detail.
        self._screen_logged = False
        self._bsu_blocks_logged = 0
        self._symbols = {}
        self.screen_watchlist = ()
        self._session_date = None
        self._signals_open = False

        # Trading is hard-disabled regardless of parameters.
        self._native_exit_enabled = False
        # Cloud Free ObjectStore disabled.
        self._object_store_export_enabled = False
        self.set_trade_builder(TradeBuilder(
            FillGroupingMethod.FLAT_TO_FLAT, FillMatchingMethod.FIFO))
        self._signal_rows = []
        self._order_event_rows = []
        # Research counters only.
        self._m5_bars_seen = 0
        self._m5_input_rejections = Counter()
        self._m5_checks = 0
        self._intent_missing_atr = 0
        self._gate_failures = Counter()
        self._m5_true_by_model = Counter()
        self._m5_true_other_blockers = Counter()
        self._d1_models = Counter()
        self._bsu_block_reasons = Counter()
        self._bpu_invalid_reasons = Counter()
        self._breakout_retest_counts = Counter()
        self._native_sec_received = 0
        self._tvx_preclose_count = 0
        self._tvx_preclose_reconciled = 0
        self._tvx_second_reasons = Counter()
        # growing trace memory on 1-year Cloud Free research windows.
        self._setup_traces = []
        self._setup_traces_omitted = 0
        self._bsu_proxy_armed_count = 0
        self._bsu_bpu1_count = 0
        self._bsu_proxy_bpu2_count = 0

        self._chart_symbol = None
        self._focus_preference = (self.get_parameter("focus_symbol") or "").strip().upper()
        self._focus_m5_plotted = 0
        focus_chart = Chart("Qwct Focus")
        focus_chart.add_series(CandlestickSeries("M5", "$"))
        focus_chart.add_series(Series("D1 Level", SeriesType.LINE, 0))
        focus_chart.add_series(Series("BPU1", SeriesType.SCATTER, 0))
        focus_chart.add_series(Series("BPU2", SeriesType.SCATTER, 0))
        self.add_chart(focus_chart)

        # Official native feed; default MINUTE keeps Cloud smoke small.
        self.universe_settings.resolution = (
            Resolution.SECOND if self._tvx_seconds_enabled
            else Resolution.MINUTE)
        # Gerchik M5 confirmation must not be inferred from those
        self.universe_settings.fill_forward = False
        self.universe_settings.asynchronous = False
        self.universe_settings.data_normalization_mode = (
            self._equity_normalization_mode)
        self._screen_universe = self.add_universe(self._select_screen_universe)

        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_open(self.symbol, 1),
            self._prepare_session)
        # Schwab EOD: cancel orders, confirm cancellation, only then exit.
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
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.after_market_close(self.symbol, 1),
            self._checkpoint_reports)

        self.debug(
            f"QWCT SCAN ACTIVE {start.date()}..{end.date()}; "
            "signal-only; ALL ORDERS DISABLED; RAW as-of/SCALED_RAW D1; "
            + ("native SEC TVX research ENABLED, high data volume"
               if self._tvx_seconds_enabled else "native SEC TVX NOT ENABLED"))

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
        # Cap SECOND universe to watchlist capacity; MINUTE unchanged.
        limit = (self.cfg.screener_watchlist_limit
                 if self._tvx_seconds_enabled else None)
        selected = select_liquid_fundamentals(
            fundamentals, self.cfg, max_results=limit)
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
            "tvx_sec_window": None,
            "bsu_tvx_evidence": None,
            "preclose_review": None,
            "split_blocked_date": None, "split_rewarm_pending": False,
            "breakout_retest": None,
            "focus_level": None,
            "setup_trace": None,
            "touch_audit": None,
        }
        self._symbols[symbol] = state
        # Consolidators removed on universe removal.
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
                    data_normalization_mode=DataNormalizationMode.SCALED_RAW):
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
        # Actual daily selected count is plotted on Qwct Research.
        # Log the initial membership ONCE; reserve Cloud Free's short
        # log quota for real D1/BSU/M5 evidence at backtest completion.
        if not self._screen_logged:
            self._screen_logged = True
            tickers = ",".join(row[1].value for row in qualifying)
            self.debug(
                f"SCREEN initial {self.time.date()}: "
                f"{len(qualifying)} qualified [{tickers[:110]}]")

    def _prepare_session(self) -> None:
        self._session_date = self.time.date()
        self._signals_open = True
        if self.symbol in self._screen_ranks:
            if self._register_symbol(self.symbol):
                self._warm_symbols([self.symbol])
        rewarm_split_symbols(self)
        self._refresh_screen_watchlist()
        for state in self._symbols.values():
            state["qualified_today"] = False
            state["decision"] = None
            state["session_levels"] = None
            state["bsu_link"] = None
            state["tvx_sec_window"] = None
            state["bsu_tvx_evidence"] = None
            state["preclose_review"] = None
            state["breakout_retest"] = None
            state["focus_level"] = None
            state["setup_trace"] = None
            state["touch_audit"] = None
            state["m5_rows"] = []

        for symbol in self.screen_watchlist:
            state = self._symbols[symbol]
            if split_research_blocked(state, self._session_date):
                self._record(symbol, "REJECT",
                             reason="corporate split day: native rewarm quarantine")
                continue
            d1 = self._frame(state["daily_rows"])
            if not d1.empty:
                d1 = d1.loc[d1.index < _time_index(self.time).normalize()]
            if len(d1) < max(80, self.cfg.trend_sma + 26):
                self._record(symbol, "REJECT", reason="insufficient closed D1")
                continue
            try:
                levels = tuple(levels_for_session(d1, self._session_date, self.cfg))
                # Freeze confirmed D1 levels for the session.
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
                    # Bounded scenario trace.
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
                    if symbol == self._chart_symbol:
                        state["focus_level"] = float(decision.level.price)
                if decision.accepted and decision.model == "breakout":
                    # Research-only breakout/retest; never submits orders.
                    state["breakout_retest"] = BreakoutRetestObserver(
                        symbol=symbol.value, session=self._session_date,
                        side=decision.side,
                        level_price=float(decision.level.price),
                        atr_value=float(d1[f"atr{self.cfg.atr_period}"].iloc[-1]),
                        max_confirm_chase_atr=self.cfg.max_entry_distance_atr,
                        max_retest_bars=self.cfg.breakout_retest_max_bars,
                        retest_tolerance_atr=self.cfg.breakout_retest_touch_atr,
                        invalidation_atr=self.cfg.breakout_retest_invalid_atr)
                if decision.accepted and decision.model == "bounce":
                    native_tick_size = float(
                        self.securities[symbol].symbol_properties.minimum_price_variation)
                    raw, raw_evidence, raw_failure = [], None, ""
                    # Match closed native RAW D1 with live RAW M5 basis.
                    try:
                        if self._equity_normalization_mode != DataNormalizationMode.RAW:
                            raise ValueError("M5 subscription not RAW")
                        raw = [
                            bar for bars in self.history[TradeBar](
                                [symbol], 180, Resolution.DAILY,
                                fill_forward=False,
                                data_normalization_mode=DataNormalizationMode.RAW)
                            for key, bar in bars.items() if key == symbol]
                        raw_evidence = resolve_raw_bsu_evidence(
                            decision, d1, native_tick_size, raw, _time_index)
                    except Exception as exc:
                        raw_failure = str(exc)[:120]
                    link, why = create_bsu_research_observer(
                        decision, d1, native_tick_size, self.cfg,
                        raw_evidence=raw_evidence, require_raw=True)
                    if raw_failure:
                        why += "; " + raw_failure
                    if (symbol.value == "NVDA" and
                            self._session_date.isoformat() == "2024-01-02"):
                        if raw_evidence is not None:
                            self.log(audit_bsu_price_basis(
                                decision, d1, native_tick_size, raw, _time_index))
                        else:
                            self.log("QWCT BSU BASIS UNVERIFIED: " + raw_failure)
                    state["bsu_link"] = link
                    if state["setup_trace"] is not None:
                        state["setup_trace"].set_bsu(
                            link is not None,
                            (f"native swing origin={link.origin_time} "
                             f"pivot={link.origin_price:.4f} "
                             f"cluster={link.cluster_price:.4f}")
                            if link is not None else why)
                    if link is not None:
                        self._bsu_proxy_armed_count += 1
                        audit = BpuTouchAudit(
                            decision.side, link.origin_price, link.tick_size)
                        state["touch_audit"] = audit
                        if state["setup_trace"] is not None:
                            state["setup_trace"].touch_audit = audit
                    else:
                        self._bsu_block_reasons[why] += 1
                        self._record(symbol, "BSU_PROXY_BLOCKED", reason=why)
                        # Log the rejection before Cloud log quota is exhausted.
                        if self._bsu_blocks_logged < 6:
                            self._bsu_blocks_logged += 1
                            self.log(
                                f"QWCT BSU BLOCKED {symbol.value} "
                                f"{self._session_date} "
                                f"{decision.model}/{decision.side} "
                                f"level={decision.level.price:.2f} reason={why}")
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

        if self._chart_symbol is None:
            decisions = {
                symbol: self._symbols[symbol]["decision"]
                for symbol in self.screen_watchlist}
            selected = choose_focus(
                self.screen_watchlist, decisions, self._focus_preference)
            if selected is not None:
                # Keep one price scale for the whole backtest.
                self._chart_symbol = selected
                d = self._symbols[selected]["decision"]
                self._symbols[selected]["focus_level"] = float(d.level.price)
                self.debug(
                    f"Qwct Focus locked to accepted D1 setup: "
                    f"{selected.value} {d.model}/{d.side} "
                    f"level={d.level.price:.4f}")
        # even when free-plan logs are throttled.
        self.plot("Qwct Research", "Screener", len(self.screen_watchlist))
        self.plot(
            "Qwct Research", "D1 scenarios",
            sum(1 for symbol in self.screen_watchlist
                if self._symbols[symbol]["decision"] is not None
                and self._symbols[symbol]["decision"].accepted))

    def on_data(self, data: Slice) -> None:
        process_native_split_events(self, data, SplitType.SPLIT_OCCURRED)
        # No Scheduled Event lookahead; SEC on_data is after consolidators.
        process_second_slice(self, data, _time_index)

    def _on_m5(self, bar: TradeBar) -> None:
        # LEAN consolidator callback. All checks still run on the same
        # native completed 5-minute TradeBar; no additional history fetch.
        process_m5(self, bar, _time_index)

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
        # Delegate to a separate module because QuantConnect Cloud editors
        # reject files larger than 32,000 characters. Callback stays native.
        write_reports(self)
