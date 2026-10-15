"""Read-only LEAN point-in-time Qwct dynamic screener diagnostic; no orders."""
from AlgorithmImports import *
from collections import Counter
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy import select_liquid_fundamentals, passes_gerchik_screener
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
            return done("FAIL", "RAW_ORIGIN_OFF_NATIVE_TICK_GRID")
    except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
        return done("UNKNOWN", "RAW_ORIGIN_AUDIT_ERROR:" + str(exc)[:40])
    return done("PASS", "RAW_PIVOT_ONLY;SCALED_RAW_SPLITS_UNVERIFIED")


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
        self.selection_events = []
        self.scan_missing_days = set()
        self.origin_counts = Counter()
        self.origin_details = []
        self.counts = Counter()
        self.rejections = Counter()
        self.example_rows = []
        self.covered_days = set()
        self.stock_day_ids = set()
        self.aligned_day_ids = set()
        self.bsu_role_aligned_day_ids = set()
        self.aligned_distinct_tickers = set()
        self.role_aligned_distinct_tickers = set()
        self.full50_near_tickers = set()
        self.full50_bsu_role_tickers = set()
        self.outside10_examples = []
        self.shadow_picks_logged = []
        self.shadow_unique_tickers = set()
        self.shadow_unique_level_origins = set()
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
        first = next(iter(fundamentals), None)
        sample_at = (str(getattr(first, "time", "NA"))[:32]
                     if first is not None else "NO_INPUT")
        sample_end = (str(getattr(first, "end_time", "NA"))[:32]
                      if first is not None else "NO_INPUT")
        late = day in self.scan_missing_days
        if late:
            self.counts["selection_after_missed_scan"] += 1
        self.selection_events.append((day, et(self.time).isoformat(),
                                      len(selected), sample_at, sample_end))
        self.log(
            f"QWCT UNIVERSE TIMING SELECT day={day} "
            f"clock={et(self.time).isoformat()} sample_time={sample_at} "
            f"sample_end={sample_end} selected={len(selected)} "
            f"after_missed_scan={late}")
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
        self.counts["scheduled_scans"] += 1
        callback_seen = day in self.screen_by_day
        members = self.screen_by_day.get(day)
        if not members:
            self.rejections["missing_same_day_universe"] += 1
            self.scan_missing_days.add(day)
            self.log(
                f"QWCT UNIVERSE TIMING SCAN day={day} "
                f"clock={et(self.time).isoformat()} "
                f"status={'EMPTY_SELECTION' if callback_seen else 'NO_CALLBACK_BEFORE_SCAN'} "
                "no prior-day fallback; NOT zero candidates")
            return
        self.log(
            f"QWCT UNIVERSE TIMING SCAN day={day} "
            f"clock={et(self.time).isoformat()} "
            "status=SAME_DAY_SELECTION_READY")
        self.covered_days.add(day)
        self.counts["days"] += 1
        self.counts["candidate_days"] += len(members)
        try:
            bucket = self._history_asof(members, day)
        except Exception as exc:
            self.rejections["native_history_error:" + str(exc)[:70]] += 1
            return
        passed = []
        qualified_d1 = {}
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
            if obs["role_aligned"]:
                qualified_d1[symbol] = d1
            self.counts["stage2_pass"] += 1
        watchlist = passed[:self.cfg.screener_watchlist_limit]
        shadow = d1_shadow_shortlist(passed, self.cfg.screener_watchlist_limit)
        legacy = {symbol for _, symbol, _ in watchlist}
        overlap = sum(symbol in legacy for _, symbol, _ in shadow)
        self.counts["shadow_symbol_days"] += len(shadow)
        self.counts["shadow_legacy_overlap_symbol_days"] += overlap
        self.counts["shadow_outside_legacy_symbol_days"] += len(shadow)-overlap
        if shadow:
            self.counts["shadow_nonempty_days"] += 1
        for i, (rank, symbol, obs) in enumerate(shadow, start=1):
            self.shadow_unique_tickers.add(symbol.value)
            tick = None
            try:
                tick = float(self.securities[symbol].symbol_properties.minimum_price_variation)
            except Exception:
                pass
            for lvl, side in obs.get("_role_levels", [])[:3]:
                report = origin_d1_audit(
                    qualified_d1[symbol], lvl, day, self.cfg, tick)
                self.origin_counts[report["status"]] += 1
                if len(self.origin_details) < 30:
                    self.origin_details.append((day, symbol.value, side, report))
            for item in obs["shadow_levels"]:
                self.shadow_unique_level_origins.add(
                    (symbol.value, item[0], item[1], item[6]))
            if len(self.shadow_picks_logged) < 25:
                self.shadow_picks_logged.append((
                    day, symbol.value, rank+1, i, obs["shadow_levels"][:3],
                    len(obs["shadow_levels"])))
        self.log(
            f"QWCT SHADOW DAY {day} legacy={len(watchlist)} "
            f"shadow={len(shadow)} overlap={overlap} "
            f"outside_legacy={len(shadow)-overlap} "
            f"rank_tickers={','.join(f'{symbol.value}:{rank+1}' for rank, symbol, _ in shadow)}; "
            "D1 ONLY / NO M5 / NO ORDERS")
        outside = passed[self.cfg.screener_watchlist_limit:]
        self.counts["full50_near_symbol_days"] += sum(
            bool(row[2]["near"]) for row in passed)
        self.counts["full50_scenario_aligned_symbol_days"] += sum(
            bool(row[2]["aligned"]) for row in passed)
        self.counts["full50_bsu_role_aligned_symbol_days"] += sum(
            bool(row[2]["role_aligned"]) for row in passed)
        self.counts["outside10_near_symbol_days"] += sum(
            bool(row[2]["near"]) for row in outside)
        self.counts["outside10_bsu_role_aligned_symbol_days"] += sum(
            bool(row[2]["role_aligned"]) for row in outside)
        self.full50_near_tickers.update(
            symbol.value for _, symbol, obs in passed if obs["near"])
        self.full50_bsu_role_tickers.update(
            symbol.value for _, symbol, obs in passed if obs["role_aligned"])
        for rank, symbol, obs in outside:
            if obs["role_aligned"] and len(self.outside10_examples) < 8:
                self.outside10_examples.append((
                    day, symbol.value, rank+1, obs, obs["examples"][:3]))
        self.counts["watchlist_days"] += len(watchlist)
        for rank, symbol, obs in watchlist:
            label = (day.isoformat(), symbol.value)
            self.stock_day_ids.add(label)
            self.counts["eligible_level_days"] += obs["eligible"]
            self.counts["near_level_days"] += obs["near"]
            self.counts["aligned_level_days"] += obs["aligned"]
            self.counts["bsu_role_aligned_level_days"] += obs["role_aligned"]
            self.counts["bsu_role_conflict_level_days"] += obs["role_conflict"]
            if obs["eligible"]:
                self.counts["watch_with_two_touch"] += 1
            if obs["near"]:
                self.counts["watch_with_near_level"] += 1
            if obs["aligned"]:
                self.counts["watch_with_trend_aligned_bounce"] += 1
                self.aligned_day_ids.add(label)
                self.aligned_distinct_tickers.add(symbol.value)
            if obs["role_aligned"]:
                self.counts["watch_with_bsu_role_aligned"] += 1
                self.bsu_role_aligned_day_ids.add(label)
                self.role_aligned_distinct_tickers.add(symbol.value)
            if obs["near"] and len(self.example_rows) < 16:
                self.example_rows.append((
                    day, symbol.value, rank+1, obs, obs["examples"][:2]))
        self.log(
            f"QWCT UNIVERSE DAY {day} candidates={len(members)} "
            f"d1_qualified={len(passed)} watchlist={len(watchlist)} "
            f"watch_near={sum(x[2]['near']>0 for x in watchlist)} "
            f"watch_aligned={sum(x[2]['aligned']>0 for x in watchlist)} "
            f"watch_bsu_role_aligned={sum(x[2]['role_aligned']>0 for x in watchlist)}; "
            "NO M5 / NO ORDERS")

    def on_end_of_algorithm(self):
        self.log(
            "QWCT UNIVERSE TIMING SUMMARY "
            f"scans={self.counts['scheduled_scans']} "
            f"selection_callbacks={len(self.selection_events)} "
            f"selection_days={len(self.screen_by_day)} "
            f"missed_scan_days={sorted(str(d) for d in self.scan_missing_days)} "
            f"late_callbacks={self.counts['selection_after_missed_scan']}; "
            "missing scan != zero candidates")
        self.log(
            "QWCT ORIGIN SUMMARY "
            f"raw_only_pass={self.origin_counts['PASS']} "
            f"fail={self.origin_counts['FAIL']} "
            f"unknown={self.origin_counts['UNKNOWN']} "
            f"printed={len(self.origin_details)}; "
            "PASS means RAW D1 pivot/grid/chronology ONLY; "
            "SCALED_RAW, split history, canonical BSU and M5 UNVERIFIED")
        for day, ticker, side, row in self.origin_details:
            self.log(
                f"QWCT ORIGIN DETAIL {day} {ticker} side={side} "
                f"cluster={row['cluster']:.6f} "
                f"raw_extreme={row['origin']} source={row['source_date']} "
                f"formed_at={row['formed_at']} confirmed={row['confirmed_at']} "
                f"valid_from={row['valid_from']} tick={row['tick']} "
                f"status={row['status']} reason={row['reason']} "
                f"basis={row['basis']}")
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
            f"bsu_role_aligned_level_days="
            f"{self.counts['bsu_role_aligned_level_days']} "
            f"bsu_role_conflict_level_days="
            f"{self.counts['bsu_role_conflict_level_days']} "
            f"watch_with_bsu_role_aligned="
            f"{self.counts['watch_with_bsu_role_aligned']} "
            f"unique_symbol_days={len(self.stock_day_ids)} "
            f"unique_aligned_symbol_days={len(self.aligned_day_ids)} "
            f"unique_aligned_tickers={len(self.aligned_distinct_tickers)} "
            f"unique_bsu_role_aligned_symbol_days="
            f"{len(self.bsu_role_aligned_day_ids)} "
            f"unique_bsu_role_aligned_tickers="
            f"{len(self.role_aligned_distinct_tickers)} "
            f"rejects={dict(self.rejections.most_common(4))}; "
            "NO M5 / NO SEC / NO ORDERS")
        self.log(
            "QWCT SHADOW SUMMARY "
            f"cap={self.cfg.screener_watchlist_limit} "
            f"days={self.counts['days']} "
            f"nonempty_days={self.counts['shadow_nonempty_days']} "
            f"shadow_symbol_days={self.counts['shadow_symbol_days']} "
            f"legacy_overlap_symbol_days="
            f"{self.counts['shadow_legacy_overlap_symbol_days']} "
            f"outside_legacy_symbol_days="
            f"{self.counts['shadow_outside_legacy_symbol_days']} "
            f"unique_shadow_tickers={len(self.shadow_unique_tickers)} "
            f"unique_shadow_level_origins={len(self.shadow_unique_level_origins)} "
            f"pick_rows_logged={len(self.shadow_picks_logged)}; "
            "D1 ONLY / NO M5 / NO SEC / NO ORDERS")
        for day, ticker, legacy_rank, shadow_rank, levels, count in self.shadow_picks_logged:
            self.log(
                f"QWCT SHADOW PICK {day} {ticker} "
                f"liquidity_rank={legacy_rank} shadow_rank={shadow_rank} "
                f"qualified_levels={count} evidence={levels}; "
                "D1 ONLY / NO M5 / NO ORDERS")
        self.log(
            "QWCT UNIVERSE FULL50 "
            f"stage2_symbol_days={self.counts['stage2_pass']} "
            f"near_symbol_days={self.counts['full50_near_symbol_days']} "
            f"scenario_aligned_symbol_days="
            f"{self.counts['full50_scenario_aligned_symbol_days']} "
            f"bsu_role_aligned_symbol_days="
            f"{self.counts['full50_bsu_role_aligned_symbol_days']} "
            f"outside10_near_symbol_days="
            f"{self.counts['outside10_near_symbol_days']} "
            f"outside10_bsu_role_aligned_symbol_days="
            f"{self.counts['outside10_bsu_role_aligned_symbol_days']} "
            f"unique_near_tickers={len(self.full50_near_tickers)} "
            f"unique_bsu_role_aligned_tickers="
            f"{len(self.full50_bsu_role_tickers)}; "
            "D1 ONLY / NO M5 / NO ORDERS")
        for day, ticker, rank, obs, levels in self.outside10_examples:
            self.log(
                f"QWCT UNIVERSE OUTSIDE10 {day} {ticker} "
                f"rank={rank} close={obs['price']:.4f} "
                f"atr={obs['atr']:.4f} "
                f"bsu_role_aligned={obs['role_aligned']} "
                f"near_levels={levels}; D1 ONLY / NO ORDERS")
        for day, ticker, rank, obs, levels in self.example_rows:
            self.log(
                f"QWCT UNIVERSE EXAMPLE {day} {ticker} rank={rank} "
                f"close={obs['price']:.4f} atr={obs['atr']:.4f} "
                f"near={obs['near']} trend_aligned_levels={obs['aligned']} "
                f"bsu_role_aligned_levels={obs['role_aligned']} "
                f"levels={levels}; D1 ONLY / NO ORDERS")
