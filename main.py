"""Qwct: LEAN-native market infrastructure + original Gerchik signal rules.

SIGNAL-ONLY. NO ORDERS. NO CUSTOM OMS, BROKER ADAPTER, NYSE CALENDAR,
VIRTUAL PORTFOLIO, OR INDICATOR CALCULATORS.

A separate reviewed change is needed before ANY broker execution, even
single-target 3R: native Bracket holds exits until entry completely fills.
"""
from AlgorithmImports import *
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.levels import levels_for_session
from strategy.scenarios import ScenarioEvaluator
from strategy.signals import build_intent


ET = ZoneInfo("America/New_York")


def _time_index(ts: datetime) -> pd.Timestamp:
    """LEAN equity TradeBar times are exchange-local, naive datetimes."""
    t = pd.Timestamp(ts)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


class QwctGerchikAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(25_000)
        self.set_time_zone("America/New_York")

        self.cfg = StrategyConfig()
        name = (self.get_parameter("symbol") or "AAPL").strip().upper()
        security = self.add_equity(name, Resolution.MINUTE)
        security.set_data_normalization_mode(DataNormalizationMode.RAW)
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
        self._scenario_evaluator = ScenarioEvaluator(self.cfg)

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
        self.consolidate(self.symbol, pd.Timedelta(minutes=5), self._on_m5)

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
        self._qualified_today = False
        self._minute5_rows = []
        self._decision = None
        self._levels = []

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
        # LEAN's event uses the actual market calendar, including half-days.
        # No liquidate() is needed here because NO orders are ever placed.
        self.debug("Session ending: signal-only, no broker action")

    def on_order_event(self, event: OrderEvent) -> None:
        # Never maintain a duplicate order ledger or emulate broker OCO.
        self.log(f"LEAN order event (unexpected in signal-only mode): {event}")
