"""Qwct BSU-Research: structural levels / native RAW M5, no orders.

Standalone QuantConnect Cloud research project; does not import or modify
the main Qwct strategy. Reuses canonical strategy levels and BsuDetector.
Results are hypotheses, NOT canonical Gerchik signals or a P&L backtest.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import datetime, timedelta, time
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.levels import levels_for_session, native_cluster_tolerance
from strategy.native_m5_validation import validate_m5_tradebar
from strategy.patterns_bsu import Bar as ResearchBar, BsuDetector


ET = ZoneInfo("America/New_York")


def et(value):
    """Interpret LEAN naive timestamps as exchange-local, never as UTC."""
    t = pd.Timestamp(value)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


class QwctBsuResearch(QCAlgorithm):
    def initialize(self):
        start = datetime.strptime(
            self.get_parameter("scan_start") or "2024-03-16", "%Y-%m-%d")
        end = datetime.strptime(
            self.get_parameter("scan_end") or "2024-04-26", "%Y-%m-%d")
        if end < start or (end - start).days > 45:
            raise ValueError("Research scan requires a 0..45 day window")
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_time_zone("America/New_York")
        self.set_cash(25_000)
        self.cfg = StrategyConfig()
        self.symbols_to_scan = ()
        self.active = {}
        self.case_nearest = {}
        self.counts = Counter()
        self.rejections = Counter()
        self._quarantined = set()
        self._events_logged = 0
        # Keep genuine completed BPU2 candle evidence separate from
        # the small real-time log budget; no reconstructed OHLC/fills.
        self._bpu2_proofs = []
        # Completely independent comparison: native LEAN PPHL D1 origins
        # absent from the existing 2-swing Qwct level observer set.
        # Never passes candidates to the original signal or order path.
        self._raw_d1 = {}
        self.pphl_shadow = {}
        self.pphl_counts = Counter()
        self.pphl_rejects = Counter()
        self.pphl_unique = set()
        self.pphl_only_unique = set()
        self.pphl_samples_logged = 0
        # Keep every observed strict+time-window M5 pair as native
        # provenance evidence, even after capped live logs fill up.
        self.pphl_in_window_proofs = []
        self.pphl_window_unique = set()
        self.pphl_offgrid_unique = set()
        self.pphl_offgrid_samples = []
        # Deliberately fixed first test universe. This is NOT a marketwide
        # point-in-time screener and does not certify other US equities.
        for name in ("MSFT", "AMZN", "AAPL"):
            sym = self.add_equity(
                name, Resolution.MINUTE, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            self.securities[sym].set_data_normalization_mode(
                DataNormalizationMode.RAW)
            self.symbols_to_scan += (sym,)
            # Native LEAN TimePeriod consolidator: no invented M5 prices.
            self.consolidate(sym, timedelta(minutes=5), self._on_m5)

        clock = self.symbols_to_scan[0]
        self.schedule.on(
            self.date_rules.every_day(clock),
            self.time_rules.before_market_open(clock, 1),
            self._prepare_session)
        self.debug(
            f"BSU RESEARCH ACTIVE {start.date()}..{end.date()} "
            "MSFT,AMZN,AAPL; ALL ORDERS DISABLED; "
            "RAW D1/RAW native M5; no Bounce Score; TVX NOT tested")
        self.debug("BSU RESEARCH PPHL SHADOW: native D1 pivots,"
                   " single-swing vs Qwct clustered origins; no orders")

    def _closed_daily(self, symbol):
        raw = [
            bar for packet in self.history[TradeBar](
                [symbol], 180, Resolution.DAILY, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW)
            for key, bar in packet.items() if key == symbol
        ]
        if len(raw) < 60:
            raise ValueError("not enough as-of native RAW daily bars")
        native_atr = AverageTrueRange(
            self.cfg.atr_period, MovingAverageType.WILDERS)
        rows, days = [], []
        prev_day = None
        seen_at = et(self.time)
        for bar in raw:
            opened, closed = et(bar.time), et(bar.end_time)
            day = opened.date()
            if (day >= seen_at.date() or closed >= seen_at
                    or closed <= opened or
                    (prev_day is not None and day <= prev_day)):
                raise ValueError("non-as-of, duplicate, or unordered RAW daily")
            prev_day = day
            native_atr.update(bar)
            rows.append({
                "open": float(bar.open), "high": float(bar.high),
                "low": float(bar.low), "close": float(bar.close),
                "volume": float(bar.volume),
                "bar_end": closed,
                "atr14": (float(native_atr.current.value)
                          if native_atr.is_ready else float("nan")),
            })
            days.append(opened.normalize())
        d1 = pd.DataFrame(rows, index=pd.DatetimeIndex(days))
        if not d1.index.is_unique:
            raise ValueError("RAW daily duplicate dates")
        if not (isfinite(float(d1["atr14"].iloc[-1]))
                and float(d1["atr14"].iloc[-1]) > 0):
            raise ValueError("native daily ATR not ready")
        self._raw_d1[symbol] = raw
        return d1

    def _pphl_candidates(self, sym, d1, states, tick, session):
        """Read-only native PPHL pivot events confirmed using closed RAW D1.

        PPHL's current indicator output is +1 (new high), -1 (new
        low), 2 (both), 0 (none). Unlike reading final ZigZag pivots,
        this records an event only AFTER it is confirmed by the k-th
        right-side daily bar. Never infer the pivot at its origin date.
        The detector source is LEAN's PivotPointsHighLow, not a homemade
        high/low pivot implementation.
        """
        from AlgorithmImports import PivotPointsHighLow

        k = self.cfg.swing_k
        native = PivotPointsHighLow(k, k, 100)
        source = self._raw_d1[sym]
        found = []
        # Streaming native updates establish the *confirmation* timestamp.
        for i, daily in enumerate(source):
            native.update(daily)
            if i < 2 * k or not native.is_ready:
                continue
            event = int(round(float(native.current.value)))
            if event not in (-1, 1, 2):
                continue
            pivot_index = i - k
            orig = d1.iloc[pivot_index]
            origin_end = et(orig["bar_end"])
            confirmed_at = et(daily.end_time)
            if (origin_end >= confirmed_at
                    or confirmed_at >= et(self.time)):
                raise ValueError("PPHL causal confirmation invariant violated")
            for kind in (("short",) if event == 1 else
                         ("long",) if event == -1 else ("short", "long")):
                price = float(orig["high" if kind == "short" else "low"])
                if not isfinite(price) or price <= 0:
                    self.pphl_rejects["nonfinite PPHL origin price"] += 1
                    continue
                if abs(price - round(price / tick) * tick) > tick * 1e-5:
                    self.pphl_rejects["off-grid native PPHL origin"] += 1
                    offgrid_key = (
                        sym.value, kind, origin_end.isoformat(),
                        round(price, 6))
                    if offgrid_key not in self.pphl_offgrid_unique:
                        self.pphl_offgrid_unique.add(offgrid_key)
                        if len(self.pphl_offgrid_samples) < 3:
                            self.pphl_offgrid_samples.append(
                                (sym.value, kind, origin_end.isoformat(),
                                 price, tick))
                    # Never round an off-grid source to generate a
                    # detector event or an invented exact touch.
                    continue
                found.append((kind, price, origin_end, confirmed_at))
        # The most recent 100 pivot origins, consistent with PPHL's
        # documented bounded history. Report any discarded old sources.
        if len(found) > 100:
            self.pphl_counts["older_pivots_skipped"] += len(found) - 100
            found = found[-100:]
        out = []
        last_atr = float(d1["atr14"].iloc[-1])
        for side, price, born, confirmed in found:
            key = (sym.value, side, born.isoformat(), round(price / tick))
            self.pphl_unique.add(key)
            self.pphl_counts["level_days"] += 1
            # Compare the actual raw pivot origin, not a rounded
            # cluster median. An equal price at another origin time is
            # a different historical swing.
            matched = any(
                x["side"] == side
                and x["origin_time"] == born.isoformat()
                and abs(x["origin"] - price) <= tick * 1e-5
                for x in states)
            if matched:
                self.pphl_counts["overlap_level_days"] += 1
                continue
            self.pphl_counts["only_level_days"] += 1
            self.pphl_only_unique.add(key)
            out.append({
                "symbol": sym.value, "session": str(session),
                "origin": price, "origin_time": born.isoformat(),
                "confirmed_at": confirmed.isoformat(),
                "side": side, "tick": tick,
                "detector": BsuDetector(
                    self.cfg, price, side, atr_value=last_atr,
                    tick_size=tick, bsu_ts=born.to_pydatetime()),
                "bpu1_strict": False,
                "bpu1_observed": None,
            })
        return out

    def _prepare_session(self):
        self.active.clear()
        self.pphl_shadow.clear()
        self._raw_d1.clear()
        session = et(self.time).date()
        count = 0
        for sym in self.symbols_to_scan:
            try:
                d1 = self._closed_daily(sym)
                tol = native_cluster_tolerance(d1, self.cfg)
                tick = float(
                    self.securities[sym].symbol_properties.minimum_price_variation)
                if (tol is None or not isfinite(tick) or tick <= 0):
                    raise ValueError("no native tick or ATR cluster tolerance")
                levels = levels_for_session(d1, session, self.cfg)
                states = []
                for lvl in levels:
                    if (lvl.source != "swing_cluster"
                            or lvl.kind not in ("support", "resistance")
                            or lvl.touches < self.cfg.min_touches
                            or lvl.strength < self.cfg.min_level_strength
                            or not 0 <= lvl.first_idx < len(d1)):
                        continue
                    origin = float(d1.iloc[lvl.first_idx][
                        "low" if lvl.kind == "support" else "high"])
                    origin_end = et(d1.iloc[lvl.first_idx]["bar_end"])
                    if (not isfinite(origin) or origin <= 0
                            or origin_end >= et(self.time)
                            or abs(origin - round(origin/tick)*tick) > tick*1e-5
                            or abs(origin-lvl.price) > tol + 1e-8):
                        self.rejections["origin invalid RAW/tick/cluster"] += 1
                        continue
                    side = "long" if lvl.kind == "support" else "short"
                    detector = BsuDetector(
                        self.cfg, origin, side,
                        atr_value=float(d1["atr14"].iloc[-1]),
                        tick_size=tick, bsu_ts=origin_end.to_pydatetime())
                    states.append({
                        "detector": detector,
                        "origin": origin, "tick": tick, "side": side,
                        "session": session, "symbol": sym.value,
                        "origin_time": origin_end.isoformat(),
                        "cluster": float(lvl.price),
                        "bpu1_bar": None,
                        "bpu1_strict": False,
                    })
                self.active[sym] = states
                count += len(states)
                self.counts["symbols_warmed"] += 1
                # The independent PPHL comparison can fail without
                # suppressing a proven Qwct baseline observation.
                try:
                    self.pphl_shadow[sym] = self._pphl_candidates(
                        sym, d1, states, tick, session)
                    self.pphl_counts["prepared_symbol_days"] += 1
                except Exception as shadow_error:
                    self.pphl_shadow[sym] = []
                    self.pphl_rejects[
                        "PPHL_FAIL: " + str(shadow_error)[:95]] += 1
            except Exception as exc:
                # Fail closed for this symbol/day. Do not fabricate candles.
                self.active[sym] = []
                self.pphl_shadow[sym] = []
                self.rejections[str(exc)[:75]] += 1
        self.counts["bsu_observer_days"] += count

    def on_data(self, data):
        # A native split invalidates today's RAW pivot and M5 observation.
        splits = getattr(data, "splits", None)
        if splits is None:
            return
        for symbol, event in splits.items():
            if (getattr(event, "type", None) == SplitType.SPLIT_OCCURRED
                    and symbol in self.active):
                self.active[symbol] = []
                self.pphl_shadow[symbol] = []
                self._quarantined.add((symbol, et(self.time).date()))
                self.rejections["LEAN split occurred: day quarantined"] += 1

    def _on_pphl_m5(self, bar, current):
        # Shadow candidates use the *same already validated native
        # consolidated TradeBar* as the main research detector.
        for case in self.pphl_shadow.get(bar.symbol, []):
            det = case["detector"]
            if det.state.phase in ("invalidated", "bpu2_confirmed"):
                det.reset()
                case["bpu1_strict"] = False
                case["bpu1_observed"] = None
            self.pphl_counts["only_m5_checks"] += 1
            side, pivot, tick = case["side"], case["origin"], case["tick"]
            extreme = float(bar.low if side == "long" else bar.high)
            old = det.state.phase
            try:
                result = det.on_bar(ResearchBar(
                    ts=current.to_pydatetime(),
                    open=float(bar.open), high=float(bar.high),
                    low=float(bar.low), close=float(bar.close),
                    volume=float(bar.volume), timeframe="M5"))
            except (TypeError, ValueError) as exc:
                self.pphl_rejects["PPHL_M5_FAIL: " + str(exc)[:60]] += 1
                continue
            if result.phase == "bpu1" and old != "bpu1":
                self.pphl_counts["only_bpu1_detector"] += 1
                case["bpu1_strict"] = abs(extreme - pivot) <= tick * 1e-5
                case["bpu1_observed"] = (
                    current.strftime("%Y-%m-%d %H:%M"),
                    float(bar.open), float(bar.high),
                    float(bar.low), float(bar.close), float(bar.volume))
                if case["bpu1_strict"]:
                    self.pphl_counts["only_bpu1_strict"] += 1
                    if self.pphl_samples_logged < 5:
                        self.log(
                            f"BSU PPHL ONLY BPU1 {case['symbol']} "
                            f"{current:%Y-%m-%d %H:%M} {side} "
                            f"origin={pivot:.4f} "
                            f"confirmed={case['confirmed_at'][:16]}; NO ORDERS")
                        self.pphl_samples_logged += 1
            elif result.phase == "bpu2_confirmed" and old != "bpu2_confirmed":
                self.pphl_counts["only_bpu2_detector"] += 1
                if not case["bpu1_strict"]:
                    continue
                self.pphl_counts["only_bpu2_strict"] += 1
                preclose_time = (current - pd.Timedelta(seconds=30)).time()
                allowed = any(
                    time.fromisoformat(a) <= preclose_time
                    < time.fromisoformat(b)
                    for a, b in self.cfg.session_windows_bounce)
                if allowed:
                    self.pphl_counts["only_bpu2_strict_in_window"] += 1
                    first = case.get("bpu1_observed")
                    if first is None:
                        self.pphl_rejects["strict window BPU2 missing BPU1 OHLC"] += 1
                    else:
                        episode_key = (
                            case["symbol"], str(current.date()), side,
                            case["origin_time"], round(pivot / tick))
                        self.pphl_window_unique.add(episode_key)
                        self.pphl_in_window_proofs.append((
                            case["symbol"], current.strftime("%Y-%m-%d %H:%M"),
                            side, pivot, case["origin_time"],
                            case["confirmed_at"], tick, first,
                            (float(bar.open), float(bar.high),
                             float(bar.low), float(bar.close),
                             float(bar.volume)),
                            float(det.state.stop_price),
                            float(det.state.luft)))
                if self.pphl_samples_logged < 5:
                    self.log(
                        f"BSU PPHL ONLY BPU2 {case['symbol']} "
                        f"{current:%Y-%m-%d %H:%M} {side} "
                        f"origin={pivot:.4f} "
                        f"window={'YES' if allowed else 'NO'}; "
                        "NO SEC TVX / NO ORDERS")
                    self.pphl_samples_logged += 1

    def _on_m5(self, bar):
        sym = bar.symbol
        if sym not in self.active:
            return
        current = et(bar.end_time)
        if ((sym, current.date()) in self._quarantined
                or current.date() != et(self.time).date()
                or not time(9, 35) <= current.time() <= time(16, 0)):
            return
        good, reason = validate_m5_tradebar(
            bar, current.to_pydatetime())
        if not good:
            self.rejections[reason] += 1
            return
        self.counts["native_m5_bars"] += 1
        self._on_pphl_m5(bar, current)
        for case in self.active[sym]:
            detector = case["detector"]
            if detector.state.phase in ("invalidated", "bpu2_confirmed"):
                detector.reset()
                case["bpu1_bar"] = None
                case["bpu1_strict"] = False
            pivot, tick, side = case["origin"], case["tick"], case["side"]
            extreme = float(bar.low if side == "long" else bar.high)
            gap = extreme - pivot
            label = (case["symbol"], str(case["session"]), side,
                     round(pivot / tick))
            previous = self.case_nearest.get(label)
            if previous is None or abs(gap) < abs(previous[0]):
                self.case_nearest[label] = (
                    gap, case["symbol"], str(case["session"]), side,
                    pivot, extreme, current.strftime("%H:%M"), tick)
            self.counts["native_m5_level_checks"] += 1
            old = detector.state.phase
            try:
                result = detector.on_bar(ResearchBar(
                    ts=current.to_pydatetime(),
                    open=float(bar.open), high=float(bar.high),
                    low=float(bar.low), close=float(bar.close),
                    volume=float(bar.volume), timeframe="M5"))
            except (ValueError, TypeError) as exc:
                self.rejections["BPU bar invalid: "+str(exc)[:60]] += 1
                continue
            if result.phase == "bpu1" and old != "bpu1":
                # Actual completed native M5 candle, captured when BPU1
                # appeared. Do not infer it from the later BPU2 candle.
                case["bpu1_bar"] = (
                    current.strftime("%Y-%m-%d %H:%M"),
                    float(bar.open), float(bar.high),
                    float(bar.low), float(bar.close),
                    float(bar.volume))
                # Detector admits <= half a reference tick (180.145 vs
                # 180.140 on AMZN); that is NOT strict price equality.
                # Keep its original observation count for comparability,
                # but never call a half-tick proxy "exact" in the logs.
                bpu1_delta = abs(extreme - pivot)
                bpu1_strict = bpu1_delta <= tick * 1e-5
                case["bpu1_strict"] = bpu1_strict
                if bpu1_strict:
                    self.counts["strict_bpu1"] += 1
                else:
                    self.counts["near_half_tick_bpu1"] += 1
                self.counts["native_bpu1"] += 1
                if self._events_logged < 7:
                    self.log(f"BSU RESEARCH BPU1 {case['symbol']} "
                             f"{current:%Y-%m-%d %H:%M} "
                             f"{side} pivot={pivot:.4f} "
                             f"observed={extreme:.4f} "
                             f"strict={'YES' if bpu1_strict else 'NO'}; "
                             "NO ORDERS")
                    self._events_logged += 1
            elif result.phase == "bpu2_confirmed" and old != "bpu2_confirmed":
                self.counts["closed_bpu2_proxy"] += 1
                first = case.get("bpu1_bar")
                if first is None:
                    self.rejections["BPU2 without retained BPU1 candle"] += 1
                else:
                    # This is only a *separate reporting flag*. It never
                    # gates/moves a detector event or authorizes a trade.
                    # Actual TVX would be sampled 30s BEFORE BPU2 close.
                    # Time eligibility is only a separate research flag;
                    # SEC/TICK timing and order placement are NOT inferred.
                    hypothetical_tvx = (
                        current - pd.Timedelta(seconds=30)).time()
                    in_bounce_window = any(
                        time.fromisoformat(a) <= hypothetical_tvx
                        < time.fromisoformat(b)
                        for a, b in self.cfg.session_windows_bounce)
                    if in_bounce_window:
                        self.counts["bpu2_in_bounce_window"] += 1
                    if case["bpu1_strict"]:
                        self.counts["strict_bpu2_closed"] += 1
                        if in_bounce_window:
                            self.counts["strict_bpu2_in_window"] += 1
                    else:
                        self.counts["half_tick_predecessor_bpu2"] += 1
                    # Original on-grid BPU1 comparison is visible even
                    # when subsequent RAW TradeBar highs show subpennies.
                    first_extreme = first[3] if side == "long" else first[2]
                    first_diff_ticks = abs(first_extreme - pivot) / tick
                    second_extreme = (float(bar.low) if side == "long"
                                      else float(bar.high))
                    second_grid_offset = abs(
                        second_extreme - round(second_extreme/tick)*tick)/tick
                    self._bpu2_proofs.append((
                        case["symbol"], current.strftime("%Y-%m-%d %H:%M"),
                        side, pivot, case["origin_time"], case["cluster"],
                        first, (float(bar.open), float(bar.high),
                                float(bar.low), float(bar.close),
                                float(bar.volume)),
                        first_diff_ticks, second_grid_offset,
                        in_bounce_window, case["bpu1_strict"],
                        float(detector.state.luft),
                        float(detector.state.stop_price)))
                if self._events_logged < 7:
                    self.log(f"BSU RESEARCH BPU2 {case['symbol']} "
                             f"{current:%Y-%m-%d %H:%M} "
                             f"{side} level={pivot:.4f}; "
                             "NO -30s TVX PROOF / NO ORDERS")
                    self._events_logged += 1
            elif result.phase == "invalidated":
                self.counts["invalid_bpu2_attempts"] += 1

    def _audit_native_sec_preclose(self, proof):
        """Retrospective, read-only native SECOND TradeBar as-of-cutoff audit.

        This runs at backtest END, not at the historical cutoff second.
        Data strictly later than BPU2-30s is excluded from every computed
        value. It is not a real-time TVX observation, quote or fill.
        """
        (ticker, event_at, side, pivot, born, confirmed, tick, first,
         closed_bpu2, stop, luft) = proof
        sym = next((s for s in self.symbols_to_scan
                    if s.value == ticker), None)
        if sym is None:
            return "NO_SYMBOL", 0, None, None, None
        bpu1_end = datetime.strptime(first[0], "%Y-%m-%d %H:%M")
        bpu2_end = datetime.strptime(event_at, "%Y-%m-%d %H:%M")
        if bpu2_end - bpu1_end != timedelta(minutes=5):
            return "BAD_BPU_TIMING", 0, None, None, None
        cutoff = bpu2_end - timedelta(seconds=30)
        # Python history date-range arguments are algorithm-local ET;
        # the upper bound is exclusive. We still enforce <= cutoff
        # on every actual TradeBar END TIME, regardless of API behavior.
        hist_end = cutoff + timedelta(seconds=1)
        try:
            rows = [
                bar for packet in self.history[TradeBar](
                    [sym], bpu1_end, hist_end, Resolution.SECOND,
                    fill_forward=False,
                    data_normalization_mode=DataNormalizationMode.RAW)
                for key, bar in packet.items() if key == sym
            ]
        except Exception as exc:
            return "HISTORY_ERROR:" + str(exc)[:90], 0, None, None, None
        selected = []
        for bar in rows:
            try:
                start = et(bar.time)
                end = et(bar.end_time)
                if (end <= et(bpu1_end) or end > et(cutoff)
                        or end-start != pd.Timedelta(seconds=1)):
                    return "INVALID_1S_INTERVAL", len(selected), None, None, None
                if (not isfinite(float(bar.volume))
                        or float(bar.volume) <= 0
                        or not all(isfinite(float(v)) and float(v) > 0
                                   for v in (bar.low, bar.high, bar.close))):
                    return "INVALID_1S_TRADE", len(selected), None, None, None
                selected.append(bar)
            except (ValueError, TypeError, OverflowError) as exc:
                return "BAD_1S_TRADE:" + str(exc)[:65], len(selected), None, None, None
        if not selected:
            return "NO_SECOND_TRADES", 0, None, None, None
        selected.sort(key=lambda bar: et(bar.end_time))
        if any(et(b.end_time) <= et(a.end_time)
               for a, b in zip(selected, selected[1:])):
            return "DUPLICATE_1S_TIMESTAMPS", len(selected), None, None, None
        if et(selected[-1].end_time) != et(cutoff):
            return "NO_TRADE_AT_EXACT_CUTOFF", len(selected), None, None, None
        high = max(float(bar.high) for bar in selected)
        low = min(float(bar.low) for bar in selected)
        last = float(selected[-1].close)
        # A partial 4m30s BPU2 trade range must be contained in the
        # independently observed completed native RAW M5 OHLC.
        if (low < closed_bpu2[2]-1e-7 or
                high > closed_bpu2[1]+1e-7):
            return "M5_SEC_RAW_MISMATCH", len(selected), low, high, last
        tol = tick / 2
        if side == "short":
            okay = (high <= first[2] + tol
                    and high >= pivot - luft - tol)
        else:
            okay = (low >= first[3] - tol
                    and low <= pivot + luft + tol)
        return ("RETROSPECTIVE_RULE_PASS" if okay
                else "RETROSPECTIVE_RULE_FAIL"), len(selected), low, high, last

    def on_end_of_algorithm(self):
        self.log(
            "BSU PPHL COMPARE "
            f"prepared_days={self.pphl_counts['prepared_symbol_days']} "
            f"pphl_level_days={self.pphl_counts['level_days']} "
            f"overlap={self.pphl_counts['overlap_level_days']} "
            f"pphl_only_level_days={self.pphl_counts['only_level_days']} "
            f"unique_pphl_origins={len(self.pphl_unique)} "
            f"unique_pphl_only_origins={len(self.pphl_only_unique)} "
            f"pphl_only_M5_checks={self.pphl_counts['only_m5_checks']} "
            f"pphl_only_BPU1={self.pphl_counts['only_bpu1_detector']} "
            f"pphl_only_BPU1_strict={self.pphl_counts['only_bpu1_strict']} "
            f"pphl_only_BPU2={self.pphl_counts['only_bpu2_detector']} "
            f"pphl_only_BPU2_strict={self.pphl_counts['only_bpu2_strict']} "
            f"pphl_only_strict_in_window="
            f"{self.pphl_counts['only_bpu2_strict_in_window']} "
            f"older_pivots_skipped="
            f"{self.pphl_counts['older_pivots_skipped']} "
            f"pphl_errors={dict(self.pphl_rejects.most_common(3))}; "
            "NO SEC TVX / NO ORDERS")
        self.log(
            "BSU PPHL EVIDENCE "
            f"strict_in_window_events="
            f"{self.pphl_counts['only_bpu2_strict_in_window']} "
            f"unique_level_day_episodes={len(self.pphl_window_unique)} "
            f"offgrid_rejections={self.pphl_rejects['off-grid native PPHL origin']} "
            f"unique_offgrid_origins={len(self.pphl_offgrid_unique)} "
            "NO SEC TVX / NO ORDERS")
        for symbol, event_at, side, price, born, confirmed, tick, first, second, stop, luft in self.pphl_in_window_proofs[:12]:
            extreme = first[3] if side == "long" else first[2]
            self.log(
                f"BSU PPHL WINDOW PROOF {symbol} BPU2={event_at} {side} "
                f"pivot={price:.4f} origin={born[:16]} "
                f"confirmed={confirmed[:16]} "
                f"BPU1={first[0]} strict_ticks={abs(extreme-price)/tick:.6f}; "
                "CLOSED M5 ONLY / NO SEC TVX")
            self.log(
                f"BSU PPHL WINDOW OHLC {symbol} "
                f"BPU1={first[1]:.4f}/{first[2]:.4f}/{first[3]:.4f}/{first[4]:.4f} "
                f"BPU2={second[0]:.4f}/{second[1]:.4f}/{second[2]:.4f}/{second[3]:.4f} "
                f"stop={stop:.4f} luft={luft:.4f}; NO ORDERS")
        if len(self.pphl_in_window_proofs) > 12:
            self.log(
                f"BSU PPHL WINDOW PROOF omitted="
                f"{len(self.pphl_in_window_proofs)-12}; NO ORDERS")
        for symbol, side, born, price, tick in self.pphl_offgrid_samples:
            self.log(
                f"BSU PPHL OFFGRID {symbol} {side} "
                f"origin={born[:16]} RAW={price:.6f} "
                f"ref_tick={tick:.6f} SKIPPED; NO ORDERS")
        # Request native SECOND trade bars only for completed strict
        # BPU2 events inside the previously configured bounce window.
        # This uses retrospective history with an explicit -30s cutoff,
        # not an event-driven live preclose signal or executable quote.
        sec_summary = Counter()
        for proof in self.pphl_in_window_proofs[:12]:
            label, count, low, high, last = self._audit_native_sec_preclose(proof)
            sec_summary[label.split(":")[0]] += 1
            symbol, when = proof[0], proof[1]
            vals = (f"low={low:.4f} high={high:.4f} "
                    f"last={last:.4f}" if low is not None and high is not None
                    and last is not None else "OHLC=UNKNOWN")
            self.log(
                f"BSU PPHL SEC RETRO {symbol} BPU2={when} "
                f"seconds={count} status={label} {vals}; "
                "historical as-of cutoff only / NO REAL-TIME TVX / NO ORDERS")
        if len(self.pphl_in_window_proofs) > 12:
            sec_summary["PROOFS_NOT_QUERIED"] += len(self.pphl_in_window_proofs) - 12
        self.log(
            f"BSU PPHL SEC SUMMARY cases={len(self.pphl_in_window_proofs)} "
            f"status_counts={dict(sec_summary)}; "
            "SEC trade prices, not execution quotes; NO ORDERS")
        best = sorted(self.case_nearest.values(), key=lambda r: abs(r[0]))[:8]
        self.log("BSU RESEARCH SUMMARY "
                 f"symbols_warmed={self.counts['symbols_warmed']} "
                 f"candidate_level_days={self.counts['bsu_observer_days']} "
                 f"M5={self.counts['native_m5_bars']} "
                 f"checks={self.counts['native_m5_level_checks']} "
                 f"BPU1={self.counts['native_bpu1']} "
                 f"BPU2_closed={self.counts['closed_bpu2_proxy']} "
                 f"invalid={self.counts['invalid_bpu2_attempts']} "
                 f"rejects={dict(self.rejections.most_common(3))}; NO ORDERS")
        for gap, ticker, day, side, pivot, extreme, at, tick in best:
            self.log(f"BSU RESEARCH NEAREST {ticker} {day} {side} "
                     f"RAW_BSU={pivot:.4f} M5={extreme:.4f} "
                     f"gap={gap:+.4f} ticks={abs(gap/tick):.1f} "
                     f"at={at}; NOT necessarily BPU1")
        # Every completed BPU2 gets an independently capped, native
        # M5 OHLC evidence pair, even if the first-7 event log filled up.
        for ticker, at, side, pivot, origin, cluster, first, second, dist, grid, allowed, strict, luft, stop in self._bpu2_proofs[:8]:
            self.log(f"BSU RESEARCH PROOF {ticker} BPU2={at} {side} "
                     f"BSU={pivot:.4f} origin={origin[:16]} "
                     f"cluster={cluster:.4f} BPU1={first[0][-5:]} "
                     f"dist_ticks={dist:.6f} BPU1_strict={'YES' if strict else 'NO'} "
                     f"bounce_window={'YES' if allowed else 'NO'}")
            self.log(f"BSU RESEARCH OHLC {ticker} "
                     f"BPU1={first[1]:.4f}/{first[2]:.4f}/{first[3]:.4f}/{first[4]:.4f} "
                     f"BPU2={second[0]:.4f}/{second[1]:.4f}/{second[2]:.4f}/{second[3]:.4f} "
                     f"BPU2_ext_grid_off_ticks={grid:.3f} "
                     f"stop={stop:.4f} luft={luft:.4f}; NO ORDERS")
        if len(self._bpu2_proofs) > 8:
            self.log(f"BSU RESEARCH PROOF omitted="
                     f"{len(self._bpu2_proofs)-8}; NO ORDERS")
        self.log(f"BSU RESEARCH ELIGIBILITY BPU1_detector="
                 f"{self.counts['native_bpu1']} "
                 f"BPU1_strict={self.counts['strict_bpu1']} "
                 f"BPU1_half_tick={self.counts['near_half_tick_bpu1']} "
                 f"BPU2_detector={self.counts['closed_bpu2_proxy']} "
                 f"BPU2_with_strict_BPU1={self.counts['strict_bpu2_closed']} "
                 f"strict_in_bounce_window="
                 f"{self.counts['strict_bpu2_in_window']}; "
                 "NO SEC TVX / NO ORDERS")
