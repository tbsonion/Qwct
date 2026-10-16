"""QWCT 5.0: 10 causal, overlapping reactions near a FROZEN M5 level.

Research-only software tags, NOT 10 certified Gerchik trading models.
No orders, BPU1/BPU2 promotion, synthetic bars or lookahead. Heuristic
parameters are engineering choices, not original-author thresholds.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

KINDS = (
    "BOUNCE", "WICK_BOUNCE", "WICK_RECLAIM", "FALSE_BREAK_1BAR",
    "FALSE_BREAK_2BAR", "BREAK_FOLLOWTHROUGH", "MIRROR_RETEST",
    "COMPRESSION", "CONSOLIDATION", "CHOP",
)
ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class M5ReactionEvent:
    kind: str
    level_price: float
    side: str
    bar_end: datetime
    anchor_end: datetime
    reason: str
    can_trade: bool = False


@dataclass(frozen=True)
class M5ReactionHeuristics:
    wick_fraction_of_range: float = 0.40
    compression_bars: int = 4
    compression_range_fraction: float = 0.80
    consolidation_bars: int = 5
    consolidation_min_intersections: int = 3
    chop_bars: int = 6
    chop_min_flips: int = 3
    proximity_m5_atr: float = 0.80
    consolidation_width_m5_atr: float = 1.60
    chop_width_m5_atr: float = 2.0
    chop_net_m5_atr: float = 0.60


class M5TenReactionObserver:
    """Classify closed native M5 candles relative to one PRE-EXISTING line.

    side='long' means the level is support from above; 'short', resistance
    from below. This observer never discovers or reprices a BSU level.
    A missing M5 cancels multi-bar inference; no continuity is fabricated.
    ATR must be actual causal M5 Wilder ATR and is needed only for 8-10.
    """

    def __init__(self, level_price: float, side: str, tick_size: float,
                 heuristics: M5ReactionHeuristics | None = None):
        self.level = float(level_price)
        self.tick = float(tick_size)
        if not all(isfinite(x) and x > 0 for x in (self.level, self.tick)):
            raise ValueError("M5_REACTION_INVALID_LEVEL_OR_TICK")
        if side not in ("long", "short"):
            raise ValueError("M5_REACTION_SIDE_REQUIRED")
        self.side = side
        self.h = heuristics or M5ReactionHeuristics()
        h = self.h
        if not isinstance(h, M5ReactionHeuristics):
            raise ValueError("M5_REACTION_HEURISTICS_REQUIRED")
        for key in h.__dataclass_fields__:
            value = getattr(h, key)
            if not isfinite(float(value)) or value <= 0:
                raise ValueError("M5_REACTION_INVALID_HEURISTIC")
        for key in ("compression_bars", "consolidation_bars",
                    "consolidation_min_intersections", "chop_bars",
                    "chop_min_flips"):
            if type(getattr(h,key)) is not int:
                raise ValueError("M5_REACTION_WINDOW_NOT_INTEGER")
        if (h.compression_bars < 3 or h.consolidation_bars < 3 or
                h.chop_bars < 4 or h.chop_min_flips >= h.chop_bars or
                h.consolidation_min_intersections > h.consolidation_bars or
                h.compression_range_fraction >= 1 or
                h.wick_fraction_of_range >= 1):
            raise ValueError("M5_REACTION_INVALID_WINDOW")
        self._history = []
        self._last = None
        self._mirror_ready = False
        self.gap_resets = 0

    def _signed(self, price):
        return (float(price) - self.level if self.side == "long"
                else self.level - float(price))

    def observe(self, bar, atr_m5: float | None = None) -> tuple[M5ReactionEvent, ...]:
        """Return zero or more tags only at CURRENT closed candle's end."""
        now = getattr(bar, "ts", None)
        if (getattr(bar, "timeframe", None) != "M5" or
                not isinstance(now, datetime) or now.tzinfo is None or
                now.utcoffset() is None or
                now.astimezone(ET).second != 0 or
                now.astimezone(ET).microsecond != 0 or
                now.astimezone(ET).minute % 5):
            raise ValueError("M5_REACTION_CLOSED_NATIVE_TIME_REQUIRED")
        x = [float(getattr(bar, key)) for key in ("open", "high", "low", "close", "volume")]
        o, hi, lo, c, volume = x
        if (not all(isfinite(v) for v in x) or min(o,hi,lo,c) <= 0
                or volume <= 0 or hi < max(o,c,lo) or lo > min(o,c,hi)):
            raise ValueError("M5_REACTION_INVALID_OHLCV")
        if atr_m5 is not None:
            atr_m5 = float(atr_m5)
            if not isfinite(atr_m5) or atr_m5 <= 0:
                raise ValueError("M5_REACTION_INVALID_M5_ATR")
        if self._last is not None and now <= self._last:
            raise ValueError("M5_REACTION_DUPLICATE_OR_OUT_OF_ORDER")
        if self._last is not None and now-self._last != timedelta(minutes=5):
            self._history.clear()
            self._mirror_ready = False
            self.gap_resets += 1
        self._last = now
        h = self.h
        tol = self.tick * (0.5 + 1e-7)
        signed = self._signed

        def defended(p):
            return signed(p) > tol

        def broken(p):
            return signed(p) < -tol

        def intersects(b):
            return float(b.low) <= self.level + tol and float(b.high) >= self.level - tol

        def pierced(b):
            return (float(b.low) < self.level-tol if self.side == "long"
                    else float(b.high) > self.level+tol)

        def tail_fraction(b):
            body_edge = min(float(b.open),float(b.close)) if self.side == "long" else max(float(b.open),float(b.close))
            t = (body_edge-float(b.low) if self.side == "long"
                 else float(b.high)-body_edge)
            width = float(b.high)-float(b.low)
            return t/width if width > tol else 0.0

        def distance(p):
            return signed(p)

        events = []
        seen = set()

        def add(kind, anchor, reason):
            if kind not in KINDS or kind in seen or anchor > now:
                raise ValueError("M5_REACTION_NONCAUSAL_TAG")
            seen.add(kind)
            events.append(M5ReactionEvent(
                kind, self.level, self.side, now, anchor, reason))

        history = self._history
        prev = history[-1] if history else None
        prev2 = history[-2] if len(history)>=2 else None

        # 1 / 2: touch and NEXT completed candle genuinely moves away.
        if (prev is not None and intersects(prev) and
                defended(prev.close) and defended(c) and
                distance(c) > distance(prev.close) + tol):
            add("BOUNCE", prev.ts, "NEXT_M5_CLOSE_AWAY_FROM_FROZEN_LEVEL")
            if (defended(prev.open) and
                    tail_fraction(prev) >= h.wick_fraction_of_range):
                add("WICK_BOUNCE", prev.ts,
                    "DEFENDED_OPEN_CLOSE_LONG_WICK_NEXT_BAR_BOUNCE_PROXY")

        # 3 / 4: a wick pierced and current close is back on defended side.
        if pierced(bar) and defended(c):
            add("WICK_RECLAIM", now,
                "TAIL_ONLY_RECLAIM" if defended(o) else "BODY_CROSS_RECLAIM")
            if defended(o):
                add("FALSE_BREAK_1BAR", now,
                    "SAME_M5_OPEN_AND_CLOSE_DEFENDED_WITH_ADVERSE_WICK")

        # 5: original side -> one wrong close -> next bar defended again.
        if (prev2 is not None and defended(prev2.close) and
                broken(prev.close) and defended(c)):
            add("FALSE_BREAK_2BAR", prev.ts,
                "PREVIOUS_M5_CLOSE_BEYOND_THEN_CURRENT_CLOSE_REENTRY")

        # 6: two consecutive closes outside, moving farther from old role.
        confirmed_break = bool(
            prev2 is not None and defended(prev2.close) and
            broken(prev.close) and broken(c) and
            -signed(c) > -signed(prev.close) + tol)
        if confirmed_break:
            add("BREAK_FOLLOWTHROUGH", prev.ts,
                "TWO_CLOSED_M5_BEYOND_LEVEL_INCREASING_DISTANCE_PROXY")

        # 7: only AFTER a previously confirmed break; new role retest.
        if (self._mirror_ready and prev is not None and broken(prev.close)
                and broken(c) and intersects(bar)):
            add("MIRROR_RETEST", now,
                "POST_CONFIRMED_BREAK_RETEST_FROM_OPPOSITE_SIDE")
        if not broken(c):
            self._mirror_ready = False
        elif confirmed_break:
            self._mirror_ready = True

        chunk = (history + [bar])[-max(h.compression_bars,
                                      h.consolidation_bars, h.chop_bars):]
        if atr_m5 is not None:
            # 8: shrinking original-side approach, with strict sequence.
            n = h.compression_bars
            if len(chunk) >= n:
                w = chunk[-n:]
                ds = [distance(v.close) for v in w]
                widths = [float(v.high)-float(v.low) for v in w]
                if (all(tol < d <= h.proximity_m5_atr*atr_m5 for d in ds)
                        and all(ds[i+1] < ds[i]-tol for i in range(n-1))
                        and widths[0] > tol
                        and widths[-1] < h.compression_range_fraction*widths[0]):
                    add("COMPRESSION", w[0].ts,
                        "M5_SHRINKING_CLOSE_DISTANCES_AND_BAR_RANGE_HEURISTIC")

            # 9: clustered intersections; no implied exact BSU touches.
            n = h.consolidation_bars
            if len(chunk)>=n:
                w=chunk[-n:]
                if (sum(intersects(v) for v in w) >= h.consolidation_min_intersections
                        and all(abs(float(v.close)-self.level) <=
                                h.proximity_m5_atr*atr_m5 for v in w)
                        and max(float(v.high) for v in w)-
                                min(float(v.low) for v in w) <=
                                h.consolidation_width_m5_atr*atr_m5):
                    add("CONSOLIDATION", w[0].ts,
                        "M5_MANY_RANGE_INTERSECTIONS_WITHIN_ATR_WIDTH_HEURISTIC")

            # 10: repeated close flips, limited direction and width.
            n = h.chop_bars
            if len(chunk)>=n:
                w=chunk[-n:]
                sides = [1 if defended(v.close) else
                         -1 if broken(v.close) else 0 for v in w]
                flips = sum(a*b == -1 for a,b in zip(sides,sides[1:]))
                if (flips >= h.chop_min_flips and any(intersects(v) for v in w)
                        and max(float(v.high) for v in w)-
                                min(float(v.low) for v in w) <=
                                h.chop_width_m5_atr*atr_m5
                        and abs(float(w[-1].close)-float(w[0].close)) <=
                                h.chop_net_m5_atr*atr_m5):
                    add("CHOP", w[0].ts,
                        "M5_MULTIPLE_CLOSE_THROUGH_NO_DIRECTION_HEURISTIC")

        self._history.append(bar)
        self._history = self._history[-max(h.compression_bars,
                                          h.consolidation_bars, h.chop_bars, 8):]
        return tuple(events)
