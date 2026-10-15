"""QWCT 2.5: independent six-case D1-origin / native M5 research, NO ORDERS.

Fixed cases are previous REAL Universe Research observations (not new picks).
A native RAW/SCALED_RAW MATCH and confirmed D1 swing are algorithmic BSU
provenance ONLY; manual Gerchik BSU remains UNVERIFIED, TVX unobserved.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import datetime, timedelta, time
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session, _confirmed_swings
from strategy.indicators import global_trend, trend_direction
from strategy.patterns_bsu import Bar as ClosedBar, BsuDetector
from strategy.native_m5_validation import validate_m5_tradebar

ET = ZoneInfo("America/New_York")

# (day, native symbol, role, original RAW pivot day, original RAW pivot,
#  original D1 swing-cluster MEDIAN). All six were native RAW/SCALED_MATCH.
CASES = (
    ("2024-04-10", "TSLA", "short", "2024-03-11", 182.87, 183.56),
    ("2024-04-11", "TXN",  "long",  "2024-03-26", 167.51, 167.325),
    ("2024-04-16", "AAPL", "short", "2024-03-11", 174.38, 173.99),
    ("2024-04-16", "AMAT", "long",  "2024-03-28", 202.71, 202.19),
    ("2024-04-18", "META", "long",  "2024-03-15", 481.34, 481.57),
    ("2024-04-19", "NFLX", "long",  "2024-03-28", 601.57, 602.785),
)


def et(value):
    value = pd.Timestamp(value)
    return value.tz_localize(ET) if value.tzinfo is None else value.tz_convert(ET)


def choose_original_origin(d1, levels, target, session, cfg, tick):
    """Find EXACT same native Shadow D1 swing source; never make a new BSU."""
    _, ticker, side, first_day, raw_price, cluster = target
    wanted_kind = "support" if side == "long" else "resistance"
    if (d1 is None or len(d1) < 60 or not d1.index.is_unique
            or not d1.index.is_monotonic_increasing or d1.index.tz is None
            or d1.index[-1].date() >= session or tick is None):
        return None, "INVALID_CLOSED_NATIVE_D1"
    if not isfinite(tick) or tick <= 0:
        return None, "NO_NATIVE_TICK"
    matches = []
    for level in levels:
        if (level.source != "swing_cluster" or level.kind != wanted_kind
                or level.valid_from is None or level.valid_from > session
                or level.touches < cfg.min_touches
                or level.strength < cfg.min_level_strength
                or level.first_idx < cfg.swing_k
                or level.last_idx <= level.first_idx
                or level.last_idx + cfg.swing_k >= len(d1)):
            continue
        date = str(d1.index[level.first_idx].date())
        extreme = float(d1.iloc[level.first_idx][
            "low" if side == "long" else "high"])
        if (date == first_day and abs(extreme-raw_price) <= 1e-6
                and abs(level.price-cluster) <= 1e-4):
            swings = _confirmed_swings(d1, cfg.swing_k)[
                1 if side == "long" else 0]
            confirmations = {idx: when for idx, _, when in swings}
            if (level.first_idx not in confirmations
                    or level.last_idx not in confirmations
                    or level.formed_at != d1.index[level.last_idx].date()
                    or level.valid_from != confirmations[level.last_idx]
                    + timedelta(days=1)):
                return None, "SWING_CONFIRMATION_MISMATCH"
            if abs(extreme - round(extreme/tick)*tick) > tick*1e-5:
                return None, "SUBTICK_PIVOT_MANUAL_REVIEW"
            matches.append(level)
    if len(matches) != 1:
        return None, "UNIQUE_ORIGINAL_SWING_NOT_FOUND"
    return matches[0], "OBSERVED_D1_SWING_PROXY_NOT_MANUAL_BSU"


def compare_closed_bases(raw, scaled, level, day, tick):
    """Require same RAW/SCALED orig and latest, matching end timestamps."""
    if not scaled or not raw or tick <= 0:
        return False, "D1_BASIS_MISSING"
    first_day = et(raw[level.first_idx].time).date()
    last_day = et(raw[-1].time).date()
    scaled_days = {}
    prev = None
    for bar in scaled:
        opened, ended = et(bar.time), et(bar.end_time)
        if (opened.date() >= day or ended.date() >= day
                or ended <= opened or
                (prev is not None and opened.date() <= prev)):
            return False, "SCALED_FUTURE_OR_DUPLICATE"
        prev = opened.date()
        scaled_days[opened.date()] = bar
    if first_day not in scaled_days or last_day not in scaled_days:
        return False, "SCALED_ORIGIN_OR_LATEST_MISSING"
    first = raw[level.first_idx]
    last = raw[-1]
    sfirst, slast = scaled_days[first_day], scaled_days[last_day]
    if (et(first.end_time) != et(sfirst.end_time)
            or et(last.end_time) != et(slast.end_time)):
        return False, "RAW_SCALED_END_TIME_DISAGREES"
    field = "low" if level.kind == "support" else "high"
    values = (float(getattr(first, field)), float(getattr(sfirst, field)),
              float(last.close), float(slast.close))
    if not all(isfinite(x) and x > 0 for x in values):
        return False, "NONFINITE_D1_PRICE"
    tolerance = tick*.5 + tick*1e-7
    if abs(values[0]-values[1]) > tolerance:
        return False, "SCALED_SOURCE_REBASED"
    if abs(values[2]-values[3]) > tolerance:
        return False, "SCALED_LATEST_DIFF"
    return True, "RAW_SCALED_ORIGIN_LATEST_MATCH"


class QwctM5SixCaseResearch(QCAlgorithm):
    def initialize(self):
        start = datetime.strptime(
            self.get_parameter("scan_start") or "2024-04-10", "%Y-%m-%d")
        end = datetime.strptime(
            self.get_parameter("scan_end") or "2024-04-19", "%Y-%m-%d")
        if end < start or (end-start).days > 12:
            raise ValueError("Six-case research requires 0..12 calendar days")
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_time_zone("America/New_York")
        self.set_cash(25_000)
        self.cfg = StrategyConfig()
        self.case_by_symbol = {}
        self.case_states = {}
        self.summary = Counter()
        self.rejects = Counter()
        self.events = []
        self.m5_last_end = {}
        self.split_days = set()
        self.securities_by_name = {}
        self.case_lookup = {(row[0], row[1]): row for row in CASES}
        self.universe_settings.fill_forward = False
        for ticker in ("TSLA", "TXN", "AAPL", "AMAT", "META", "NFLX"):
            symbol = self.add_equity(
                ticker, Resolution.MINUTE, fill_forward=False,
                extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            self.securities_by_name[ticker] = symbol
            self.consolidate(symbol, timedelta(minutes=5), self._on_m5)
        anchor = self.securities_by_name["TSLA"]
        self.schedule.on(
            self.date_rules.every_day(anchor),
            self.time_rules.before_market_open(anchor, 1),
            self._prepare)
        self.debug(
            f"QWCT M5 SIX CASE ACTIVE {start.date()}..{end.date()} "
            "fixed 6 prior real D1 Shadow observations; RAW M5 native "
            "consolidators; manual BSU UNVERIFIED; no SEC/TVX/orders")

    def _get_daily(self, symbol, basis, session):
        bars = [
            bar for packet in self.history[TradeBar](
                [symbol], 180, Resolution.DAILY, fill_forward=False,
                data_normalization_mode=basis)
            for key, bar in packet.items() if key == symbol
        ]
        previous = None
        for bar in bars:
            begin, end = et(bar.time), et(bar.end_time)
            if (begin.date() >= session or end.date() >= session
                    or end <= begin or
                    (previous is not None and begin.date() <= previous)):
                raise ValueError("daily future, duplicate or out-of-order")
            previous = begin.date()
        return bars

    def _frame(self, bars):
        if len(bars) < 60:
            raise ValueError("D1 history fewer than 60 bars")
        native_atr = AverageTrueRange(
            self.cfg.atr_period, MovingAverageType.WILDERS)
        native_sma = SimpleMovingAverage(self.cfg.trend_sma)
        rows, index = [], []
        for bar in bars:
            native_atr.update(bar)
            native_sma.update(bar.end_time, bar.close)
            rows.append({
                "open": float(bar.open), "high": float(bar.high),
                "low": float(bar.low), "close": float(bar.close),
                "volume": float(bar.volume), "bar_end": et(bar.end_time),
                f"atr{self.cfg.atr_period}": (
                    float(native_atr.current.value) if native_atr.is_ready
                    else float("nan")),
                f"sma{self.cfg.trend_sma}": (
                    float(native_sma.current.value) if native_sma.is_ready
                    else float("nan")),
            })
            index.append(et(bar.time).normalize())
        return pd.DataFrame(rows, index=pd.DatetimeIndex(index))

    def _prepare(self):
        day = et(self.time).date()
        for (date, ticker), target in self.case_lookup.items():
            if date != str(day):
                continue
            sym = self.securities_by_name[ticker]
            self.summary["scheduled_cases"] += 1
            state = {"target": target, "status": "REJECTED", "reason": "",
                     "symbol": sym, "detector": None, "strict": False,
                     "first": None, "bpu1": 0, "bpu2": 0, "m5": 0,
                     "invalidated": 0, "best_gap_ticks": None}
            self.case_states[sym] = state
            try:
                raw = self._get_daily(sym, DataNormalizationMode.RAW, day)
                scaled = self._get_daily(
                    sym, DataNormalizationMode.SCALED_RAW, day)
                d1 = self._frame(raw)
                tick = float(self.securities[
                    sym].symbol_properties.minimum_price_variation)
                levels = levels_for_session(d1, day, self.cfg)
                level, reason = choose_original_origin(
                    d1, levels, target, day, self.cfg, tick)
                if level is None:
                    raise ValueError(reason)
                basis_ok, basis_reason = compare_closed_bases(
                    raw, scaled, level, day, tick)
                if not basis_ok:
                    raise ValueError(basis_reason)
                side = target[2]
                direction = 1 if side == "long" else -1
                latest_index = len(d1)-1
                if not (global_trend(d1, latest_index, self.cfg)
                        == trend_direction(d1, latest_index, self.cfg)
                        == direction):
                    raise ValueError("D1_SHADOW_TREND_NO_LONGER_MATCHES")
                origin = float(d1.iloc[level.first_idx][
                    "low" if side == "long" else "high"])
                origin_end = et(d1.iloc[level.first_idx]["bar_end"])
                last_end = et(d1.iloc[-1]["bar_end"])
                if not (origin_end < last_end < et(self.time)):
                    raise ValueError("D1_ORIGIN_NOT_BEFORE_DECISION")
                last_atr = float(d1.iloc[-1][f"atr{self.cfg.atr_period}"])
                if not isfinite(last_atr) or last_atr <= 0:
                    raise ValueError("D1_ATR_NOT_READY")
                observer = BsuDetector(
                    self.cfg, origin, side, atr_value=last_atr,
                    tick_size=tick, bsu_ts=origin_end.to_pydatetime())
                state.update(status="READY_PROXY", reason=reason,
                             detector=observer, level=origin, tick=tick,
                             side=side, cluster=float(level.price),
                             origin_end=origin_end.isoformat())
                self.summary["ready_proxies"] += 1
                self.log(
                    f"QWCT M5 READY {date} {ticker} {side} "
                    f"pivot={origin:.4f} cluster={level.price:.4f} "
                    f"src={target[3]} tick={tick} "
                    "raw_scaled=MATCH manual_bsu=UNVERIFIED NO ORDERS")
            except Exception as exc:
                state["reason"] = str(exc)[:90]
                self.rejects[state["reason"]] += 1
                self.log(f"QWCT M5 REJECT {date} {ticker} "
                         f"reason={state['reason']}")

    def on_data(self, data):
        splits = getattr(data, "splits", None)
        if splits is None:
            return
        for sym, event in splits.items():
            if (sym in self.case_states
                    and getattr(event, "type", None)
                    == SplitType.SPLIT_OCCURRED):
                self.split_days.add((sym, et(self.time).date()))
                self.case_states[sym]["status"] = "SPLIT_QUARANTINED"
                self.rejects["SPLIT_OCCURRED"] += 1

    def _on_m5(self, bar):
        sym = bar.symbol
        state = self.case_states.get(sym)
        if state is None or state["status"] != "READY_PROXY":
            return
        stamp = et(bar.end_time)
        if ((sym, stamp.date()) in self.split_days
                or stamp.date().isoformat() != state["target"][0]
                or not time(9, 35) <= stamp.time() <= time(16, 0)):
            return
        good, reason = validate_m5_tradebar(
            bar, stamp.to_pydatetime())
        if not good:
            self.rejects[reason] += 1
            return
        previous = self.m5_last_end.get(sym)
        if previous is not None and stamp <= previous:
            self.rejects["M5_DUPLICATE_OR_OUT_OF_ORDER"] += 1
            state["status"] = "M5_QUARANTINED"
            return
        self.m5_last_end[sym] = stamp
        state["m5"] += 1
        self.summary["valid_native_m5"] += 1
        det = state["detector"]
        if det.state.phase in ("invalidated", "bpu2_confirmed"):
            det.reset()
            state["strict"], state["first"] = False, None
        pivot, tick, side = state["level"], state["tick"], state["side"]
        extreme = float(bar.low if side == "long" else bar.high)
        gap = abs(extreme-pivot)/tick
        if state["best_gap_ticks"] is None or gap < state["best_gap_ticks"]:
            state["best_gap_ticks"] = gap
        old = det.state.phase
        try:
            result = det.on_bar(ClosedBar(
                ts=stamp.to_pydatetime(), open=float(bar.open),
                high=float(bar.high), low=float(bar.low),
                close=float(bar.close), volume=float(bar.volume),
                timeframe="M5"))
        except (ValueError, TypeError) as exc:
            self.rejects["M5_DETECTOR:" + str(exc)[:55]] += 1
            state["status"] = "M5_QUARANTINED"
            return
        if result.phase == "bpu1" and old != "bpu1":
            strict = abs(extreme-pivot) <= tick*1e-5
            state["strict"] = strict
            state["bpu1"] += 1
            state["first"] = (
                stamp.strftime("%H:%M"), float(bar.open),
                float(bar.high), float(bar.low), float(bar.close))
            self.summary["closed_bpu1"] += 1
            if strict:
                self.summary["strict_bpu1"] += 1
            if len(self.events) < 16:
                self.events.append(
                    f"QWCT M5 BPU1 {stamp.date()} {sym.value} "
                    f"{side} at={stamp:%H:%M} pivot={pivot:.4f} "
                    f"extreme={extreme:.4f} strict={int(strict)}")
        elif result.phase == "bpu2_confirmed" and old != "bpu2_confirmed":
            state["bpu2"] += 1
            self.summary["closed_bpu2"] += 1
            if state["strict"]:
                self.summary["strict_closed_bpu2"] += 1
            # M5 cannot prove the TVX state at BPU2 close minus 30s.
            bpu2_preclose = (stamp-timedelta(seconds=30)).time()
            window = any(
                time.fromisoformat(a) <= bpu2_preclose
                < time.fromisoformat(b)
                for a, b in self.cfg.session_windows_bounce)
            if window and state["strict"]:
                self.summary["strict_bpu2_in_bounce_window"] += 1
            if len(self.events) < 16:
                self.events.append(
                    f"QWCT M5 BPU2 {stamp.date()} {sym.value} "
                    f"{side} at={stamp:%H:%M} pivot={pivot:.4f} "
                    f"strict_bpu1={int(state['strict'])} "
                    f"bounce_window={int(window)} "
                    "TVX_UNVERIFIED NO ORDERS")
        elif result.phase == "invalidated" and old != "invalidated":
            state["invalidated"] += 1
            self.summary["bpu2_invalidated"] += 1

    def on_end_of_algorithm(self):
        self.log(
            "QWCT M5 SUMMARY "
            f"cases={self.summary['scheduled_cases']} "
            f"ready={self.summary['ready_proxies']} "
            f"m5={self.summary['valid_native_m5']} "
            f"bpu1={self.summary['closed_bpu1']} "
            f"strict_bpu1={self.summary['strict_bpu1']} "
            f"bpu2_closed={self.summary['closed_bpu2']} "
            f"strict_bpu2={self.summary['strict_closed_bpu2']} "
            f"strict_window={self.summary['strict_bpu2_in_bounce_window']} "
            f"invalidated={self.summary['bpu2_invalidated']} "
            f"rejects={dict(self.rejects.most_common(5))}; "
            "MANUAL BSU AND -30S TVX UNVERIFIED / NO ORDERS")
        for state in self.case_states.values():
            t = state["target"]
            self.log(
                f"QWCT M5 CASE {t[0]} {t[1]} {t[2]} "
                f"status={state['status']} reason={state['reason']} "
                f"m5={state['m5']} nearest_ticks={state['best_gap_ticks']} "
                f"bpu1={state['bpu1']} bpu2={state['bpu2']} "
                f"invalid={state['invalidated']}; NO ORDERS")
        for entry in self.events:
            self.log(entry + "; CLOSED M5 ONLY / NO FILLS")
