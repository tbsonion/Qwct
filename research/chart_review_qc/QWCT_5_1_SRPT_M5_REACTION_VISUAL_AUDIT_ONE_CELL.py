# QWCT 5.1 — ONE CELL | audit ACTUAL SRPT M5 reaction labels vs frozen $125 geometry.
# This file embeds strategy/m5_reaction_taxonomy.py; no extra Cloud files.
# READ-ONLY. Predeclared prior-day D1 context SRPT $125.00, not author BSU.
# Does NOT change existing research.ipynb cells, strategy, main.py or orders.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from math import isfinite
from dataclasses import dataclass
from collections import Counter
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session

# The canonical QWCT 5.1 detector is embedded verbatim below so this works
# inside the SMALL QuantConnect Cloud cohort project without more Python files.
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


# Native QuantBook session and frozen D1 neighborhood chosen BEFORE M5 replay.
DAY = datetime(2024, 6, 3)
SESSION = DAY.date()
TICKER = "SRPT"
CONTEXT_PRICE = 125.00  # Frozen premarket D1 software level, not Gerchik BSU.

def _et(ts):
    value = pd.Timestamp(ts)
    return value.tz_localize(ET) if value.tzinfo is None else value.tz_convert(ET)

qb = QuantBook()
qb.set_time_zone("America/New_York")
qb.set_start_date(2024, 7, 1)
qb.set_end_date(2024, 7, 2)
equity = qb.add_equity(
    TICKER, Resolution.MINUTE, fill_forward=False,
    data_normalization_mode=DataNormalizationMode.RAW)
symbol = equity.symbol
tick = float(qb.securities[symbol].symbol_properties.minimum_price_variation)
cfg = StrategyConfig()
d1 = list(qb.history[TradeBar](
    symbol, DAY-timedelta(days=335), DAY, Resolution.DAILY,
    fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW))
d1 = [b for b in d1 if _et(b.time).date() < SESSION
      and not getattr(b,"is_fill_forward",False)]
if len(d1) < 180:
    raise ValueError(f"QWCT_50_D1_TOO_SHORT: {len(d1)}")
d1 = d1[-180:]
daily_atr = AverageTrueRange(cfg.atr_period, MovingAverageType.WILDERS)
rows = []
for b in d1:
    daily_atr.update(b)
    rows.append({
        "date": _et(b.time), "open":float(b.open), "high":float(b.high),
        "low":float(b.low), "close":float(b.close), "volume":float(b.volume),
        f"atr{cfg.atr_period}":float(daily_atr.current.value)
        if daily_atr.is_ready else float("nan"),
    })
frame = pd.DataFrame(rows).set_index("date")
levels = levels_for_session(frame, SESSION, cfg)
matches = [
    l for l in levels
    if (abs(float(l.price)-CONTEXT_PRICE)<=tick*0.5 and
        l.source=="swing_cluster" and l.valid_from is not None and
        l.valid_from<=SESSION and l.kind in ("support","mirror"))
]
if len(matches) != 1:
    raise ValueError(f"QWCT_50_FROZEN_D1_CONTEXT_MISSING_OR_AMBIGUOUS: {len(matches)}")
lvl = matches[0]
if lvl.kind == "mirror" and float(frame.close.iloc[-1]) <= CONTEXT_PRICE+tick/2:
    raise ValueError("QWCT_50_FROZEN_MIRROR_NOT_SUPPORT_SIDE")
print("QWCT 5.1 FROZEN_CONTEXT",TICKER,
      f"D1_LEVEL={float(lvl.price):.4f}", f"KIND={lvl.kind}",
      f"VALID_FROM={lvl.valid_from}", "ROLE=long",
      "NOT_FIXED_BSU_NOT_AUTHOR_APPROVED NO_ORDERS")

original = list(qb.history[TradeBar](
    symbol, DAY.replace(hour=9,minute=30), DAY.replace(hour=16),
    Resolution.MINUTE, fill_forward=False,
    data_normalization_mode=DataNormalizationMode.RAW))
minute_ends = set()
m5 = []
def on_closed(sender, b):
    end = _et(b.end_time).to_pydatetime()
    if end.date()!=SESSION or not time(9,35)<=end.time()<=time(16,0):
        return
    if (float(b.volume)<=0 or getattr(b,"is_fill_forward",False) or
        any(end-timedelta(minutes=j) not in minute_ends for j in range(5))):
        return
    if (float(b.high)<max(float(b.open),float(b.close),float(b.low))
            or float(b.low)>min(float(b.open),float(b.close),float(b.high))):
        raise ValueError("QWCT_50_NATIVE_M5_INVALID_OHLC")
    m5.append((end,b))
