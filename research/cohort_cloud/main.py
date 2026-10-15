"""QWCT 2.6 read-only dynamic D1->M5 cohort; never place orders."""
from AlgorithmImports import *
from collections import Counter
from datetime import datetime, timedelta, time
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy import select_liquid_fundamentals, passes_gerchik_screener
from strategy.patterns_bsu import Bar as ClosedBar, BsuDetector
from strategy.native_m5_validation import validate_m5_tradebar
from strategy.levels import levels_for_session, _confirmed_swings, native_cluster_tolerance
from strategy.indicators import trend_direction, global_trend

ET = ZoneInfo("America/New_York")


def et(value):
    t = pd.Timestamp(value)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


def d1_shadow_shortlist(passed, limit):
    """Read-only D1-first max-N shadow; retains original liquidity rank."""
    if type(limit) is not int or limit <= 0:
        raise ValueError("shadow capacity must be a positive integer")
    qualified = [
        row for row in passed
        if row[2].get("stage2") is True and row[2].get("role_aligned", 0) > 0
    ]
    return sorted(qualified, key=lambda row: (row[0], row[1].value))[:limit]


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
                    eligible=0, near=0, aligned=0, role_aligned=0,
                    role_conflict=0, shadow_levels=[], examples=[], _role_levels=[])
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
    role_aligned = []
    for x in near:
        # Canonical ScenarioEvaluator bounce side depends on prior close.
        # The separate BsuDetector arm instead uses source kind:
        # support => long, resistance => short. Never equate them.
        side = "short" if x.price >= price else "long"
        matching = (gt == lt == (1 if side == "long" else -1))
        if matching:
            qualified.append((x, side))
            if (x.kind == "support" and side == "long"
                    or x.kind == "resistance" and side == "short"):
                role_aligned.append((x, side))
    shadow_levels = [
        (round(x.price, 4), x.kind, side, x.touches,
         round(x.strength, 2), str(x.valid_from), str(x.formed_at))
        for x, side in role_aligned
    ]
    examples = [
        (round(x.price, 4), x.kind,
         "short" if x.price >= price else "long",
         x.touches, round(x.strength, 2),
         "PASS" if gt == lt == (1 if x.price < price else -1)
         else "FAIL", gt, lt,
         "BSU_ROLE_OK" if (
             x.kind == "support" and x.price < price
             or x.kind == "resistance" and x.price >= price)
         else "BSU_ROLE_MISMATCH")
        for x in near[:3]]
    return dict(stage2=True, price=price, atr=a, volume=v,
                eligible=len(levels), near=len(near),
                aligned=len(qualified), role_aligned=len(role_aligned),
                role_conflict=len(qualified)-len(role_aligned),
                shadow_levels=shadow_levels, examples=examples, _role_levels=role_aligned)

