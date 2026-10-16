# QWCT 4.8b — why was SRPT's 2024-06-03 14:39:30 SEC cutoff blocked?
# ONE standalone QuantConnect research.ipynb cell. Read-only, no orders.
# SRPT vs SPY is a data-feed positive control, not a Gerchik signal.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from datetime import datetime, timedelta
from collections import Counter
from zoneinfo import ZoneInfo
import pandas as pd

ET = ZoneInfo("America/New_York")
START = datetime(2024, 6, 3, 14, 35, tzinfo=ET)
CUTOFF = datetime(2024, 6, 3, 14, 39, 30, tzinfo=ET)
CLOCK_SECONDS = 270


def et(ts):
    ts = pd.Timestamp(ts)
    return ts.tz_localize(ET) if ts.tzinfo is None else ts.tz_convert(ET)


def seconds(delta):
    fn = getattr(delta, "total_seconds", None)
    if fn is not None:
        return float(fn())
    native = getattr(delta, "TotalSeconds", None)
    return float(native() if callable(native) else native) if native is not None else None


def coverage_summary(trades, start, cutoff):
    """Describe actual observed (end timestamp, volume) ONLY; never infer trades."""
    ordered = sorted(trades, key=lambda row: row[0])
    stamps = [end for end, _ in ordered]
    unique = len(set(stamps)) == len(stamps)
    if any(not start < end <= cutoff for end in stamps):
        raise ValueError("SEC_COVERAGE_OUT_OF_WINDOW")
    gaps = []
    previous = start
    for end in stamps:
        interval = int((end - previous).total_seconds())
        if interval <= 0:
            raise ValueError("SEC_COVERAGE_DUPLICATE_OR_EARLY")
        gaps.append((previous, end, interval))
        previous = end
    if previous < cutoff:
        gaps.append((previous, cutoff, int((cutoff - previous).total_seconds())))
    max_gap = max((g[2] for g in gaps), default=CLOCK_SECONDS)
    bins = [0] * 5
    for end in stamps:
        slot = min(4, max(0, int((end-start).total_seconds()-1)//60))
        bins[slot] += 1
    last_age = None if not stamps else int((cutoff-stamps[-1]).total_seconds())
    return dict(
        traded_seconds=len(stamps),
        first=stamps[0] if stamps else None,
        last=stamps[-1] if stamps else None,
        exact_cutoff=(bool(stamps) and stamps[-1] == cutoff),
        last_trade_age_s=last_age,
        max_interval_s=max_gap,
        intervals_over_10s=sum(interval > 10 for _, _, interval in gaps),
        worst_gaps=sorted(
            [g for g in gaps if g[2] > 10],
            key=lambda g: -g[2])[:5],
        per_minute=bins,
        observed_volume=sum(float(volume) for _, volume in ordered),
        native_10s_gate_possible=(
            unique and bool(stamps) and stamps[-1] == cutoff
            and max_gap <= 10),
    )


def audit_one(qb, ticker):
    symbol = qb.add_equity(
        ticker, Resolution.SECOND, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW).symbol
    raw = list(qb.history[TradeBar](
        symbol, START.replace(tzinfo=None),
        (CUTOFF+timedelta(seconds=1)).replace(tzinfo=None),
        Resolution.SECOND, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    valid = []
    rejected = Counter()
    for b in raw:
        end = et(b.end_time).to_pydatetime()
        if end <= START or end > CUTOFF:
            continue
        if b.symbol != symbol:
            rejected["WRONG_SYMBOL"] += 1
        elif getattr(b, "is_fill_forward", False):
            rejected["FILL_FORWARD"] += 1
        elif seconds(b.period) != 1 or seconds(b.end_time-b.time) != 1:
            rejected["NOT_NATIVE_1_SECOND"] += 1
        elif (float(b.volume) <= 0 or float(b.high) < max(
                float(b.open), float(b.low), float(b.close)) or
              float(b.low) > min(
                float(b.open), float(b.high), float(b.close))):
            rejected["BAD_OHLCV"] += 1
        else:
            valid.append((end, float(b.volume)))
    if len(set(t for t, _ in valid)) != len(valid):
        rejected["DUPLICATE_END"] += 1
        valid = list({t: (t, v) for t, v in valid}.values())
    stats = coverage_summary(valid, START, CUTOFF)
    print("QWCT 4.8b SEC COVERAGE", ticker,
          f"raw_rows={len(raw)} valid_native_traded_sec={stats['traded_seconds']}",
          "clock_seconds=270", f"rejected={dict(rejected)}")
    print("QWCT 4.8b SEC TIMING", ticker,
          f"first={stats['first']}", f"last={stats['last']}",
          f"exact_cutoff={stats['exact_cutoff']}",
          f"last_trade_age_s={stats['last_trade_age_s']}",
          f"max_gap_s={stats['max_interval_s']}",
          f"gaps_over_10s={stats['intervals_over_10s']}",
          f"traded_sec_per_minute={stats['per_minute']}",
          f"strict_10s_gate_possible={stats['native_10s_gate_possible']}")
    print("QWCT 4.8b WORST GAPS", ticker,
          [(a.strftime("%H:%M:%S"), b.strftime("%H:%M:%S"), gap)
           for a, b, gap in stats["worst_gaps"]])
    # Compare ONLY four entire M1 buckets to observed traded SEC volume.
    # Different vendor normalization / aggregation may disagree, so this
    # is diagnostic evidence, not a data-repair algorithm or a BPU signal.
    m1 = list(qb.history[TradeBar](
        symbol, START.replace(tzinfo=None),
        datetime(2024, 6, 3, 14, 40),
        Resolution.MINUTE, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    ends = {START+timedelta(minutes=i) for i in range(1, 5)}
    m1_map = {et(b.end_time).to_pydatetime(): float(b.volume)
              for b in m1 if et(b.end_time).to_pydatetime() in ends}
    sec_full_minutes = sum(volume for end, volume in valid
                           if end <= START+timedelta(minutes=4))
    if len(m1_map) == 4:
        minute_total = sum(m1_map.values())
        ratio = (round(sec_full_minutes/minute_total, 4)
                 if minute_total > 0 else None)
        print("QWCT 4.8b VOLUME CROSSCHECK", ticker,
              f"M1_4MIN={minute_total}",
              f"SECOND_4MIN={sec_full_minutes}",
              f"SEC_TO_M1_VOLUME_RATIO={ratio}",
              "DIAGNOSTIC_ONLY")
    else:
        print("QWCT 4.8b VOLUME CROSSCHECK", ticker,
              f"M1_OBSERVED={len(m1_map)}/4", "UNAVAILABLE")
    print("QWCT 4.8b RESULT", ticker,
          "NATIVE_SECOND_WINDOW_ONLY",
          "NOT_TVX_NOT_BPU_NO_ORDERS")


qb = QuantBook()
qb.set_time_zone("America/New_York")
qb.set_start_date(2024, 7, 1)
qb.set_end_date(2024, 7, 2)
for ticker in ("SRPT", "SPY"):
    audit_one(qb, ticker)
