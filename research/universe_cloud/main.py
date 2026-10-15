"""Read-only LEAN point-in-time Qwct dynamic screener diagnostic; no orders."""
from AlgorithmImports import *
from collections import Counter
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy import select_liquid_fundamentals, passes_gerchik_screener
from strategy.levels import levels_for_session
from strategy.indicators import trend_direction, global_trend

ET = ZoneInfo("America/New_York")


def et(value):
    t = pd.Timestamp(value)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


def classify_snapshot(d1, cfg, session):
    """Use existing Qwct D1 screener, levels, and native-SMA trend rules."""
    if len(d1) < 60 or not d1.index.is_unique:
        raise ValueError("incomplete or duplicated as-of D1")
    last = d1.iloc[-1]
    price, a, v = (float(last["close"]),
                   float(last[f"atr{cfg.atr_period}"]),
                   float(last["volume_sma"]))
    stage2 = passes_gerchik_screener(price, a, v, cfg)
    if not stage2:
        return dict(stage2=False, price=price, atr=a, volume=v,
                    eligible=0, near=0, aligned=0, examples=[])
    levels = [x for x in levels_for_session(d1, session, cfg)
              if (x.source == "swing_cluster"
                  and x.kind in ("support", "resistance")
                  and x.valid_from is not None
                  and x.valid_from <= session
                  and x.touches >= cfg.min_touches
                  and x.strength >= cfg.min_level_strength)]
    near = [x for x in levels
            if abs(x.price-price) <= cfg.level_proximity_atr * a]
    gt = global_trend(d1, len(d1)-1, cfg)
    lt = trend_direction(d1, len(d1)-1, cfg)
    qualified = []
    for x in near:
        # Canonical ScenarioEvaluator bounce direction is relative to
        # the prior D1 close, not inferred from support/resistance labels.
        side = "short" if x.price >= price else "long"
        matching = (gt == lt == (1 if side == "long" else -1))
        if matching:
            qualified.append((x, side))
    examples = [
        (round(x.price, 4), x.kind,
         "short" if x.price >= price else "long",
         x.touches, round(x.strength, 2),
         "PASS" if gt == lt == (1 if x.price < price else -1)
         else "FAIL", gt, lt)
        for x in near[:3]]
    return dict(stage2=True, price=price, atr=a, volume=v,
                eligible=len(levels), near=len(near),
                aligned=len(qualified), examples=examples)


