# QWCT 4.1 — READY BACKTEST main.py for the SMALL Cohort-Research project.
# Replace the entire Cloud main.py with this file ONLY in that research project.
# It does NOT replace the full production/repo main.py.
# Already closed native D1 and M5 bars; no orders, no portfolio simulation.
from AlgorithmImports import *
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas as pd

from strategy.config import StrategyConfig
from strategy.levels import levels_for_session
from strategy.patterns_bsu import Bar, M5BsuSequenceScanner

ET = ZoneInfo("America/New_York")
SESSION = datetime(2024, 6, 3)
TICKERS = ("AMAT", "NFLX", "SRPT", "MSFT")


def _et(value):
    ts = pd.Timestamp(value)
    return ts.tz_localize(ET) if ts.tzinfo is None else ts.tz_convert(ET)


class QwctM5SourceResearch(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 6, 3)
        self.set_end_date(2024, 6, 3)
        self.set_time_zone("America/New_York")
        self.set_cash(25000)
        self.cfg = StrategyConfig()
        self._research = {}
        self.debug("QWCT 4.1 BACKTEST: read-only M5 source/BPU verification; NO ORDERS")

        for ticker in TICKERS:
            equity = self.add_equity(
                ticker, Resolution.MINUTE, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW)
            symbol = equity.symbol
            daily = list(self.history[TradeBar](
                symbol, SESSION - timedelta(days=335),
                SESSION,  # Only history known at Initialize (00:00 ET).
                Resolution.DAILY, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW))
            daily = [b for b in daily
                     if _et(b.time).date() < SESSION.date()
                     and not getattr(b, "is_fill_forward", False)]
            if len(daily) < 180:
                raise ValueError(
                    f"{ticker}: only {len(daily)} native D1; require 180")
            daily = daily[-180:]

            atr = AverageTrueRange(
                self.cfg.atr_period, MovingAverageType.WILDERS)
            rows = []
            for b in daily:
                atr.update(b)
                rows.append({
                    "date": _et(b.time),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume),
                    f"atr{self.cfg.atr_period}":
                        float(atr.current.value) if atr.is_ready else float("nan"),
                })
            frame = pd.DataFrame(rows).set_index("date")
            d1_levels = levels_for_session(frame, SESSION.date(), self.cfg)
            tick = float(
                self.securities[symbol].symbol_properties.minimum_price_variation)
            scan = M5BsuSequenceScanner(
                self.cfg, session=SESSION.date(), d1_levels=d1_levels,
                d1_atr=float(atr.current.value),
                previous_d1_close=float(frame.close.iloc[-1]),
                tick_size=tick)

            # Manually update native LEAN consolidators. A full M5 requires
            # five actual non-fill-forward 1m bars before being examined.
            cons = TradeBarConsolidator(timedelta(minutes=5))
            cons.data_consolidated += (
                lambda sender, bar, name=ticker: self._closed_m5(name, bar))
            self._research[ticker] = {
                "symbol": symbol, "consolidator": cons, "scan": scan,
                "minutes_seen": set(), "m5_count": 0,
                "closed_m5_ends": set(), "events_logged": 0,
            }
            self.debug(
                f"QWCT 4.1 INIT {ticker} D1={len(frame)} "
                f"LEVELS={len(d1_levels)} M5_ZONES={len(scan.zones)} TICK={tick}")

    def on_data(self, data):
        for ticker, state in self._research.items():
            symbol = state["symbol"]
            if symbol not in data.bars:
                continue
            bar = data.bars[symbol]
            stamp = _et(bar.end_time)
            if (stamp.date() != SESSION.date()
                    or stamp.time() < time(9, 31)
                    or stamp.time() > time(16, 0)
                    or getattr(bar, "is_fill_forward", False)):
                continue
            state["minutes_seen"].add(stamp)
            state["consolidator"].update(bar)

    def _closed_m5(self, ticker, closed):
        state = self._research[ticker]
        stamp = _et(closed.end_time)
        if (stamp.date() != SESSION.date()
                or not (time(9, 35) <= stamp.time() <= time(16, 0))
                or float(closed.volume) <= 0
                or any(stamp - timedelta(minutes=k)
                       not in state["minutes_seen"] for k in range(5))):
            return
        state["m5_count"] += 1
        state["closed_m5_ends"].add(stamp)
        bar = Bar(
            ts=stamp.to_pydatetime(),
            open=float(closed.open), high=float(closed.high),
            low=float(closed.low), close=float(closed.close),
            timeframe="M5", volume=float(closed.volume))
        events = state["scan"].observe(bar)
        for event in events:
            # Always count all events but keep the cloud log short.
            if state["events_logged"] < 12:
                self.debug(
                    f"QWCT 4.1 {ticker} {event.event} "
                    f"BSU={event.source_end} BPU1={event.bpu1_end} "
                    f"BPU2={event.bpu2_end} RAW_PRICE={event.level_price:.4f} "
                    f"D1_CONTEXT={event.d1_context_price:.4f} NO_ORDERS")
                state["events_logged"] += 1

    def on_end_of_algorithm(self):
        # QuantConnect's timed consolidator normally waits for the NEXT
        # minute's Update() to publish the prior completed M5. At 16:00
        # there is no next regular-session minute, so explicitly Scan()
        # the buffered ACTUAL bars at 16:01 (never synthesize prices).
        for ticker, state in self._research.items():
            state["consolidator"].scan(datetime(
                SESSION.year, SESSION.month, SESSION.day, 16, 1))
            expected_minutes = [
                _et(SESSION.replace(hour=9, minute=31)) + timedelta(minutes=i)
                for i in range(390)
            ]
            missing_minutes = [
                t.strftime("%H:%M") for t in expected_minutes
                if t not in state["minutes_seen"]
            ]
            expected_ends = [
                _et(SESSION.replace(hour=9, minute=35)) + timedelta(minutes=5*i)
                for i in range(78)
            ]
            missing_m5 = [
                t.strftime("%H:%M") for t in expected_ends
                if t not in state["closed_m5_ends"]
            ]
            scan = state["scan"]
            self.debug(
                f"QWCT 4.2 DATA AUDIT {ticker} "
                f"ACTUAL_1M={len(state['minutes_seen'])}/390 "
                f"MISSING_1M={missing_minutes[:15]} "
                f"REJECTED_OR_UNPUBLISHED_M5={missing_m5[:15]}")
            self.debug(
                f"QWCT 4.2 SUMMARY {ticker} "
                f"COMPLETE_M5={state['m5_count']}/78 "
                f"BPU1_EXACT={scan.bpu1_count} "
                f"BPU2_CLOSED={scan.completed} "
                "SAME_SESSION_ONLY AUTHOR_UNVERIFIED NO_ORDERS")
