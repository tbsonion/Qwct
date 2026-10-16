"""Read indicator snapshots computed by built-in QuantConnect LEAN indicators.

No home-grown ATR or moving-average calculations. The QCAlgorithm feeds
the 'atr14' and 'sma50' columns from AverageTrueRange and SimpleMovingAverage.
Missing data is explicit (NaN) and all dependent gates must fail closed.
"""
from __future__ import annotations

from math import isfinite
from dataclasses import dataclass
from datetime import date
import numpy as np

import pandas as pd

from .config import StrategyConfig


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    col = f"atr{period}"
    if col not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype=float)
    return df[col].astype(float)


def trend_direction(df: pd.DataFrame, idx: int, cfg: StrategyConfig,
                    bars: int | None = None) -> int:
    """Same Gerchik directional rule, using only LEAN-provided SMA snapshots."""
    bars = bars or cfg.local_trend_bars
    col = f"sma{cfg.trend_sma}"
    if col not in df or idx >= len(df) or idx - bars < 0:
        return 0
    try:
        now = float(df[col].iloc[idx])
        prior = float(df[col].iloc[idx - bars])
        close = float(df["close"].iloc[idx])
    except (TypeError, ValueError, IndexError, KeyError):
        return 0
    if not all(isfinite(v) for v in (now, prior, close)):
        return 0
    if now > prior and close > now:
        return 1
    if now < prior and close < now:
        return -1
    return 0


