"""Qwct: LEAN-native market infrastructure + original Gerchik signal rules.

SIGNAL-ONLY. NO ORDERS. NO CUSTOM OMS, BROKER ADAPTER, NYSE CALENDAR,
VIRTUAL PORTFOLIO, OR INDICATOR CALCULATORS.

A separate reviewed change is needed before ANY broker execution, even
single-target 3R: native Bracket holds exits until entry completely fills.
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


ET = ZoneInfo("America/New_York")


def _time_index(ts: datetime) -> pd.Timestamp:
    """LEAN equity TradeBar times are exchange-local, naive datetimes."""
    t = pd.Timestamp(ts)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


class QwctGerchikAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.cfg = StrategyConfig()
        self.set_cash(self.cfg.starting_equity)
        self.set_time_zone("America/New_York")
        name = (self.get_parameter("symbol") or "AAPL").strip().upper()
        security = self.add_equity(name, Resolution.MINUTE)
        # Match the native screener universe and D1 indicator warmup across
        # stock splits; the latest split-adjusted price is still tradable.
        security.set_data_normalization_mode(DataNormalizationMode.SPLIT_ADJUSTED)
        self.symbol = security.symbol

        # These are actual LEAN indicators. The strategy never recalculates
        # ATR or SMA in pandas. Historical indicator values are kept alongside
        # closed daily candles purely for 14-group as-of feature evaluation.
        self._atr = AverageTrueRange(
            self.cfg.atr_period, MovingAverageType.WILDERS)
        self._sma = SimpleMovingAverage(self.cfg.trend_sma)
        self._daily_rows = []
        self._minute5_rows = []
        self._decision = None
        self._levels = []
        self._qualified_today = False
        self._session_date = None
        self._signals_open = False
        self._scenario_evaluator = ScenarioEvaluator(self.cfg)
        self._session_policy = SessionPolicy(self.cfg)

        # QC's native daily Fundamental Universe selects price/volume/liquidity.
        # Stage two uses native ATR and SMA(volume) on closed D1 bars.
        # The existing single-symbol signal engine remains unchanged; the
        # ranked scanner watchlist is research-only and does NOT send orders.
        self._screen_states = {}
        self._screen_ranks = {}
        self.screen_watchlist = ()
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.asynchronous = False
        self.universe_settings.data_normalization_mode = DataNormalizationMode.SPLIT_ADJUSTED
        self._screen_universe = self.add_universe(self._select_screen_universe)

        # Prime from LEAN's native typed history. No custom CSV feed or
        # homemade holiday calendar; fail closed if no usable history.
        try:
            bars = self.history[TradeBar](
                self.symbol, 180, Resolution.DAILY)
            for bar in bars:
                self._append_daily(bar)
        except Exception as exc:
            self.error(f"Native daily history failed: {exc}")

        # LEAN handles daily / M5 aggregation and exchange trading hours.
        self.consolidate(self.symbol, Resolution.DAILY, self._on_daily)
        self.consolidate(self.symbol, timedelta(minutes=5), self._on_m5)

        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_open(self.symbol, 1),
            self._prepare_session)
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_close(self.symbol, 5),
            self._end_session)

        self.debug("Qwct signal-only mode: NO order submission, NO brokerage")

    def _append_daily(self, bar: TradeBar) -> None:
        day = _time_index(bar.time).normalize()
        # Do not include duplicate daily history/consolidated samples in ATR.
        if self._daily_rows and day <= self._daily_rows[-1]["date"]:
            return
        self._atr.update(bar)
        self._sma.update(bar.end_time, bar.close)
        self._daily_rows.append({
            "date": day,
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume),
            f"atr{self.cfg.atr_period}": (
                float(self._atr.current.value) if self._atr.is_ready else float("nan")
            ),
            f"sma{self.cfg.trend_sma}": (
                float(self._sma.current.value) if self._sma.is_ready else float("nan")
            ),
        })
        # Memory cap; keep enough D1 bars for level clustering/50 SMA.
        self._daily_rows = self._daily_rows[-240:]

    def _on_daily(self, bar: TradeBar) -> None:
        self._append_daily(bar)
        # The manually-added anchor has minute resolution, so its D1 screen
        # indicator must be updated by the actual D1 consolidator, not M1 bars.
        self._screen_update_daily(bar)

    def _select_screen_universe(self, fundamentals):
        # Native LEAN supplies the previous completed daily universe snapshot.
        # Do not request History or inspect Portfolio inside this function.
        selected = select_liquid_fundamentals(fundamentals, self.cfg)
        self._screen_ranks = {symbol: i for i, symbol in enumerate(selected)}
        return selected

    def on_securities_changed(self, changes: SecurityChanges) -> None:
        added = [security.symbol for security in changes.added_securities]
        for security in changes.removed_securities:
            self._screen_states.pop(security.symbol, None)

        if not added:
            return
        for symbol in added:
            # Only actual LEAN indicator objects; no rolling virtual market.
            self._screen_states[symbol] = {
                "atr": AverageTrueRange(self.cfg.atr_period, MovingAverageType.WILDERS),
                "volume": SimpleMovingAverage(self.cfg.volume_lookback_days),
                "last_date": None,
                "last_price": None,
            }
        try:
            # A typed single-symbol History[TradeBar] yields TradeBars.
            # The MULTI-symbol overload can yield DataDictionary[TradeBar];
            # do not iterate it as a flat list of bars. These are native
            # historical requests, not a replacement market-data client.
            lookback = max(self.cfg.volume_lookback_days,
                           self.cfg.atr_period + 1) + 10
            for symbol in added:
                history = self.history[TradeBar](
                    symbol, lookback, Resolution.DAILY,
                    data_normalization_mode=DataNormalizationMode.SPLIT_ADJUSTED)
                for bar in history:
                    if _time_index(bar.time).date() < self.time.date():
                        self._screen_update_daily(bar)
        except Exception as exc:
            self.error(f"Native screener history unavailable: {exc}")
            # Unready indicators fail closed. No estimated ATR/volume.

    def _screen_update_daily(self, bar: TradeBar) -> None:
        state = self._screen_states.get(bar.symbol)
        if state is None:
            return
        trading_day = _time_index(bar.time).date()
        if state["last_date"] is not None and trading_day <= state["last_date"]:
            return
        state["atr"].update(bar)
        state["volume"].update(bar.end_time, bar.volume)
        state["last_date"] = trading_day
        state["last_price"] = float(bar.close)

    def on_data(self, data: Slice) -> None:
        # Scanned securities have DAILY subscription. The separately-added
        # anchor ticker has M1 bars: NEVER feed M1 into daily ATR/volume SMA.
        for symbol in tuple(self._screen_states):
            bar = data.bars.get(symbol)
            if bar is None or bar.period < timedelta(hours=20):
                continue
            self._screen_update_daily(bar)

    def _refresh_screen_watchlist(self) -> None:
        qualifying = []
        for symbol, rank in self._screen_ranks.items():
            state = self._screen_states.get(symbol)
            if state is None or state["last_date"] is None:
                continue
            # Reject old snapshots / any future bar at pre-market decision.
            age = (self.time.date() - state["last_date"]).days
            if age <= 0 or age > 7:
                continue
            if not state["atr"].is_ready or not state["volume"].is_ready:
                continue
            a = float(state["atr"].current.value)
            v = float(state["volume"].current.value)
            p = state["last_price"]
            if passes_gerchik_screener(p, a, v, self.cfg):
                qualifying.append((rank, symbol, p, a, v))

        # Fundamental candidates are already sorted by daily dollar volume.
        qualifying.sort(key=lambda x: (x[0], x[1].value))
        self.screen_watchlist = tuple(x[1] for x in
                                      qualifying[:self.cfg.screener_watchlist_limit])
        details = ", ".join(
            f"{sym.value}(P={p:.2f},ATR={a:.2f},V20={v:.0f})"
            for _, sym, p, a, v in
            qualifying[:self.cfg.screener_watchlist_limit])
        self.debug(f"GERCHIK SCREEN {self.time.date()}: "
                   f"{len(qualifying)} qualified / "
                   f"{len(self._screen_ranks)} liquid candidates. "
                   f"TOP: {details or 'none'} [SIGNAL ONLY]")

    def _daily_frame(self) -> pd.DataFrame:
        if not self._daily_rows:
            return pd.DataFrame()
        return pd.DataFrame(self._daily_rows).set_index("date").sort_index()

    def _m5_frame(self) -> pd.DataFrame:
        if not self._minute5_rows:
            return pd.DataFrame()
        return pd.DataFrame(self._minute5_rows).set_index("date").sort_index()

    def _prepare_session(self) -> None:
        self._session_date = self.time.date()
        self._signals_open = True
        self._qualified_today = False
        self._minute5_rows = []
        self._decision = None
        self._levels = []
        self._refresh_screen_watchlist()

        d1 = self._daily_frame()
        d1 = d1[d1.index < _time_index(self.time).normalize()] if not d1.empty else d1
        min_len = max(80, self.cfg.trend_sma + 26)
        if len(d1) < min_len:
            self.debug("NO SIGNAL: insufficient closed D1 history")
            return

        last = d1.iloc[-1]
        atr_value = last.get(f"atr{self.cfg.atr_period}", float("nan"))
        vol = float(d1["volume"].tail(self.cfg.volume_lookback_days).mean())
        if (pd.isna(atr_value) or float(atr_value) < self.cfg.min_atr
                or float(last["close"]) <= self.cfg.min_price
                or vol < self.cfg.min_volume):
            self.debug("NO SIGNAL: price/ATR/volume eligibility not met")
            return

        try:
            self._levels = levels_for_session(d1, self._session_date, self.cfg)
            self._decision = self._scenario_evaluator.evaluate(
                self.symbol.value, self._session_date,
                _time_index(self.time).to_pydatetime(),
                d1, None, self._levels)
            if self._decision.accepted:
                self.debug(
                    f"Prepared {self._decision.model}/{self._decision.side}"
                    f" @ {self._decision.level.price:.2f}"
                    f" score={self._decision.score:.2f}"
                    " (no orders)")
        except Exception as exc:
            # Invalid strategy calculation must NEVER trigger fallback orders.
            self._decision = None
            self.error(f"Gerchik session calculation failed: {exc}")

    def _on_m5(self, bar: TradeBar) -> None:
        # This cutoff is driven by LEAN's exchange-specific market-close
        # schedule, including early-close days; never use 16:00 as a shortcut.
        if not self._signals_open:
            return
        if self._session_date != _time_index(bar.end_time).date():
            return
        self._minute5_rows.append({
            "date": _time_index(bar.end_time),
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume),
        })
        if self._qualified_today or not self._decision or not self._decision.accepted:
            return

        d1 = self._daily_frame()
        if d1.empty:
            return
        market = MarketData(self.symbol.value, d1, self._m5_frame())
        try:
            intent = build_intent(
                self._decision, market,
                _time_index(bar.end_time).to_pydatetime(),
                self.cfg,
                equity=float(self.portfolio.total_portfolio_value))
            if intent and intent.all_gates_passed:
                window_ok, _ = self._session_policy.is_entry_allowed(
                    intent.model, _time_index(bar.end_time).to_pydatetime())
                if not window_ok:
                    return
                self._qualified_today = True
                # This is an INTENT, NOT an order. A final LEAN buying-power
                # check would be required if execution were ever enabled.
                self.debug(
                    f"SIGNAL {intent.model}/{intent.side} {self.symbol.value}"
                    f" entry={intent.limit_price:.2f}"
                    f" stop={intent.stop_price:.2f}"
                    f" 3R risk/sh={intent.risk_per_share:.2f}"
                    " [NO ORDER SENT]")
        except Exception as exc:
            self.error(f"Gerchik M5 calculation failed: {exc}")

    def _end_session(self) -> None:
        # This event fires five minutes before the *actual* market close.
        # Disable further signals; no positions/orders exist to liquidate.
        self._signals_open = False
        self.debug("Session ending: signal-only, no broker action")

    def on_order_event(self, event: OrderEvent) -> None:
        # Never maintain a duplicate order ledger or emulate broker OCO.
        self.log(f"LEAN order event (unexpected in signal-only mode): {event}")