cons = TradeBarConsolidator(timedelta(minutes=5))
cons.data_consolidated += on_closed
for b in original:
    end = _et(b.end_time).to_pydatetime()
    if (getattr(b,"is_fill_forward",False) or b.symbol!=symbol
            or end in minute_ends or float(b.volume)<=0):
        continue
    if not (time(9,31)<=end.time()<=time(16,0)):
        continue
    minute_ends.add(end)
    cons.update(b)
cons.scan(DAY.replace(hour=16,minute=1))
if not m5:
    raise ValueError("QWCT_50_NO_REAL_NATIVE_M5")
m5.sort(key=lambda row:row[0])
if len(set(t for t,_ in m5))!=len(m5):
    raise ValueError("QWCT_50_DUPLICATE_NATIVE_M5_END")
expected = [pd.Timestamp(DAY.replace(hour=9,minute=35),tz=ET)+timedelta(minutes=5*i)
            for i in range(78)]
actual_ends = set(pd.Timestamp(t) for t,_ in m5)
missing_m5 = [x.strftime("%H:%M") for x in expected if x not in actual_ends]
print("QWCT 5.1 NATIVE_DATA",TICKER,
      f"M1={len(minute_ends)}/390", f"M5={len(m5)}/78",
      f"MISSING_M5={missing_m5}", "RAW NO_FILL_FORWARD")

observer = M5TenReactionObserver(float(lvl.price),"long",tick)
m5_atr = AverageTrueRange(14, MovingAverageType.WILDERS)
previous_end = None
events = []
by_end = {}
atr_by_end = {}
for end,b in m5:
    if previous_end is not None and end-previous_end!=timedelta(minutes=5):
        m5_atr = AverageTrueRange(14, MovingAverageType.WILDERS)
    m5_atr.update(b)
    bar = type("M5Evidence", (), {})()
    bar.ts = end
    bar.timeframe = "M5"
    bar.open = float(b.open)
    bar.high = float(b.high)
    bar.low = float(b.low)
    bar.close = float(b.close)
    bar.volume = float(b.volume)
    by_end[end] = bar
    known_atr = float(m5_atr.current.value) if m5_atr.is_ready else None
    atr_by_end[end] = known_atr
    events.extend(observer.observe(bar, known_atr))
    previous_end = end

count=Counter(e.kind for e in events)
print("QWCT 5.1 SUMMARY",
      f"NATIVE_M5={len(m5)}", f"GAP_RESETS={observer.gap_resets}",
      f"EVENTS={len(events)}", "AUTHOR_UNVERIFIED NO_ORDERS")
for name in KINDS:
    print("QWCT 5.1 REACTION", name,
          f"COUNT={count[name]}", "SOFTWARE_ONLY NO_ORDERS")

# A separate auditor re-derives the geometries; it never calls the
# original M5TenReactionObserver to certify a previously reported tag.
"""QWCT 5.1 independent MECHANICAL audit of closed-M5 reaction tags.

This independently re-reads real bar geometry, anchors and causal ATR,
using the *published software conditions* of QWCT 5.0. It is NOT
Gerchik-labeled ground truth and cannot certify discretionary accuracy.
Read-only, no new signal, no author score and no broker action.
"""
from datetime import timedelta
from math import isfinite


