"""Read-only original BSU pivot vs D1 cluster and native M5 OHLC audit.

NOT the Gerchik signal gate. A crossed price range never proves an
executable level trade, exact BPU1, sub-minute path or TVX.
The canonical BsuDetector remains untouched.
"""
from collections import Counter
from math import isfinite


class TouchAudit:
    """One frozen, already qualified D1 RAW source and its D1 cluster."""

    def __init__(self, ticker, day, source_date, side, raw_origin,
                 cluster, tick, basis):
        if side not in ("long", "short"):
            raise ValueError("unsupported level side")
        raw_origin, cluster, tick = map(float, (raw_origin, cluster, tick))
        if not all(isfinite(v) and v > 0 for v in
                   (raw_origin, cluster, tick)):
            raise ValueError("invalid historical source/cluster/tick")
        self.ticker, self.day, self.source = ticker, str(day), str(source_date)
        self.side, self.raw, self.cluster, self.tick = (
            side, raw_origin, cluster, tick)
        self.basis = basis
        self.counts = Counter()
        self.nearest = None
        self.at = None
        self.nearest_signed = None
        self.first_cross_at = None
        self.first_cluster_at = None
        self.raw_cluster_diff_ticks = (cluster - raw_origin) / tick
        self.cluster_grid = (
            abs(cluster - round(cluster / tick) * tick) <= tick*1e-5)

    def observe(self, bar, at):
        """Audit an independently admitted CLOSED native five-minute bar.

        Four disjoint categories:
        EXACT_WICK = relevant high (short) or low (long) equals RAW pivot
        to native half-tick precision; same as detector's equality.
        SHORT_OF = relevant wick has not reached original pivot.
        RANGE_CROSSED = wick overshot and OHLC spans RAW pivot; crossing
        inside a candle is NOT the Gerchik exact BPU1 requirement.
        BEYOND_NO_SPAN = entire observed candle is beyond the RAW pivot;
        no observed within-candle range crosses that price.
        """
        low, high = float(bar.low), float(bar.high)
        if not all(isfinite(v) and v > 0 for v in (low, high)):
            raise ValueError("invalid observed M5 extrema")
        if high < low:
            raise ValueError("invalid native M5 OHLC range")
        extreme = high if self.side == "short" else low
        delta = (extreme - self.raw)/self.tick
        tol = self.tick * 0.5 + self.tick * 1e-7
        if abs(extreme-self.raw) <= tol:
            category = "EXACT_WICK"
        elif (self.side == "short" and extreme < self.raw - tol
              or self.side == "long" and extreme > self.raw + tol):
            category = "SHORT_OF"
        elif low <= self.raw <= high:
            category = "RANGE_CROSSED"
        else:
            category = "BEYOND_NO_SPAN"
        self.counts[category] += 1
        self.counts["BARS"] += 1
        stamp = at.strftime("%H:%M")
        if self.nearest is None or abs(delta) < self.nearest:
            self.nearest = abs(delta)
            self.nearest_signed = delta
            self.at = stamp
        if category == "RANGE_CROSSED" and self.first_cross_at is None:
            self.first_cross_at = stamp
        if low <= self.cluster <= high:
            self.counts["CLUSTER_RANGE"] += 1
            if self.first_cluster_at is None:
                self.first_cluster_at = stamp
        if abs(extreme - self.cluster) <= tol:
            # A diagnostic only: the D1 median may be off the tick grid.
            self.counts["CLUSTER_WICK_NEAR"] += 1
        return category


def audit_report(cases, limit=12):
    """Return compact log lines, prioritized by source-range crossing.

    Cases without observed M5 are counted but never called negative cases.
    Aggregates count original-source-level CASE/BAR observations, not trades.
    """
    audits = [row["audit"] for row in cases]
    observed = [a for a in audits if a.counts["BARS"]]
    totals = Counter()
    for a in observed:
        totals.update(a.counts)
    cross_cases = sum(a.counts["RANGE_CROSSED"] > 0 for a in observed)
    exact_cases = sum(a.counts["EXACT_WICK"] > 0 for a in observed)
    cluster_only_cases = sum(
        a.counts["CLUSTER_RANGE"] > 0 and
        not (a.counts["EXACT_WICK"] or a.counts["RANGE_CROSSED"])
        for a in observed)
    summary = (
        f"QWCT BSU AUDIT SUMMARY proxies={len(audits)} "
        f"observed={len(observed)} case_bars={totals['BARS']} "
        f"raw_exact={totals['EXACT_WICK']} "
        f"short_of={totals['SHORT_OF']} "
        f"range_crossed={totals['RANGE_CROSSED']} "
        f"beyond_no_span={totals['BEYOND_NO_SPAN']} "
        f"cluster_ranges={totals['CLUSTER_RANGE']} "
        f"cluster_wick_near={totals['CLUSTER_WICK_NEAR']} "
        f"exact_cases={exact_cases} crossed_cases={cross_cases} "
        f"cluster_only_cases={cluster_only_cases}; "
        "NOT BPU1 / NOT TVX / NO ORDERS")
    lines = [summary]
    ranked = sorted(
        observed,
        key=lambda a: (
            -(a.counts["RANGE_CROSSED"] > 0),
            -(a.counts["CLUSTER_RANGE"] > 0),
            a.nearest, a.day, a.ticker))
    for a in ranked[:limit]:
        lines.append(
            f"QWCT BSU AUDIT CASE {a.day} {a.ticker} {a.side} "
            f"src={a.source} raw={a.raw:.4f} "
            f"cluster={a.cluster:.4f} delta_ticks={a.raw_cluster_diff_ticks:.2f} "
            f"cluster_grid={int(a.cluster_grid)} basis={a.basis} "
            f"m5={a.counts['BARS']} exact={a.counts['EXACT_WICK']} "
            f"short={a.counts['SHORT_OF']} "
            f"cross={a.counts['RANGE_CROSSED']} "
            f"beyond={a.counts['BEYOND_NO_SPAN']} "
            f"clust_cross={a.counts['CLUSTER_RANGE']} "
            f"nearest_signed={a.nearest_signed:.2f} at={a.at} "
            f"first_cross={a.first_cross_at or '-'}; NO ORDERS")
    return lines
