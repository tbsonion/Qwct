"""Gerchik D1 / M5 multi-equity signal research using native LEAN APIs.

Execution is HARD DISABLED. No entries, custom broker adapter, fill simulator,
software OCO or shadow portfolio. Native EOD cancellation/liquidation is
prepared but gated off until a reviewed Schwab-compatible execution solution
exists. Schwab requires order cancel confirmations BEFORE market liquidation.
"""
from AlgorithmImports import *
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.levels import levels_for_session
from strategy.scenarios import ScenarioEvaluator
from strategy.sessions import SessionPolicy
from strategy.signals import build_intent
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

        # Native Fundamental Universe owns stock membership and data feeds.
        # Minute resolution is required for real M5 consolidators on *each*
        # selected stock, not only on the anchor or first watchlist stock.
        self.universe_settings.resolution = Resolution.MINUTE
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
        for state in self._symbols.values():
            state["qualified_today"] = False
            state["decision"] = None
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
                levels = levels_for_session(d1, self._session_date, self.cfg)
                decision = self._scenario_evaluator.evaluate(
                    symbol.value, self._session_date,
                    _time_index(self.time).to_pydatetime(), d1, None, levels)
                state["decision"] = decision
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

    def _on_m5(self, bar: TradeBar) -> None:
        symbol = bar.symbol
        if (not self._signals_open or
                symbol not in self.screen_watchlist or
                _time_index(bar.end_time).date() != self._session_date):
            return
        state = self._symbols.get(symbol)
        if state is None:
            return
        state["m5_rows"].append({
            "date": _time_index(bar.end_time),
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume)})
        state["m5_rows"] = state["m5_rows"][-80:]
        decision = state["decision"]
        if state["qualified_today"] or decision is None or not decision.accepted:
            return
        market = MarketData(
            symbol.value, self._frame(state["daily_rows"]),
            self._frame(state["m5_rows"]))
        try:
            intent = build_intent(
                decision, market, _time_index(bar.end_time).to_pydatetime(),
                self.cfg, equity=float(self.portfolio.total_portfolio_value))
            if intent is None or not intent.all_gates_passed:
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
            self.debug("EOD SIGNAL-ONLY: no orders/positions submitted")
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
        if not self._object_store_export_enabled:
            # The Free cloud plan has no ObjectStore write permission.
            # Emit only a short end-of-run count; DO NOT claim the complete
            # decision journal was saved (it remains in-memory only).
            counts = {key: sum(row["type"] == key
                               for row in self._signal_rows)
                      for key in ("INTENT", "SCENARIO", "REJECT", "ERROR")}
            self.log(
                "Qwct end-of-run signal summary: "
                + ", ".join(f"{key}={value}" for key, value in counts.items())
                + "; ObjectStore export DISABLED (Free organization). "
                  "Full decision CSV/JSON NOT saved."
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
