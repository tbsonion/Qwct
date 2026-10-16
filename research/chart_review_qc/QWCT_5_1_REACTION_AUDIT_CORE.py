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
