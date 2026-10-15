# QWCT 2.9 STEP 2 — actual existing mirror-level scan on frozen historical D1
# PASTE IN NEW Research cell (below AON/DELL charts). Shift+Enter.
# Only approved as-of source evidence; no orders, no amended BPU1 tolerance.
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo
import pandas as pd
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session, native_cluster_tolerance

"""Independent read-only validation of Qwct D1 mirror candidates as-of session.

Not a Gerchik manual level label, detector, signal gate or trading approval.
Uses existing Level metadata and strictly prior closed D1 OHLC.
"""
from datetime import timedelta
from math import isfinite


def audit_mirror(d1, level, session, swing_k, tolerance, lookback=60):
    """Return a reproducible causal D1 mirror source/breach/retest trace.

    Side must be inferred unambiguously from the ORIGINAL source bar's
    low/high proximity to the D1 cluster price; otherwise fail closed.
    An accepted mirror is still ONLY an automatic cluster-level proxy.
    """
    out = dict(status="UNKNOWN", reason="", original_kind=None,
               source=None, swing_confirm=None, breach=None,
               retest=None, valid_from=None, price=None)
    def finish(status, reason):
        out["status"], out["reason"] = status, reason
        return out
    if (getattr(level, "kind", None) != "mirror" or
            getattr(level, "source", None) != "swing_cluster"):
        return finish("SKIP", "NOT_SWING_MIRROR")
    if (d1 is None or len(d1)<2*swing_k+5 or
            not d1.index.is_unique or not d1.index.is_monotonic_increasing):
        return finish("UNKNOWN", "INVALID_D1_FRAME")
    i, j = level.first_idx, level.last_idx
    if not isinstance(swing_k,int) or swing_k<1 or not(
            swing_k<=i<j and j+swing_k<len(d1)):
        return finish("UNKNOWN", "UNCONFIRMED_SWING_WINDOW")
    price=float(level.price)
    tol=float(tolerance)
    if not all(isfinite(z) and z>0 for z in (price,tol)):
        return finish("UNKNOWN","BAD_PRICE_OR_CLUSTER_TOLERANCE")
    if level.valid_from is None or level.valid_from>session:
        return finish("UNKNOWN","NOT_VALID_BEFORE_SESSION")
    dates=[x.date() for x in d1.index]
    if (dates[-1]>=session or
            any(a>=b for a,b in zip(dates,dates[1:]))):
        return finish("UNKNOWN","D1_NOT_CAUSAL_TO_SESSION")
    source=d1.iloc[i]
    high,low=float(source["high"]),float(source["low"])
    if high<low or not all(isfinite(v) for v in (high,low)):
        return finish("UNKNOWN","INVALID_SOURCE_OHLC")
    is_high=abs(high-price)<=tol
    is_low=abs(low-price)<=tol
    if is_high==is_low:
        return finish("UNKNOWN","ORIGINAL_KIND_AMBIGUOUS")
    kind="resistance" if is_high else "support"
    last_confirm=dates[j+swing_k]
    base_from=last_confirm+timedelta(days=1)
    if (level.formed_at!=dates[j] or
            level.valid_from<=last_confirm):
        return finish("UNKNOWN","LEVEL_CHRONOLOGY_MISMATCH")
    out.update(original_kind=kind,source=str(dates[i]),
               swing_confirm=str(last_confirm),
               price=price,valid_from=str(level.valid_from))
    start=max(j+1,len(d1)-lookback,1)
    while start<len(d1) and dates[start]<base_from:
        start+=1
    breached=None
    for idx in range(start,len(d1)):
        b=d1.iloc[idx]
        if kind=="support":
            confirmed=(breached is not None and float(b["high"])>=price
                       and float(b["close"])<price)
            if not confirmed and float(b["close"])<price and breached is None:
                breached=idx
        else:
            confirmed=(breached is not None and float(b["low"])<=price
                       and float(b["close"])>price)
            if not confirmed and float(b["close"])>price and breached is None:
                breached=idx
        if confirmed:
            out["breach"]=str(dates[breached])
            out["retest"]=str(dates[idx])
            if dates[idx]+timedelta(days=1)!=level.valid_from:
                return finish("UNKNOWN","RETEST_DATE_DISAGREES_WITH_VALID_FROM")
            return finish("PROXY_VERIFIED","CLOSED_D1_BREACH_RETEST_ASOF")
    return finish("UNKNOWN","NO_SEPARATE_CAUSAL_BREACH_AND_RETEST")


def mirror_inventory(d1, levels, session, swing_k, tolerance, lookback=60):
    """Use only the supplied frozen D1 and user-supplied original Levels."""
    return [(level, audit_mirror(d1,level,session,swing_k,tolerance,lookback))
            for level in levels if level.kind=="mirror"]