def origin_d1_audit(d1, lvl, session, cfg, native_tick):
    """PASS = RAW D1 pivot/grid/chronology ONLY, not canonical BSU."""
    r = dict(status="UNKNOWN", reason="", cluster=lvl.price,
             origin=None, source_date=None, confirmed_at=None,
             formed_at=str(lvl.formed_at), valid_from=str(lvl.valid_from),
             tick=native_tick, basis="RAW_ONLY_SCALED_RAW_UNCHECKED")

    def done(status, reason):
        r["status"], r["reason"] = status, reason
        return r

    if lvl.source != "swing_cluster" or lvl.kind not in ("support", "resistance"):
        return done("FAIL", "NOT_ORIGINAL_SUPPORT_RESISTANCE_SWING")
    if (d1 is None or d1.empty
            or not isinstance(d1.index, pd.DatetimeIndex)
            or d1.index.tz is None or not d1.index.is_unique
            or not d1.index.is_monotonic_increasing
            or d1.index[-1].date() >= session):
        return done("FAIL", "NON_CAUSAL_OR_INVALID_RAW_D1")
    i, j, k = lvl.first_idx, lvl.last_idx, cfg.swing_k
    if i < k or j <= i or j+k >= len(d1) or lvl.touches < cfg.min_touches:
        return done("FAIL", "INVALID_CONFIRMED_SWING_INDICES")
    r["source_date"] = str(d1.index[i].date())
    field = "low" if lvl.kind == "support" else "high"
    try:
        swings = _confirmed_swings(d1, k)[0 if field == "high" else 1]
        confirmations = {idx: date for idx, _, date in swings}
        if i not in confirmations or j not in confirmations:
            return done("FAIL", "ORIGIN_OR_LAST_IS_NOT_CONFIRMED_SWING")
        last_confirm = confirmations[j]
        r["confirmed_at"] = str(last_confirm)
        if (d1.index[j].date() != lvl.formed_at
                or lvl.valid_from != last_confirm + timedelta(days=1)
                or lvl.valid_from > session or confirmations[i] > last_confirm):
            return done("FAIL", "FORMATION_OR_VALID_FROM_CHRONOLOGY")
        origin = float(d1.iloc[i][field])
        r["origin"] = origin
        if not isfinite(origin) or origin <= 0:
            return done("FAIL", "INVALID_RAW_ORIGIN_EXTREME")
        if not isfinite(float(lvl.price)) or lvl.price <= 0:
            return done("FAIL", "INVALID_CLUSTER_PRICE")
        tolerance = native_cluster_tolerance(d1, cfg)
        if tolerance is None:
            return done("UNKNOWN", "NATIVE_CLUSTER_TOLERANCE_UNAVAILABLE")
        if abs(origin - lvl.price) > tolerance + 1e-7:
            return done("FAIL", "RAW_ORIGIN_OUTSIDE_NATIVE_CLUSTER")
        if native_tick is None:
            return done("UNKNOWN", "NATIVE_SECURITY_TICK_UNAVAILABLE")
        tick = float(native_tick)
        if not isfinite(tick) or tick <= 0:
            return done("UNKNOWN", "NATIVE_SECURITY_TICK_INVALID")
        if abs(origin - round(origin / tick)*tick) > tick*1e-5:
            # Daily RAW TradeBars contain executed trades. SEC Rule 612
            # allows midpoint/sub-penny executions even when limit/order
            # quotes have a larger minimum tick. An off-grid print is NOT
            # automatically a bad source, but cannot arm exact-tick BPU.
            return done("UNKNOWN", "RAW_TRADE_EXTREME_SUBTICK_NOT_ORDER_PRICE")
    except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
        return done("UNKNOWN", "RAW_ORIGIN_AUDIT_ERROR:" + str(exc)[:40])
    return done("PASS", "RAW_D1_ONLY;SCALED_RAW_UNVERIFIED")