def audit_reaction_event(e, by_end, atr_by_end, *, level, side, tick, h):
    """Return (mechanically_consistent, objective_reason) for one QWCT event.

    Require a complete contiguous M5 path from event anchor to observed bar.
    Multi-bar windows are independently recomputed, with only as-of ATR.
    """
    if side not in ("long", "short") or not isfinite(float(level)) or not isfinite(float(tick)) or tick <= 0:
        return False, "INVALID_FROZEN_CONTEXT"
    if (e.level_price != level or e.side != side or
            e.bar_end not in by_end or e.anchor_end not in by_end or
            e.anchor_end > e.bar_end or getattr(e, "can_trade", True)):
        return False, "INVALID_EVENT_PROVENANCE"
    times = sorted(t for t in by_end if t <= e.bar_end)
    if not times or times[-1] != e.bar_end:
        return False, "MISSING_OBSERVATION"
    # Only the latest truly contiguous native 5-minute segment is eligible.
    first = len(times) - 1
    while first > 0 and times[first] - times[first-1] == timedelta(minutes=5):
        first -= 1
    contiguous = times[first:]
    if e.anchor_end not in contiguous:
        return False, "ANCHOR_ACROSS_MISSING_M5"
    bars = [by_end[t] for t in contiguous]
    at = bars[-1]
    tol = tick * (0.5 + 1e-7)

    def signed(p):
        return float(p)-level if side == "long" else level-float(p)

    def defended(p):
        return signed(p) > tol

    def broken(p):
        return signed(p) < -tol

    def cross(b):
        return float(b.low) <= level+tol and float(b.high) >= level-tol

    def pierced(b):
        return (float(b.low) < level-tol if side == "long"
                else float(b.high) > level+tol)

    def prev(i):
        return bars[-i] if len(bars) >= i else None

    def windows(n):
        w = bars[-n:]
        return w if len(w) == n and w[0].ts == e.anchor_end else None

    def atr():
        return atr_by_end.get(e.bar_end)

    previous, before = prev(2), prev(3)
    kind = e.kind
    ok = False
    if kind == "BOUNCE":
        ok = (previous is not None and previous.ts == e.anchor_end
              and cross(previous) and defended(previous.close)
              and defended(at.close) and
              signed(at.close) > signed(previous.close)+tol)
    elif kind == "WICK_BOUNCE":
        if previous is not None:
            width = float(previous.high)-float(previous.low)
            body_edge = (min(float(previous.open),float(previous.close))
                         if side == "long" else
                         max(float(previous.open),float(previous.close)))
            tail = ((body_edge-float(previous.low)) if side == "long"
                    else (float(previous.high)-body_edge))
            ok = (previous.ts == e.anchor_end and cross(previous)
                  and defended(previous.open) and defended(previous.close)
                  and defended(at.close) and signed(at.close) >
                  signed(previous.close)+tol and width>tol and
                  tail/width >= h.wick_fraction_of_range)
    elif kind == "WICK_RECLAIM":
        why = ("TAIL_ONLY_RECLAIM" if defended(at.open)
               else "BODY_CROSS_RECLAIM")
        ok = (e.anchor_end == e.bar_end and
              pierced(at) and defended(at.close) and e.reason == why)
    elif kind == "FALSE_BREAK_1BAR":
        ok = (e.anchor_end == e.bar_end and defended(at.open)
              and defended(at.close) and pierced(at))
    elif kind == "FALSE_BREAK_2BAR":
        ok = (previous is not None and before is not None and
              previous.ts == e.anchor_end and
              defended(before.close) and broken(previous.close) and
              defended(at.close))
    elif kind == "BREAK_FOLLOWTHROUGH":
        ok = (previous is not None and before is not None and
              previous.ts == e.anchor_end and
              defended(before.close) and broken(previous.close) and
              broken(at.close) and
              -signed(at.close) > -signed(previous.close)+tol)
    elif kind == "MIRROR_RETEST":
        # Confirm a break earlier in the SAME contiguous segment;
        # a subsequent return to original defended side cancels this role.
        ready = False
        for i in range(2, len(bars)-1):
            b2,b1,b = bars[i-2],bars[i-1],bars[i]
            if not broken(b.close):
                ready = False
            elif (defended(b2.close) and broken(b1.close)
                  and -signed(b.close) > -signed(b1.close)+tol):
                ready = True
        ok = (e.anchor_end == e.bar_end and ready and
              previous is not None and broken(previous.close) and
              broken(at.close) and cross(at))
    elif kind == "COMPRESSION":
        w = windows(h.compression_bars)
        a = atr()
        if w and a is not None and isfinite(float(a)) and a > 0:
            ds = [signed(v.close) for v in w]
            widths = [float(v.high)-float(v.low) for v in w]
            ok = (all(tol < d <= h.proximity_m5_atr*a for d in ds)
                  and all(ds[i+1] < ds[i]-tol for i in range(len(ds)-1))
                  and widths[0]>tol and widths[-1] <
                  h.compression_range_fraction*widths[0])
    elif kind == "CONSOLIDATION":
        w=windows(h.consolidation_bars)
        a=atr()
        if w and a is not None and isfinite(float(a)) and a > 0:
            ok = (sum(cross(v) for v in w) >= h.consolidation_min_intersections
                  and all(abs(float(v.close)-level) <= h.proximity_m5_atr*a
                          for v in w)
                  and max(float(v.high) for v in w) -
                  min(float(v.low) for v in w) <= h.consolidation_width_m5_atr*a)
    elif kind == "CHOP":
        w=windows(h.chop_bars)
        a=atr()
        if w and a is not None and isfinite(float(a)) and a > 0:
            states = [1 if defended(v.close) else
                      -1 if broken(v.close) else 0 for v in w]
            flips = sum(x*y == -1 for x,y in zip(states,states[1:]))
            ok = (flips >= h.chop_min_flips and any(cross(v) for v in w)
                  and max(float(v.high) for v in w) -
                  min(float(v.low) for v in w) <= h.chop_width_m5_atr*a
                  and abs(float(w[-1].close) -
                          float(w[0].close)) <= h.chop_net_m5_atr*a)
    else:
        return False, "UNKNOWN_REACTION_KIND"
    return (True, "MECHANICS_MATCHED_NOT_AUTHOR_VALIDATED") if ok else (
        False, "GEOMETRY_OR_ANCHOR_MISMATCH")