class QwctUniverseResearch(QCAlgorithm):
    def initialize(self):
        start = datetime.strptime(
            self.get_parameter("scan_start") or "2024-04-01", "%Y-%m-%d")
        end = datetime.strptime(
            self.get_parameter("scan_end") or "2024-04-05", "%Y-%m-%d")
        if end < start or (end-start).days > 14:
            raise ValueError("Universe research requires <=14 calendar days")
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_time_zone("America/New_York")
        self.set_cash(25_000)
        self.cfg = StrategyConfig()
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.fill_forward = False
        self.universe_settings.asynchronous = False
        self.universe_settings.data_normalization_mode = (
            DataNormalizationMode.RAW)
        self.screen_by_day = {}
        self.counts = Counter()
        self.rejections = Counter()
        self.example_rows = []
        self.covered_days = set()
        self.stock_day_ids = set()
        self.aligned_day_ids = set()
        anchor = self.add_equity(
            "SPY", Resolution.MINUTE, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        self.add_universe(self._screen)
        self.schedule.on(
            self.date_rules.every_day(anchor),
            self.time_rules.before_market_open(anchor, 1),
            self._prepare)
        self.debug(
            f"QWCT UNIVERSE RESEARCH ACTIVE {start.date()}..{end.date()} "
            "native Fundamental/RAW D1, same Qwct stage1+stage2, "
            "50 candidates / 10 watchlist; no M5, SEC, trades or orders")

    def _screen(self, fundamentals):
        """Reuse Qwct native fundamental selector, no future data/history."""
        day = et(self.time).date()
        selected = select_liquid_fundamentals(fundamentals, self.cfg)
        self.screen_by_day[day] = tuple(selected)
        return selected

    def _history_asof(self, symbols, day):
        """ONE batched LEAN History call; reject future or same-day bars."""
        bucket = {s: [] for s in symbols}
        for packet in self.history[TradeBar](
                list(symbols), 180, Resolution.DAILY, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW):
            for symbol, bar in packet.items():
                if symbol not in bucket:
                    continue
                st, end = et(bar.time), et(bar.end_time)
                if (st.date() >= day or end.date() >= day
                        or end <= st):
                    self.rejections["same-day/future or invalid D1"] += 1
                    bucket[symbol] = None
                    continue
                if bucket[symbol] is not None:
                    bucket[symbol].append(bar)
        return bucket

    def _native_frame(self, raw, day):
        if raw is None or len(raw) < 60:
            raise ValueError("insufficient closed RAW D1")
        raw.sort(key=lambda bar: et(bar.time))
        if len({et(x.time).date() for x in raw}) != len(raw):
            raise ValueError("duplicate D1 bar day")
        atr = AverageTrueRange(self.cfg.atr_period,
                               MovingAverageType.WILDERS)
        sma = SimpleMovingAverage(self.cfg.trend_sma)
        volume = SimpleMovingAverage(self.cfg.volume_lookback_days)
        rows, days = [], []
        for bar in raw:
            st, end = et(bar.time), et(bar.end_time)
            if st.date() >= day or end.date() >= day:
                raise ValueError("non-as-of D1 history")
            atr.update(bar)
            sma.update(bar.end_time, bar.close)
            volume.update(bar.end_time, bar.volume)
            rows.append({
                "open": float(bar.open), "high": float(bar.high),
                "low": float(bar.low), "close": float(bar.close),
                "volume": float(bar.volume), "bar_end": end,
                f"atr{self.cfg.atr_period}": (
                    float(atr.current.value) if atr.is_ready else float("nan")),
                f"sma{self.cfg.trend_sma}": (
                    float(sma.current.value) if sma.is_ready else float("nan")),
                "volume_sma": (float(volume.current.value)
                               if volume.is_ready else float("nan"))
            })
            days.append(st.normalize())
        return pd.DataFrame(rows, index=pd.DatetimeIndex(days))

    def _prepare(self):
        day = et(self.time).date()
        if day in self.covered_days:
            return
        members = self.screen_by_day.get(day)
        if not members:
            self.rejections["missing_same_day_universe"] += 1
            return
        self.covered_days.add(day)
        self.counts["days"] += 1
        self.counts["candidate_days"] += len(members)
        try:
            bucket = self._history_asof(members, day)
        except Exception as exc:
            self.rejections["native_history_error:" + str(exc)[:70]] += 1
            return
        passed = []
        for rank, symbol in enumerate(members):
            try:
                d1 = self._native_frame(bucket[symbol], day)
                obs = classify_snapshot(d1, self.cfg, day)
            except Exception as exc:
                self.rejections["D1:" + str(exc)[:60]] += 1
                continue
            self.counts["d1_ready"] += 1
            if not obs["stage2"]:
                self.counts["stage2_reject"] += 1
                continue
            passed.append((rank, symbol, obs))
            self.counts["stage2_pass"] += 1
        watchlist = passed[:self.cfg.screener_watchlist_limit]
        self.counts["watchlist_days"] += len(watchlist)
        for rank, symbol, obs in watchlist:
            label = (day.isoformat(), symbol.value)
            self.stock_day_ids.add(label)
            self.counts["eligible_level_days"] += obs["eligible"]
            self.counts["near_level_days"] += obs["near"]
            self.counts["aligned_level_days"] += obs["aligned"]
            if obs["eligible"]:
                self.counts["watch_with_two_touch"] += 1
            if obs["near"]:
                self.counts["watch_with_near_level"] += 1
            if obs["aligned"]:
                self.counts["watch_with_trend_aligned_bounce"] += 1
                self.aligned_day_ids.add(label)
            if obs["near"] and len(self.example_rows) < 16:
                self.example_rows.append((
                    day, symbol.value, rank+1, obs, obs["examples"][:2]))
        self.log(
            f"QWCT UNIVERSE DAY {day} candidates={len(members)} "
            f"d1_qualified={len(passed)} watchlist={len(watchlist)} "
            f"watch_near={sum(x[2]['near']>0 for x in watchlist)} "
            f"watch_aligned={sum(x[2]['aligned']>0 for x in watchlist)}; "
            "NO M5 / NO ORDERS")

    def on_end_of_algorithm(self):
        self.log(
            "QWCT UNIVERSE SUMMARY "
            f"days={self.counts['days']} "
            f"candidate_days={self.counts['candidate_days']} "
            f"d1_ready={self.counts['d1_ready']} "
            f"stage2_pass={self.counts['stage2_pass']} "
            f"watchlist_days={self.counts['watchlist_days']} "
            f"watch_with_two_touch={self.counts['watch_with_two_touch']} "
            f"watch_with_near_level={self.counts['watch_with_near_level']} "
            f"watch_with_trend_aligned_bounce="
            f"{self.counts['watch_with_trend_aligned_bounce']} "
            f"aligned_level_days={self.counts['aligned_level_days']} "
            f"unique_symbol_days={len(self.stock_day_ids)} "
            f"unique_aligned_symbol_days={len(self.aligned_day_ids)} "
            f"rejects={dict(self.rejections.most_common(4))}; "
            "NO M5 / NO SEC / NO ORDERS")
        for day, ticker, rank, obs, levels in self.example_rows:
            self.log(
                f"QWCT UNIVERSE EXAMPLE {day} {ticker} rank={rank} "
                f"close={obs['price']:.4f} atr={obs['atr']:.4f} "
                f"near={obs['near']} trend_aligned_levels={obs['aligned']} "
                f"levels={levels}; D1 ONLY / NO ORDERS")