def compare_raw_scaled(d1, lvl, session, scaled_bars, tick):
    """PIT RAW/SCALED_RAW price-basis observation, never BSU authorization."""
    result = dict(status="UNKNOWN", why="MISSING_SCALED_HISTORY",
                  source=None, raw=None, scaled=None, last_raw=None,
                  last_scaled=None, ratio=None, tick=tick, bars=0)

    def done(status, why):
        result["status"], result["why"] = status, why
        return result

    i = lvl.first_idx
    if (d1 is None or d1.empty or not d1.index.is_unique
            or not d1.index.is_monotonic_increasing
            or d1.index.tz is None or i < 0 or i >= len(d1)
            or d1.index[-1].date() >= session):
        return done("UNKNOWN", "INVALID_RAW_ASOF_INDEX")
    source_day, last_day = d1.index[i].date(), d1.index[-1].date()
    result["source"] = str(source_day)
    if not scaled_bars:
        return result
    try:
        tick = float(tick)
        if not isfinite(tick) or tick <= 0:
            return done("UNKNOWN", "NO_NATIVE_TICK")
        field = "low" if lvl.kind == "support" else "high"
        if lvl.kind not in ("support", "resistance"):
            return done("UNKNOWN", "INVALID_LEVEL_KIND")
        origin_raw = float(d1.iloc[i][field])
        last_raw = float(d1.iloc[-1]["close"])
        start_end = et(d1.iloc[i]["bar_end"])
        last_end = et(d1.iloc[-1]["bar_end"])
        by_day, previous = {}, None
        for bar in scaled_bars:
            start, end = et(bar.time), et(bar.end_time)
            if (start.date() >= session or end.date() >= session
                    or end <= start or (previous is not None
                    and start.date() <= previous)):
                return done("UNKNOWN", "SCALED_ASOF_ORDER_OR_FUTURE")
            previous = start.date()
            by_day[start.date()] = bar
        result["bars"] = len(by_day)
        if source_day not in by_day or last_day not in by_day:
            return done("UNKNOWN", "SCALED_SOURCE_OR_LATEST_MISSING")
        origin_bar, last_bar = by_day[source_day], by_day[last_day]
        if (et(origin_bar.end_time) != start_end
                or et(last_bar.end_time) != last_end):
            return done("UNKNOWN", "RAW_SCALED_ENDTIME_MISMATCH")
        origin_scaled = float(getattr(origin_bar, field))
        last_scaled = float(last_bar.close)
        if not all(isfinite(v) and v > 0 for v in
                   (origin_raw, origin_scaled, last_raw, last_scaled)):
            return done("UNKNOWN", "INVALID_BASIS_PRICE")
        result.update(raw=origin_raw, scaled=origin_scaled,
                      last_raw=last_raw, last_scaled=last_scaled,
                      ratio=origin_scaled/origin_raw)
        tolerance = tick*0.5 + tick*1e-7
        if abs(last_raw-last_scaled) > tolerance:
            return done("LATEST_DIFF", "LATEST_CLOSE_BASIS_DISAGREES")
        if abs(origin_raw-origin_scaled) > tolerance:
            return done("REBASED", "HISTORICAL_ORIGIN_SCALE_DIFFERS")
    except (AttributeError, TypeError, ValueError, KeyError,
            IndexError, OverflowError) as exc:
        return done("UNKNOWN", "BASIS_ERROR:" + str(exc)[:35])
    return done("MATCH", "ORIGIN_AND_LATEST_MATCH_WITHIN_HALF_TICK")