# Check the full list of native M5 tags, not just visually appealing ones.
failed=[]
checked=[]
by_time={}
for e in events:
    ok,why=audit_reaction_event(
        e, by_end, atr_by_end, level=float(lvl.price),
        side="long", tick=tick, h=observer.h)
    checked.append((e,ok,why))
    by_time.setdefault(e.bar_end,[]).append(e.kind)
    if not ok:
        failed.append((e,why))
    observed=by_end[e.bar_end]
    print("QWCT 5.1 GEOMETRY",
          e.bar_end.strftime("%H:%M"), e.kind,
          "ANCHOR="+e.anchor_end.strftime("%H:%M"),
          f"O={observed.open:.2f}",f"H={observed.high:.2f}",
          f"L={observed.low:.2f}",f"C={observed.close:.2f}",
          "M5_ATR14="+(
              f"{atr_by_end[e.bar_end]:.5f}"
              if atr_by_end[e.bar_end] is not None else "UNKNOWN"),
          "PASS_MECHANICAL" if ok else "FAIL_CLOSED",
          "NOT_AUTHOR_VALIDATED")
overlapping={
    t.strftime("%H:%M"):v for t,v in by_time.items() if len(v)>1
}
print("QWCT 5.1 AUDIT SUMMARY",
      f"CHECKED={len(checked)}",
      f"PASS={sum(ok for _,ok,_ in checked)}",
      f"FAIL={len(failed)}",
      f"MISSING_M5={missing_m5}",
      f"OVERLAPS={overlapping}",
      "GERCHIK_GROUND_TRUTH_LABELS=0",
      "NO_ORDERS")
if failed:
    raise ValueError("QWCT_51_GEOMETRY_MISMATCH: "+str([
        (e.kind,e.bar_end.strftime("%H:%M"),why) for e,why in failed])[:400])

# Three PRESELECTED zoom windows; not chosen by later price action.
focus = [
    ("10:30 — WICK_RECLAIM + FALSE_BREAK_2BAR (may overlap)",
     datetime(2024,6,3,10,15,tzinfo=ET),
     datetime(2024,6,3,10,55,tzinfo=ET)),
    ("11:30 — M5 MIRROR_RETEST vs already confirmed break",
     datetime(2024,6,3,11,5,tzinfo=ET),
     datetime(2024,6,3,11,45,tzinfo=ET)),
    ("10:40–11:10 — rolling CONSOLIDATION / CHOP",
     datetime(2024,6,3,10,35,tzinfo=ET),
     datetime(2024,6,3,11,15,tzinfo=ET)),
]
fig=make_subplots(rows=3,cols=1,shared_xaxes=False,
                  vertical_spacing=.10,
                  subplot_titles=tuple(x[0] for x in focus))
for row,(title,start,stop) in enumerate(focus,start=1):
    candles=[(end,b) for end,b in m5 if start<=end<=stop]
    if not candles:
        raise ValueError("QWCT_51_FOCAL_NATIVE_WINDOW_EMPTY")
    fig.add_trace(go.Candlestick(
        x=[t for t,_ in candles],
        open=[float(b.open) for _,b in candles],
        high=[float(b.high) for _,b in candles],
        low=[float(b.low) for _,b in candles],
        close=[float(b.close) for _,b in candles],
        name="Actual RAW M5",showlegend=(row==1)),row=row,col=1)
    fig.add_hline(y=float(lvl.price),row=row,col=1,
                  annotation_text="Frozen prior-day D1 software $125.00")
    visible=[e for e in events if start<=e.bar_end<=stop]
    for name in KINDS:
        subset=[e for e in visible if e.kind==name]
        if not subset:
            continue
        fig.add_trace(go.Scatter(
            x=[e.bar_end for e in subset],
            y=[by_end[e.bar_end].close for e in subset],
            mode="markers",name=name,showlegend=(row==1),
            marker=dict(size=11,symbol="diamond"),
            customdata=[[e.anchor_end.strftime("%H:%M"),e.reason]
                        for e in subset],
            hovertemplate=(
                "closed M5=%{x}<br>price=%{y:.4f}<br>"
                "anchor=%{customdata[0]}<br>software=%{customdata[1]}"
                "<extra>%{fullData.name}</extra>")
        ),row=row,col=1)
    fig.update_xaxes(rangeslider_visible=False,row=row,col=1)
fig.update_layout(
    width=1140,height=1130,margin=dict(t=90,l=70,r=100,b=55),
    title="QWCT 5.1 | SRPT 2024-06-03 | M5 reaction geometry audit ONLY",
    hovermode="closest")
fig.show()
print("QWCT 5.1 COMPLETE",
      "MECHANICAL_AUDIT_PASSED",
      "AUTHOR_REACTION_ACCURACY=UNKNOWN",
      "FIXED_BSU=UNKNOWN",
      "NO_BROKER_NO_ORDERS")
