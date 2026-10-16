# QWCT 5.0 — ONE CELL | actual SRPT native M5, 10 level reactions.
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
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session

# The canonical QWCT 5.0 detector is embedded verbatim below so this works
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
print("QWCT 5.0 FROZEN_CONTEXT",TICKER,
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
print("QWCT 5.0 NATIVE_DATA",TICKER,
      f"M1={len(minute_ends)}/390", f"M5={len(m5)}/78",
      f"MISSING_M5={missing_m5}", "RAW NO_FILL_FORWARD")

observer = M5TenReactionObserver(float(lvl.price),"long",tick)
m5_atr = AverageTrueRange(14, MovingAverageType.WILDERS)
previous_end = None
events = []
by_end = {}
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
    events.extend(observer.observe(
        bar, float(m5_atr.current.value) if m5_atr.is_ready else None))
    previous_end = end

count=Counter(e.kind for e in events)
print("QWCT 5.0 SUMMARY",
      f"NATIVE_M5={len(m5)}", f"GAP_RESETS={observer.gap_resets}",
      f"EVENTS={len(events)}", "AUTHOR_UNVERIFIED NO_ORDERS")
for name in KINDS:
    print("QWCT 5.0 REACTION", name,
          f"COUNT={count[name]}", "SOFTWARE_ONLY NO_ORDERS")
for e in events[:24]:
    print("QWCT 5.0 EVIDENCE",e.bar_end.strftime("%H:%M"),
          e.kind, "ANCHOR="+e.anchor_end.strftime("%H:%M"),
          "REASON="+e.reason, "NOT_BPU_NOT_TVX")

fig=go.Figure()
fig.add_trace(go.Candlestick(
    x=[t for t,_ in m5],
    open=[float(b.open) for _,b in m5],
    high=[float(b.high) for _,b in m5],
    low=[float(b.low) for _,b in m5],
    close=[float(b.close) for _,b in m5],
    name="RAW closed native M5"))
fig.add_hline(y=CONTEXT_PRICE,
              annotation_text="Prior-day frozen D1 software proxy $125.00")
for name in KINDS:
    tagged=[e for e in events if e.kind==name]
    if tagged:
        fig.add_trace(go.Scatter(
            x=[e.bar_end for e in tagged],
            y=[by_end[e.bar_end].close for e in tagged],
            mode="markers", name=name,
            marker=dict(size=10),
            text=[e.reason+" | "+e.anchor_end.strftime("%H:%M")
                  for e in tagged],
            hovertemplate="%{x}<br>price=%{y}<br>%{text}<extra>%{fullData.name}</extra>"))
fig.update_layout(
    title="QWCT 5.0 | SRPT 2024-06-03 | 10 reaction software tags (NOT Gerchik author verified)",
    xaxis_rangeslider_visible=False, height=680,
    xaxis_title="America/New_York",
    yaxis_title="SRPT RAW price")
fig.show()
print("QWCT 5.0 COMPLETE", "ALL_10_RULES_CHECKED",
      "NOT_ALL_10_MUST_APPEAR_IN_ONE_SESSION",
      "NO_ORDERS NO_AUTHOR_APPROVAL")