class QwctM5CohortResearch(QCAlgorithm):
    """Freeze native D1 selection at 09:29; AFTER CLOSE replay native M1->M5."""

    def initialize(self):
        start = datetime.strptime(
            self.get_parameter("scan_start") or "2024-06-01", "%Y-%m-%d")
        end = datetime.strptime(
            self.get_parameter("scan_end") or "2024-06-30", "%Y-%m-%d")
        if end < start or (end-start).days > 35:
            raise ValueError("Cohort research is limited to <=35 days")
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_time_zone("America/New_York")
        self.set_cash(25_000)
        self.cfg = StrategyConfig()
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.fill_forward = False
        self.universe_settings.asynchronous = False
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.by_day = {}
        self.callback_at = {}
        self.active = {}
        self.all_cases = []
        self.quarantined = set()
        self.active_day = None
        self.scanned = set()
        self.finished = set()
        self.summary = Counter()
        self.rejects = Counter()
        self.basis = Counter()
        self.origin = Counter()
        self.events = []
        self.tail_examples = []
        anchor = self.add_equity(
            "SPY", Resolution.MINUTE, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        self.add_universe(self._select)
        self.schedule.on(self.date_rules.every_day(anchor),
                         self.time_rules.before_market_open(anchor, 1),
                         self._prepare)
        self.schedule.on(self.date_rules.every_day(anchor),
                         self.time_rules.after_market_close(anchor, 0),
                         self._finish)
        self.debug(
            f"QWCT 2.6 COHORT ACTIVE {start.date()}..{end.date()} "
            "native Fundamental50 + D1 Shadow10; strict same-day callbacks; "
            "after-close RAW M1 -> native M5 replay; NO M5-at-open, "
            "NO SEC / NO TVX / NO ORDERS")

    def _select(self, fundamentals):
        day = et(self.time).date()
        selected = tuple(select_liquid_fundamentals(fundamentals, self.cfg))
        self.by_day[day] = selected
        self.callback_at[day] = et(self.time)
        self.summary["callbacks"] += 1
        if day.weekday() >= 5:
            self.summary["weekend_callbacks"] += 1
        return selected

    def _daily_history(self, symbols, day, mode):
        bucket = {sym: [] for sym in symbols}
        for packet in self.history[TradeBar](
                list(symbols), 180, Resolution.DAILY, fill_forward=False,
                data_normalization_mode=mode):
            for sym, bar in packet.items():
                if sym not in bucket:
                    continue
                begin, end = et(bar.time), et(bar.end_time)
                if (begin.date() >= day or end.date() >= day
                        or end <= begin or (bucket[sym] and
                        begin <= et(bucket[sym][-1].time))):
                    bucket[sym] = None
                    continue
                if bucket[sym] is not None:
                    bucket[sym].append(bar)
        return bucket

    def _native_frame(self, raw, day):
        if raw is None or len(raw) < 60:
            raise ValueError("D1_INSUFFICIENT_CLOSED_RAW")
        atr = AverageTrueRange(self.cfg.atr_period, MovingAverageType.WILDERS)
        sma = SimpleMovingAverage(self.cfg.trend_sma)
        volume = SimpleMovingAverage(self.cfg.volume_lookback_days)
        rows, days, seen = [], [], set()
        for bar in raw:
            start, end = et(bar.time), et(bar.end_time)
            if (start.date() in seen or start.date() >= day
                    or end.date() >= day or end <= start):
                raise ValueError("D1_DUPLICATE_OR_NONCAUSAL")
            seen.add(start.date())
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
                "volume_sma": (
                    float(volume.current.value) if volume.is_ready else float("nan")),
            })
            days.append(start.normalize())
        return pd.DataFrame(rows, index=pd.DatetimeIndex(days))

    def _prepare(self):
        day = et(self.time).date()
        if day in self.scanned:
            return
        self.scanned.add(day)
        self.summary["scheduled_scans"] += 1
        members = self.by_day.get(day)
        if (not members or self.callback_at[day] > et(self.time)):
            self.rejects["NO_SAME_DAY_FUNDAMENTAL_CALLBACK"] += 1
            self.log(f"QWCT COHORT SKIP {day} NO_SAME_DAY_CALLBACK; "
                     "not zero qualified stocks; Saturday never auto-carried")
            self.active, self.active_day = {}, day
            return
        self.summary["selection_days"] += 1
        self.summary["candidate_stock_days"] += len(members)
        self.active, self.active_day = {}, day
        try:
            bucket = self._daily_history(
                members, day, DataNormalizationMode.RAW)
        except Exception as exc:
            self.rejects["RAW_D1_REQUEST:" + str(exc)[:48]] += 1
            return

        passed, frames = [], {}
        for rank, symbol in enumerate(members):
            try:
                d1 = self._native_frame(bucket[symbol], day)
                obs = classify_snapshot(d1, self.cfg, day)
                self.summary["d1_ready"] += 1
                if obs["stage2"]:
                    self.summary["stage2_pass"] += 1
                    passed.append((rank, symbol, obs))
                    if obs["role_aligned"] > 0:
                        frames[symbol] = d1
            except Exception as exc:
                self.rejects["RAW_D1:" + str(exc)[:48]] += 1

        shadow = d1_shadow_shortlist(passed, self.cfg.screener_watchlist_limit)
        self.summary["shadow_symbol_days"] += len(shadow)
        if not shadow:
            return
        try:
            scaled = self._daily_history(
                [sym for _, sym, _ in shadow], day,
                DataNormalizationMode.SCALED_RAW)
        except Exception as exc:
            self.rejects["SCALED_D1_REQUEST:" + str(exc)[:48]] += 1
            return
        for rank, symbol, obs in shadow:
            try:
                tick = float(
                    self.securities[symbol].symbol_properties.minimum_price_variation)
            except Exception:
                tick = None
            for level, side in obs.get("_role_levels", [])[:3]:
                d1 = frames[symbol]
                orig = origin_d1_audit(d1, level, day, self.cfg, tick)
                self.origin[orig["status"]] += 1
                if orig["status"] != "PASS":
                    self.rejects["ORIGIN_" + orig["status"] + ":" +
                                 orig["reason"][:42]] += 1
                    continue
                proof = compare_raw_scaled(
                    d1, level, day, scaled.get(symbol), tick)
                self.basis[proof["status"]] += 1
                # REBASED is tagged rather than silently mistaken for MATCH.
                # Historical RAW source remains the ONLY pivot for RAW M5.
                if proof["status"] not in ("MATCH", "REBASED"):
                    self.rejects["BASIS_" + proof["status"] + ":" +
                                 proof["why"][:40]] += 1
                    continue
                last_atr = float(
                    d1.iloc[-1][f"atr{self.cfg.atr_period}"])
                if not isfinite(last_atr) or last_atr <= 0:
                    self.rejects["ATR_NOT_READY"] += 1
                    continue
                try:
                    detector = BsuDetector(
                        self.cfg, orig["origin"], side,
                        atr_value=last_atr, tick_size=tick,
                        bsu_ts=et(d1.iloc[level.first_idx]["bar_end"]).to_pydatetime())
                except (TypeError, ValueError) as exc:
                    self.rejects["DETECTOR:" + str(exc)[:48]] += 1
                    continue
                case = dict(
                    ticker=symbol.value, side=side, symbol=symbol,
                    day=day, origin=orig["origin"], source=orig["source_date"],
                    basis=proof["status"], tick=tick, detector=detector,
                    bpu1=0, strict_bpu1=0, bpu2=0, strict_bpu2=0,
                    invalid=0, n_m5=0, best_ticks=None, first_strict=False)
                self.active.setdefault(symbol, []).append(case)
                self.all_cases.append(case)
                self.summary["ready_origins"] += 1
        if self.active:
            self.log(
                f"QWCT COHORT DAY {day} shadow={len(shadow)} "
                f"ready={sum(len(x) for x in self.active.values())} "
                f"basis_M={self.basis['MATCH']} "
                f"basis_R={self.basis['REBASED']}; retrospective M5 ONLY")

    def on_data(self, data):
        """Quarantine real split days; never replay a mixed native price basis."""
        splits = getattr(data, "splits", None)
        if splits is None:
            return
        for sym, event in splits.items():
            if (sym in self.active and
                    getattr(event, "type", None) == SplitType.SPLIT_OCCURRED):
                self.quarantined.add((sym, et(self.time).date()))
                self.rejects["SPLIT_OCCURRED_QUARANTINE"] += 1

    def _finish(self):
        day = et(self.time).date()
        if day in self.finished:
            return
        self.finished.add(day)
        if day != self.active_day or not self.active:
            return
        symbols = [
            sym for sym in self.active
            if (sym, day) not in self.quarantined]
        if not symbols:
            return
        # Replay at the ACTUAL exchange close (half-days too). A +1
        # minute schedule may never execute on the final backtest day.
        # Completed native minutes were NEVER used by the 09:29 selector.
        start = datetime.combine(day, time(9, 30), ET)
        end = et(self.time).to_pydatetime()
        if et(end) <= et(start):
            self.rejects["INVALID_SESSION_CLOSE"] += 1
            return
        minute = {symbol: [] for symbol in symbols}
        try:
            for packet in self.history[TradeBar](
                    symbols, start, end, Resolution.MINUTE,
                    fill_forward=False, extended_market_hours=False,
                    data_normalization_mode=DataNormalizationMode.RAW):
                for sym, bar in packet.items():
                    if sym in minute:
                        minute[sym].append(bar)
        except Exception as exc:
            self.rejects["MINUTE_HISTORY:" + str(exc)[:50]] += 1
            return
        self.summary["after_close_replay_days"] += 1
        for symbol in symbols:
            self._replay(symbol, minute[symbol], day, end)

    def _replay(self, symbol, minute_bars, day, close):
        """Actual LEAN TradeBarConsolidator from historical native TradeBars."""
        cases = self.active[symbol]
        if not minute_bars:
            self.rejects["EMPTY_M1_" + symbol.value] += 1
            return
        times = []
        for bar in minute_bars:
            start, finish = et(bar.time), et(bar.end_time)
            if (start.date() != day or finish.date() != day
                    or not time(9, 30) <= start.time() < time(16, 0)
                    or finish-start != timedelta(minutes=1)
                    or start < et(datetime.combine(day, time(9, 30), ET))
                    or finish > et(datetime.combine(day, time(16, 0), ET))
                    or (times and start <= times[-1])):
                self.rejects["BAD_OR_UNORDERED_M1_" + symbol.value] += 1
                return
            times.append(start)
        first_m1_end = et(minute_bars[0].end_time)
        last_m1_end = et(minute_bars[-1].end_time)
        if last_m1_end == et(close):
            self.summary["m1_tail_at_close"] += 1
        else:
            self.summary["m1_tail_before_close"] += 1
        emitted = []
        consolidator = TradeBarConsolidator(timedelta(minutes=5))
        def collect(sender, bar):
            emitted.append(bar)
        consolidator.data_consolidated += collect
        try:
            for bar in minute_bars:
                consolidator.update(bar)
        except Exception as exc:
            self.rejects["M5_CONSOLIDATOR:" + str(exc)[:45]] += 1
            return
        self.summary["native_m1"] += len(minute_bars)
        self.summary["m5_emitted"] += len(emitted)
        last_m5_end = et(emitted[-1].end_time) if emitted else None
        if last_m5_end == et(close):
            self.summary["m5_tail_at_close"] += 1
        else:
            self.summary["m5_tail_before_close"] += 1
        if len(self.tail_examples) < 4:
            self.tail_examples.append((
                str(day), symbol.value, len(minute_bars),
                len(emitted), str(last_m1_end.time()),
                str(last_m5_end.time()) if last_m5_end is not None else "NA",
                str(et(close).time())))
        if not emitted:
            self.rejects["NO_NATIVE_M5_" + symbol.value] += 1
            return
        for bar in emitted:
            at = et(bar.end_time)
            if not time(9, 35) <= at.time() <= time(16, 0):
                self.rejects["M5_OUTSIDE_REGULAR_SESSION"] += 1
                continue
            allowed, reason = validate_m5_tradebar(bar, at.to_pydatetime())
            if not allowed:
                self.rejects[reason] += 1
                continue
            self.summary["valid_m5"] += 1
            for case in cases:
                self._observe(case, bar, at)

    def _observe(self, case, bar, at):
        detector = case["detector"]
        if detector.state.phase in ("invalidated", "bpu2_confirmed"):
            detector.reset()
            case["first_strict"] = False
        case["n_m5"] += 1
        level, tick = case["origin"], case["tick"]
        extreme = float(bar.low if case["side"] == "long" else bar.high)
        distance = abs(extreme-level)/tick
        if case["best_ticks"] is None or distance < case["best_ticks"]:
            case["best_ticks"] = distance
        old = detector.state.phase
        try:
            state = detector.on_bar(ClosedBar(
                ts=at.to_pydatetime(), open=float(bar.open),
                high=float(bar.high), low=float(bar.low),
                close=float(bar.close), volume=float(bar.volume),
                timeframe="M5"))
        except (ValueError, TypeError) as exc:
            self.rejects["M5_DETECTOR:" + str(exc)[:45]] += 1
            return
        if state.phase == "bpu1" and old != "bpu1":
            strict = abs(extreme-level) <= tick*1e-5
            case["first_strict"] = strict
            case["bpu1"] += 1
            self.summary["bpu1"] += 1
            if strict:
                case["strict_bpu1"] += 1
                self.summary["strict_bpu1"] += 1
            if len(self.events) < 12:
                self.events.append(
                    f"QWCT COHORT BPU1 {case['day']} {case['ticker']} "
                    f"{case['side']} level={level:.4f} at={at:%H:%M} "
                    f"strict={int(strict)} basis={case['basis']}")
        elif state.phase == "bpu2_confirmed" and old != "bpu2_confirmed":
            case["bpu2"] += 1
            self.summary["bpu2_closed"] += 1
            if case["first_strict"]:
                case["strict_bpu2"] += 1
                self.summary["strict_bpu2"] += 1
                cutoff = (at-timedelta(seconds=30)).time()
                if any(time.fromisoformat(a) <= cutoff < time.fromisoformat(b)
                       for a, b in self.cfg.session_windows_bounce):
                    self.summary["strict_bpu2_window"] += 1
            if len(self.events) < 12:
                self.events.append(
                    f"QWCT COHORT BPU2 {case['day']} {case['ticker']} "
                    f"{case['side']} level={level:.4f} at={at:%H:%M} "
                    f"strict={int(case['first_strict'])} "
                    "TVX_UNVERIFIED NO ORDERS")
        elif state.phase == "invalidated" and old != "invalidated":
            case["invalid"] += 1
            self.summary["invalidated"] += 1

    def on_end_of_algorithm(self):
        self.log(
            "QWCT COHORT SUMMARY "
            f"scans={self.summary['scheduled_scans']} "
            f"callbacks={self.summary['callbacks']} "
            f"weekend_callbacks={self.summary['weekend_callbacks']} "
            f"days={self.summary['selection_days']} "
            f"stock_days={self.summary['candidate_stock_days']} "
            f"d1_ready={self.summary['d1_ready']} "
            f"stage2={self.summary['stage2_pass']} "
            f"shadow_days={self.summary['shadow_symbol_days']} "
            f"raw_origin_pass={self.origin['PASS']} "
            f"origin_unknown={self.origin['UNKNOWN']} "
            f"origin_fail={self.origin['FAIL']} "
            f"basis_match={self.basis['MATCH']} "
            f"basis_rebased={self.basis['REBASED']} "
            f"ready_origins={self.summary['ready_origins']} "
            f"replay_days={self.summary['after_close_replay_days']} "
            f"m1={self.summary['native_m1']} "
            f"m5={self.summary['valid_m5']} "
            f"m1_tail_close={self.summary['m1_tail_at_close']} "
            f"m1_tail_early={self.summary['m1_tail_before_close']} "
            f"m5_tail_close={self.summary['m5_tail_at_close']} "
            f"m5_tail_early={self.summary['m5_tail_before_close']} "
            f"bpu1={self.summary['bpu1']} "
            f"strict_bpu1={self.summary['strict_bpu1']} "
            f"bpu2={self.summary['bpu2_closed']} "
            f"strict_bpu2={self.summary['strict_bpu2']} "
            f"strict_window={self.summary['strict_bpu2_window']} "
            f"invalid={self.summary['invalidated']}; NO ORDERS")
        self.log(f"QWCT COHORT REJECTS {dict(self.rejects.most_common(12))}")
        for day, ticker, m1, m5, last_m1, last_m5, close in self.tail_examples:
            self.log(
                f"QWCT COHORT TAIL {day} {ticker} m1={m1} m5={m5} "
                f"m1_last={last_m1} m5_last={last_m5} close={close}; "
                "TIMING AUDIT ONLY / NO SYNTHETIC BAR")
        # Distinct observed cases only. Free 10KB log budget.
        rows = sorted(
            (c for c in self.all_cases if c["best_ticks"] is not None),
            key=lambda c: (c["best_ticks"], c["day"], c["ticker"]))
        self.log(
            f"QWCT COHORT COVERAGE tracked={len(self.all_cases)} "
            f"observed={len(rows)} nearest_samples={min(10, len(rows))}")
        for c in rows[:10]:
            self.log(
                f"QWCT COHORT NEAREST {c['day']} {c['ticker']} "
                f"{c['side']} basis={c['basis']} "
                f"m5={c['n_m5']} closest_ticks={c['best_ticks']} "
                f"bpu1={c['bpu1']} bpu2={c['bpu2']}")
        for event in self.events:
            self.log(event + "; CLOSED M5 ONLY / NO FILLS")