def global_trend(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> int:
    return trend_direction(df, idx, cfg, bars=cfg.trend_sma // 2)


# QWCT 3.9 — ten independent, causal D1 reaction observations.
# This is a SOFTWARE HEURISTIC TAXONOMY, not universal Gerchik criteria.
# The original detector / BSU / BPU / orders never call this function.
@dataclass(frozen=True)
class D1ReactionTaxon:
    kind: str
    observed_on: date
    anchor_on: date
    reference_price: float
    source_label: str
    phase: str
    basis: str = "SOFTWARE_DIAGNOSTIC_NOT_AUTHOR_RULE"
    can_trade: bool = False


@dataclass(frozen=True)
class ReactionHeuristics:
    # Exploratory D1 proxies, never thresholds to approve BSU/BPU1.
    # All ATR values come from the existing historical native LEAN column.
    wick_fraction_of_range: float = 0.40
    compression_bars: int = 4
    compression_range_fraction: float = 0.80
    consolidation_bars: int = 5
    consolidation_min_intersections: int = 3
    consolidation_width_atr: float = 1.60
    proximity_atr: float = 0.80
    chop_bars: int = 6
    chop_min_flips: int = 3
    chop_width_atr: float = 2.0
    chop_net_change_atr: float = 0.60


D1_REACTION_KINDS = (
    "BOUNCE", "WICK_BOUNCE", "WICK_RECLAIM", "FALSE_BREAK_1BAR",
    "FALSE_BREAK_2BAR", "BREAK_FOLLOWTHROUGH", "MIRROR_RETEST",
    "COMPRESSION", "CONSOLIDATION", "CHOP",
)


def observe_d1_level_reactions(
        d1_asof: pd.DataFrame, evidence: BsuSourceEvidence, trace: dict, *,
        session: date, tick_size: float, atr_column: str,
        heuristics: ReactionHeuristics | None = None) -> tuple:
    """Classify 10 overlapping observations only AFTER completed D1 candles.

    Includes strictly descriptive software heuristics for compression,
    consolidation, chop and what could be a sustained breakout. Never treats
    "breakout with followthrough" as a guaranteed future true breakout.
    Must be called ONLY with a previously verified frozen mirror source.
    """
    # Lazy import avoids a circular dependency at import time.
    from .levels import BsuSourceEvidence, _d1_wick_reaction
    h = heuristics if heuristics is not None else ReactionHeuristics()
    if not isinstance(h, ReactionHeuristics):
        raise ValueError("REACTION_HEURISTICS_REQUIRED")
    for name in h.__dataclass_fields__:
        value = getattr(h, name)
        if not isfinite(float(value)) or value <= 0:
            raise ValueError("INVALID_REACTION_HEURISTIC")
    for name in ("compression_bars", "consolidation_bars",
                 "consolidation_min_intersections", "chop_bars",
                 "chop_min_flips"):
        value = getattr(h, name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("INVALID_REACTION_WINDOW")
    if (h.compression_bars < 3 or h.consolidation_bars < 3 or
            h.chop_bars < 4 or h.chop_min_flips >= h.chop_bars or
            h.consolidation_min_intersections > h.consolidation_bars or
            h.compression_range_fraction >= 1):
        raise ValueError("INVALID_REACTION_WINDOW")
    if (not isinstance(session, date) or isinstance(session, pd.Timestamp) or
            not isinstance(d1_asof, pd.DataFrame) or d1_asof.empty or
            not isinstance(d1_asof.index, pd.DatetimeIndex) or
            d1_asof.index.tz is None or not d1_asof.index.is_unique or
            not d1_asof.index.is_monotonic_increasing):
        raise ValueError("INVALID_REACTION_ASOF_D1")
    dates = [x.date() for x in d1_asof.index]
    if any(a >= b for a,b in zip(dates, dates[1:])) or dates[-1] >= session:
        raise ValueError("NONCAUSAL_REACTION_DATE")
    if (not isinstance(atr_column, str) or atr_column not in d1_asof or
            any(x not in d1_asof for x in ("open","high","low","close"))):
        raise ValueError("MISSING_NATIVE_REACTION_DATA")
    if (not isinstance(evidence, BsuSourceEvidence) or
            evidence.status != "AUTHOR_UNVERIFIED" or evidence.can_trade or
            evidence.label not in ("FIRST_SWING","LAST_SWING") or
            evidence.confirmed_date >= session or
            evidence.source_date >= evidence.confirmed_date or
            not isinstance(trace, dict) or
            trace.get("status") != "PROXY_VERIFIED" or
            trace.get("original_kind") not in ("resistance","support")):
        raise ValueError("REACTION_SOURCE_UNVERIFIED")
    try:
        price,tick = float(evidence.price),float(tick_size)
        from_date = date.fromisoformat(trace["valid_from"])
        retest_date = date.fromisoformat(trace["retest"])
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ValueError("INVALID_REACTION_TRACE_OR_PRICE") from exc
    if (not all(isfinite(x) and x>0 for x in (price,tick)) or
            from_date > session or retest_date >= from_date or
            evidence.source_date not in dates or
            evidence.confirmed_date not in dates):
        raise ValueError("INVALID_REACTION_TRACE_OR_PRICE")
    bars=d1_asof[["open","high","low","close"]].astype(float)
    if (not np.isfinite(bars.to_numpy(dtype=float)).all() or
            (bars.min(axis=1)<=0).any() or
            (bars.high < bars[["open","close","low"]].max(axis=1)).any() or
            (bars.low > bars[["open","close","high"]].min(axis=1)).any()):
        raise ValueError("INVALID_REACTION_OHLC")
    tol = tick*(0.5+1e-7)
    pos = {d:i for i,d in enumerate(dates)}
    first=pos[evidence.confirmed_date]+1
    n=len(bars)
    if first>=n:
        return ()

    def role_at(i):
        original=trace["original_kind"]
        if dates[i] < from_date:
            return original,"ORIGINAL"
        return ("support" if original=="resistance" else "resistance"),"MIRROR"

    def defended(value, role):
        return value > price+tol if role=="support" else value < price-tol

    def wrong(value, role):
        return value < price-tol if role=="support" else value > price+tol

    def distance_on_defended(value,role):
        return value-price if role=="support" else price-value

    def native_atr(i):
        x=d1_asof.iloc[i][atr_column]
        if pd.isna(x):
            return None
        try:
            v=float(x)
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError("INVALID_NATIVE_REACTION_ATR") from exc
        if not isfinite(v) or v<=0:
            raise ValueError("INVALID_NATIVE_REACTION_ATR")
        return v

    result={}
    def record(kind,i,anchor,phase,basis="SOFTWARE_DIAGNOSTIC_NOT_AUTHOR_RULE"):
        if kind not in D1_REACTION_KINDS or i<first or i>=n or anchor>i:
            raise ValueError("NONCAUSAL_REACTION_TAG")
        key=(kind,dates[i])
        if key not in result:
            result[key]=D1ReactionTaxon(
                kind=kind,observed_on=dates[i],anchor_on=dates[anchor],
                reference_price=price,source_label=evidence.label,
                phase=phase,basis=basis)

    for observation in evidence.wick_reactions:
        if observation.at not in pos or observation.at<=evidence.confirmed_date:
            raise ValueError("NONCAUSAL_REACTION_WICK")
        i=pos[observation.at]
        role,phase=role_at(i)
        if observation.role!=role:
            raise ValueError("REACTION_ROLE_MISMATCH")
        native = _d1_wick_reaction(
            bars.iloc[i], price, tick, role, dates[i],
            d1_asof.iloc[i][atr_column], True)
        if native is None or native.event != observation.event:
            raise ValueError("STALE_REACTION_WICK_OR_BAR")
        # The traced role reversal retest is dated BEFORE "valid_from";
        # do not mislabel that transitional candle as an original-side
        # failed break/bounce. Mirror retest is independently tagged below.
        if observation.at==retest_date:
            continue
        if observation.event in ("TAIL_ONLY_RECLAIM","BODY_CROSS_RECLAIM"):
            record("WICK_RECLAIM",i,i,phase,"CLOSED_D1_WICK_RECLAIM")
            # A one-bar false break starts, pierces and CLOSES on the same
            # defended side. An open on the wrong side (body-cross reclaim)
            # is NOT that one-bar pattern; it may be an overnight gap.
            if defended(float(bars.iloc[i].open),role):
                record("FALSE_BREAK_1BAR",i,i,phase,
                       "SAME_CLOSED_D1_OPEN_AND_CLOSE_DEFENDED")
        # A bounce is not a mere candle touching: wait for NEXT D1 close.
        if (i+1<n and dates[i+1]>dates[i] and
                role_at(i+1)[1]==phase and
                defended(float(bars.iloc[i].close),role) and
                defended(float(bars.iloc[i+1].close),role) and
                distance_on_defended(float(bars.iloc[i+1].close),role) >
                distance_on_defended(float(bars.iloc[i].close),role)+tol):
            record("BOUNCE",i+1,i,phase,"NEXT_CLOSED_D1_DEFENDED_REACTION")
            # 0.40 is an explicitly named SOFT heuristic, not "Gerchik strong".
            if (observation.event=="TAIL_ONLY_RECLAIM" and
                    observation.wick_to_range is not None and
                    native.wick_to_range is not None and
                    native.wick_to_range>=h.wick_fraction_of_range):
                record("WICK_BOUNCE",i+1,i,phase,
                       "NEXT_CLOSED_D1_PLUS_LARGE_TAIL_PROXY")

    for phase,days in (("ORIGINAL",evidence.original_two_bar_reclaim_dates),
                       ("MIRROR",evidence.mirror_two_bar_reclaim_dates)):
        for day in days:
            if day not in pos or day<=evidence.confirmed_date:
                raise ValueError("NONCAUSAL_REACTION_TWO_BAR")
            i=pos[day]
            if i==0 or role_at(i)[1]!=phase or role_at(i-1)[1]!=phase:
                raise ValueError("REACTION_TWO_BAR_ROLE_TRANSITION")
            role,_=role_at(i)
            if not(wrong(float(bars.iloc[i-1].close),role) and
                   defended(float(bars.iloc[i].close),role)):
                raise ValueError("REACTION_TWO_BAR_CLOSES_MISMATCH")
            record("FALSE_BREAK_2BAR",i,i-1,phase,
                   "TWO_CLOSED_D1_REENTRY_PROXY")

    # A mirror event is the actual dated, independently audited D1 retest
    # from the existing cluster trace. Candidate FIRST/LAST must ALSO be
    # crossed by that SAME candle; otherwise no per-candidate mirror tag.
    if retest_date in pos:
        j=pos[retest_date]
        if j>=first and dates[j]<from_date:
            b=bars.iloc[j]
            newrole="support" if trace["original_kind"]=="resistance" else "resistance"
            if b.low<=price<=b.high and defended(float(b.close),newrole):
                record("MIRROR_RETEST",j,j,"MIRROR_TRANSITION",
                       "AUDITED_CLUSTER_TRACE_AND_CANDIDATE_RANGE")

    for i in range(first,n):
        role,phase=role_at(i)
        cur=bars.iloc[i]
        # The existing audit identifies only the FIRST mirror transition.
        # A later approach from the mirror-defended side to the SAME
        # candidate price is also an observable retest, not necessarily
        # an author-approved price/BSU. Never bridge the role transition.
        if (phase=="MIRROR" and i>first and
                role_at(i-1)[1]=="MIRROR" and
                defended(float(bars.iloc[i-1].close),role) and
                defended(float(cur.close),role) and
                float(cur.low)<=price<=float(cur.high)):
            record("MIRROR_RETEST",i,i,phase,
                   "LATER_D1_MIRROR_SIDE_RETEST_PROXY")
        # Directional break -> TWO closes beyond price; second close moves
        # farther from the level. Both bars must be in one consistent role.
        if i>=max(first+2,2) and role_at(i-1)[1]==phase and role_at(i-2)[1]==phase:
            p2,p1=bars.iloc[i-2],bars.iloc[i-1]
            if (defended(float(p2.close),role) and
                    wrong(float(p1.close),role) and
                    wrong(float(cur.close),role) and
                    (price-float(cur.close) if role=="support" else
                     float(cur.close)-price) >
                    (price-float(p1.close) if role=="support" else
                     float(p1.close)-price)+tol):
                record("BREAK_FOLLOWTHROUGH",i,i-1,phase,
                       "TWO_BEYOND_CLOSES_NOT_PERMANENT_BREAK")
        atr=native_atr(i)
        if atr is None:
            continue  # missing historical native ATR => UNKNOWN, never zero
        # Compression requires D1 closes on the defended side, approaching
        # the line in order, with a visibly shrinking bar-range envelope.
        w=h.compression_bars
        if i-w+1>=first and all(role_at(j)[1]==phase for j in range(i-w+1,i+1)):
            chunk=bars.iloc[i-w+1:i+1]
            distances=[distance_on_defended(float(v),role) for v in chunk.close]
            ranges=[float(q.high-q.low) for _,q in chunk.iterrows()]
            if (all(v>tol and v<=h.proximity_atr*atr for v in distances) and
                    all(distances[j+1]<distances[j]-tol for j in range(w-1)) and
                    ranges[-1] < h.compression_range_fraction*ranges[0] and
                    ranges[0]>tol):
                record("COMPRESSION",i,i-w+1,phase,
                       "SHRINKING_CLOSE_DISTANCE_AND_RANGE_PROXY")
        w=h.consolidation_bars
        if i-w+1>=first and all(role_at(j)[1]==phase for j in range(i-w+1,i+1)):
            chunk=bars.iloc[i-w+1:i+1]
            intersections=sum(float(q.low)<=price<=float(q.high)
                              for _,q in chunk.iterrows())
            if (intersections>=h.consolidation_min_intersections and
                    max(abs(float(c)-price) for c in chunk.close)<=
                    h.proximity_atr*atr and
                    float(chunk.high.max()-chunk.low.min()) <=
                    h.consolidation_width_atr*atr):
                record("CONSOLIDATION",i,i-w+1,phase,
                       "MULTIPLE_SPANNING_BARS_IN_NARROW_D1_BAND_PROXY")
        w=h.chop_bars
        if i-w+1>=first and all(role_at(j)[1]==phase for j in range(i-w+1,i+1)):
            chunk=bars.iloc[i-w+1:i+1]
            closes=[float(c) for c in chunk.close]
            sides=[1 if c>price+tol else -1 if c<price-tol else 0
                   for c in closes]
            flips=sum(sides[j]*sides[j-1]==-1 for j in range(1,w))
            # A sequence of gap-only flips with no candle trading through
            # the reference is not enough to call this observed chop.
            spans=sum(float(q.low)<=price<=float(q.high)
                      for _,q in chunk.iterrows())
            if (flips>=h.chop_min_flips and spans>0 and
                    float(chunk.high.max()-chunk.low.min())<=h.chop_width_atr*atr and
                    abs(closes[-1]-closes[0])<=h.chop_net_change_atr*atr):
                record("CHOP",i,i-w+1,phase,
                       "FREQUENT_D1_CLOSE_SIDE_FLIPS_NO_NET_PROGRESS_PROXY")
    return tuple(sorted(result.values(),
                        key=lambda x:(x.observed_on,D1_REACTION_KINDS.index(x.kind))))