# Uses original QuantConnect D1 TradeBar objects and built-in LEAN indicators,
# NOT reconstructed/synthetic market bars or hand-written ATR.
# Self-contained: a fresh Research kernel may not have run the earlier chart cell.
qb=QuantBook()
qb.set_start_date(2024, 7, 1)
qb.set_end_date(2024, 7, 2)
qb.set_time_zone("America/New_York")

cfg=StrategyConfig()
et_zone=ZoneInfo("America/New_York")
REVIEW_CASES = [
    ("AON","2024-06-12","2024-05-10",293.5900),
    ("DELL","2024-06-07","2024-05-14",128.7500),
]

for ticker,day_text,source_text,pivot in REVIEW_CASES:
    day=datetime.strptime(day_text,"%Y-%m-%d")
    cutoff=day.replace(hour=9,minute=29)
    symbol=qb.add_equity(ticker, Resolution.MINUTE, fill_forward=False,
                         data_normalization_mode=DataNormalizationMode.RAW).symbol
    try:
        original=list(qb.history[TradeBar](
            symbol,day-timedelta(days=335),cutoff,Resolution.DAILY,
            fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW))
        # Date-only D1 algorithm uses end-of-day dates, all before target morning.
        previous=None
        safe=[]
        for b in original:
            start=pd.Timestamp(b.time)
            end=pd.Timestamp(b.end_time)
            if start.tzinfo is None:
                start=start.tz_localize(et_zone)
            else:
                start=start.tz_convert(et_zone)
            if end.tzinfo is None:
                end=end.tz_localize(et_zone)
            else:
                end=end.tz_convert(et_zone)
            if (start.date() >= day.date() or end>=pd.Timestamp(cutoff,tz=et_zone)
                    or (previous is not None and start<=previous)):
                raise ValueError("NONCAUSAL/UNORDERED_NATIVE_D1")
            previous=start
            safe.append((start,b))
        if len(safe)<180:
            raise ValueError(f"INSUFFICIENT_NATIVE_D1_{len(safe)}")
        safe=safe[-180:]
        atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
        sma=SimpleMovingAverage(cfg.trend_sma)
        vol=SimpleMovingAverage(cfg.volume_lookback_days)
        rows=[]
        days=[]
        for at,b in safe:
            atr.update(b)
            sma.update(b.end_time,b.close)
            vol.update(b.end_time,b.volume)
            rows.append(dict(
                open=float(b.open),high=float(b.high),low=float(b.low),
                close=float(b.close),volume=float(b.volume),
                bar_end=pd.Timestamp(b.end_time),
                **{f"atr{cfg.atr_period}":(
                   float(atr.current.value) if atr.is_ready else float("nan")),
                   f"sma{cfg.trend_sma}":(
                   float(sma.current.value) if sma.is_ready else float("nan"))},
                volume_sma=float(vol.current.value) if vol.is_ready
                    else float("nan")))
            days.append(at.normalize())
        d1=pd.DataFrame(rows,index=pd.DatetimeIndex(days))
        source_at=pd.Timestamp(source_text,tz=et_zone)
        if source_at not in d1.index:
            raise ValueError("HISTORICAL_ORIGINAL_SOURCE_NOT_IN_ASOF_D1")
        if not (abs(float(d1.loc[source_at,"high"])-pivot)<.0001
                or abs(float(d1.loc[source_at,"low"])-pivot)<.0001):
            raise ValueError("ORIGINAL_RAW_SOURCE_PRICE_MISMATCH")
        frozen=levels_for_session(d1,day.date(),cfg)
        mirrors=[x for x in frozen if x.kind=="mirror"]
        tol=native_cluster_tolerance(d1,cfg)
        if tol is None:
            raise ValueError("NATIVE_ATR_CLUSTER_TOL_NOT_READY")
        print(f"\nQWCT MIRROR REVIEW {ticker} {day_text} "
              f"full_d1={len(d1)} levels={len(frozen)} mirrors={len(mirrors)} "
              f"native_ATR_cluster_tol={tol:.4f}")
        if not mirrors:
            print("NO AUTO-MIRRORS AS-OF. This does not prove no manual Gerchik BSU.")
        for l in sorted(mirrors,key=lambda z:abs(z.price-pivot))[:12]:
            e=audit_mirror(d1,l,day.date(),cfg.swing_k,tol,cfg.mirror_lookback)
            print("QWCT MIRROR CASE",
                  "price",round(l.price,4),
                  "source",e["source"],
                  "old_side",e["original_kind"],
                  "breach",e["breach"],
                  "retest",e["retest"],
                  "valid_from",l.valid_from,
                  "status",e["status"],
                  "reason",e["reason"],
                  "NOT_BPU1 / NO_ORDERS")
    except Exception as exc:
        print(f"QWCT MIRROR ERROR {ticker} {type(exc).__name__}: {exc}")
        # Fail closed: no mirror count or claimed signal on incomplete history.
