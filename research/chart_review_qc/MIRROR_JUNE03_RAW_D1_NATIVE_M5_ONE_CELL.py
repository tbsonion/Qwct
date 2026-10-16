# QWCT 3.1 — single-cell QuantConnect Research, only preselected 2024-06-03 cases
# Paste the entire script into ONE NEW QuantConnect Research Notebook cell.
# Existing chart and 3.0 Cloud backtest code remain unchanged.
# 3 original positive June 3 cohort candidates and 1 preselected rejected control.
# Actual LEAN RAW D1 TradeBar source + LEAN M1->M5 consolidator, NO ORDERS.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session, native_cluster_tolerance, _confirmed_swings
from strategy.indicators import global_trend, trend_direction
from strategy import passes_gerchik_screener
from strategy.native_m5_validation import validate_m5_tradebar
from datetime import datetime, timedelta, time
from math import isfinite
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ET=ZoneInfo("America/New_York")
SESSION=datetime(2024,6,3)
# Source: exact FIRST day of native June-2024 QWCT 3.0 full PIT census,
# engine 2.5.0.0.18184 run f3bfd88e2caf06f53ff02c353b76d27f.
# Expected levels from BEFORE the 2024-06-03 trading session, NOT M5 outcomes.
CASES=[
    dict(ticker="AMAT",cluster=214.4600,decision="POSITIVE_LONG"),
    dict(ticker="NFLX",cluster=633.7750,decision="POSITIVE_LONG"),
    dict(ticker="SRPT",cluster=125.0000,decision="POSITIVE_LONG"),
    dict(ticker="MSFT",cluster=415.5900,decision="NEGATIVE_ROLE_CONTROL"),
]
cfg=StrategyConfig()
qb=QuantBook()
qb.set_start_date(2024,7,1)
qb.set_end_date(2024,7,2)
qb.set_time_zone("America/New_York")
print("QWCT 3.1 NATIVE SOURCE REVIEW: three Jun03 positives + one rejected control; "
      "no retroactive candidate selection, no orders, no TVX.")

def et(value):
    t=pd.Timestamp(value)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)

def typed_d1(symbol,mode):
    cutoff=SESSION.replace(hour=9,minute=29)
    original=list(qb.history[TradeBar](
        symbol,SESSION-timedelta(days=335),cutoff,
        Resolution.DAILY,fill_forward=False,data_normalization_mode=mode))
    if not original:
        raise ValueError("D1_NATIVE_HISTORY_EMPTY")
    rows,seen,previous=[],set(),None
    for bar in original:
        at,until=et(bar.time),et(bar.end_time)
        if (at.date()>=SESSION.date() or until>=et(cutoff)
                or until<=at or at.date() in seen
                or (previous is not None and at<=previous)
                or getattr(bar,"is_fill_forward",False)):
            raise ValueError("NONCAUSAL/DUPLICATE/FF_D1_NATIVE_BAR")
        seen.add(at.date());previous=at
        rows.append((at,bar))
    if len(rows)<180:
        raise ValueError(f"D1_ONLY_{len(rows)}_CLOSED_BARS_EXPECTED_180")
    return rows[-180:]

def native_d1_frame(rows):
    atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
    sma=SimpleMovingAverage(cfg.trend_sma)
    vol=SimpleMovingAverage(cfg.volume_lookback_days)
    frame=[]
    for at,b in rows:
        atr.update(b)
        sma.update(b.end_time,b.close)
        vol.update(b.end_time,b.volume)
        frame.append(dict(
            date=at,open=float(b.open),high=float(b.high),
            low=float(b.low),close=float(b.close),volume=float(b.volume),
            bar_end=et(b.end_time),
            **{f"atr{cfg.atr_period}":(
                float(atr.current.value) if atr.is_ready else float("nan")),
               f"sma{cfg.trend_sma}":(
                float(sma.current.value) if sma.is_ready else float("nan"))},
            volume_sma=float(vol.current.value) if vol.is_ready
               else float("nan")))
    d1=pd.DataFrame(frame).set_index("date")
    if len(d1)!=180 or d1.index[-1].date()>=SESSION.date():
        raise ValueError("D1_180_ASOF_CHECK_FAILED")
    return d1

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

def mirror_morning(case,d1):
    # Replay EXACT original 3.0 D1 morning gates on FROZEN previous D1.
    close=float(d1.iloc[-1]["close"])
    a=float(d1.iloc[-1][f"atr{cfg.atr_period}"])
    vol=float(d1.iloc[-1]["volume_sma"])
    stage2=passes_gerchik_screener(close,a,vol,cfg)
    gt=global_trend(d1,len(d1)-1,cfg)
    lt=trend_direction(d1,len(d1)-1,cfg)
    tol=native_cluster_tolerance(d1,cfg)
    if tol is None:
        raise ValueError("NATIVE_CLUSTER_ATR_UNAVAILABLE")
    levels=levels_for_session(d1,SESSION.date(),cfg)
    candidates=[x for x in levels
                if x.kind=="mirror" and x.source=="swing_cluster"
                and abs(x.price-case["cluster"])<=0.0001]
    if len(candidates)!=1:
        raise ValueError(f"MIRROR_COHORT_FREEZE_MISMATCH_{len(candidates)}")
    level=candidates[0]
    trace=audit_mirror(d1,level,SESSION.date(),cfg.swing_k,tol,cfg.mirror_lookback)
    old=trace["original_kind"]
    role=("support" if old=="resistance" else
          "resistance" if old=="support" else "UNKNOWN")
    side="short" if level.price>=close else "long"
    near=isfinite(a) and a>0 and abs(level.price-close)<=cfg.level_proximity_atr*a
    strong=level.touches>=cfg.min_touches and level.strength>=cfg.min_level_strength
    role_ok=((role=="support" and side=="long") or
             (role=="resistance" and side=="short"))
    trend_ok=gt==lt==(1 if side=="long" else -1)
    eligible=(stage2 and near and strong and role_ok and trend_ok and
              trace["status"]=="PROXY_VERIFIED")
    expected=case["decision"]=="POSITIVE_LONG"
    if bool(eligible)!=expected or (expected and side!="long"):
        raise ValueError(f"FROZEN_3_0_ELIGIBILITY_MISMATCH_{case['ticker']}"
                         f"_near{near}_role{role_ok}_trend{trend_ok}_proof{trace['status']}")
    # Original D1 first_idx MUST be a confirmed swing of the ORIGINAL kind.
    swing_field="high" if old=="resistance" else "low"
    confirmed=_confirmed_swings(d1,cfg.swing_k)[0 if old=="resistance" else 1]
    good_idx={i for i,_,_ in confirmed}
    if level.first_idx not in good_idx or level.last_idx not in good_idx:
        raise ValueError("ORIGINAL_FIRST_OR_LAST_NOT_CONFIRMED_D1_SWING")
    source_at=d1.index[level.first_idx]
    raw_origin=float(d1.iloc[level.first_idx][swing_field])
    print(f"QWCT 3.1 FROZEN {case['ticker']} date=2024-06-03 "
          f"decision={case['decision']} stage2={int(stage2)} "
          f"near={int(near)} role_ok={int(role_ok)} trend_ok={int(trend_ok)} "
          f"strong={int(strong)} proof={trace['status']} "
          f"research_eligible={int(eligible)} "
          f"prior_close={close:.4f} ATR14={a:.4f}")
    print(f"QWCT 3.1 SOURCE {case['ticker']} original={old} new_role={role} "
          f"source_date={source_at.date()} first_idx={level.first_idx} "
          f"last_idx={level.last_idx} swing_confirm={trace['swing_confirm']} "
          f"breach={trace['breach']} retest={trace['retest']} "
          f"valid_from={level.valid_from} "
          f"RAW_original_{swing_field}={raw_origin:.4f} "
          f"CLUSTER_median={level.price:.4f} "
          f"origin_minus_median={raw_origin-level.price:+.4f} "
          "BSU_MANUAL_UNVERIFIED")
    return level,trace,side,raw_origin,source_at,swing_field

def native_tick(symbol):
    try:
        tick=float(qb.securities[symbol].symbol_properties.minimum_price_variation)
    except Exception as ex:
        raise ValueError("NATIVE_SYMBOL_MINIMUM_PRICE_VARIATION_UNAVAILABLE") from ex
    if not isfinite(tick) or tick<=0:
        raise ValueError("INVALID_NATIVE_TICK")
    return tick

def scaled_basis(symbol,source_day,field,raw_origin,raw_close,tick):
    # D1 parity check only, not price adjustment of source or M5.
    try:
        scaled=typed_d1(symbol,DataNormalizationMode.SCALED_RAW)
    except Exception as ex:
        return "UNKNOWN_SCALED_HISTORY_"+type(ex).__name__,None,None
    byday={at.date():b for at,b in scaled}
    if source_day not in byday:
        return "UNKNOWN_SCALED_ORIGINAL_DATE_MISSING",None,None
    last_day=SESSION.date()-timedelta(days=3)   # DON'T infer market days from calendar
    del last_day
    latest=scaled[-1][1]
    origin=float(getattr(byday[source_day],field))
    close=float(latest.close)
    if not (isfinite(origin) and isfinite(close) and origin>0 and close>0):
        return "UNKNOWN_INVALID_SCALED_PRICE",origin,close
    if abs(close-raw_close)>tick/2+tick*1e-7:
        result="LATEST_CLOSE_BASIS_DIFFERENCE"
    elif abs(origin-raw_origin)>tick/2+tick*1e-7:
        result="REBASED_SOURCE_HISTORY"
    else:
        result="RAW_AND_SCALED_MATCH"
    return result,origin,close

def real_native_m5(symbol):
    """Only observed native RAW M1 into original LEAN TradeBarConsolidator(5m).

    Timestamp mapping uses native Bar Time + EndTime, not a resample/synthetic
    candle or a forward-filled minute. Incomplete 5m buckets never count as
    verified exact original wick touches.
    """
    start=SESSION.replace(hour=9,minute=30)
    stop=SESSION.replace(hour=16,minute=1)
    original=list(qb.history[TradeBar](
        symbol,start,stop,Resolution.MINUTE,
        fill_forward=False,extended_market_hours=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    seen=set();previous=None;minute=[]
    for b in original:
        bt,be=et(b.time),et(b.end_time)
        if not (bt.date()==SESSION.date() and
                time(9,30)<=bt.time()<time(16,0)):
            continue
        if (be.date()!=SESSION.date() or
            be-bt!=timedelta(minutes=1) or
            be.time()>time(16,0) or
            (previous is not None and bt<=previous) or
            bt in seen or
            getattr(b,"is_fill_forward",False) or
            not isfinite(float(b.volume)) or float(b.volume)<=0):
            raise ValueError("NATIVE_M1_INVALID_DUPLICATE_OR_NO_ACTUAL_VOLUME")
        previous=bt;seen.add(bt);minute.append(b)
    if not minute:
        raise ValueError("EMPTY_REAL_NATIVE_M1")
    emitted=[]
    consolidator=TradeBarConsolidator(timedelta(minutes=5))
    def collect(sender,bar):
        emitted.append(bar)
    consolidator.data_consolidated+=collect
    for b in minute:
        consolidator.update(b)
    # LEAN native end-of-day emission, only with genuine final 5 real M1s.
    starts={et(b.time) for b in minute}
    close_end=et(SESSION.replace(hour=16))
    final_start=close_end-timedelta(minutes=5)
    tail_ok=all((final_start+timedelta(minutes=i)) in starts for i in range(5))
    if tail_ok:
        consolidator.scan(minute[-1].end_time)
    expected=pd.date_range(
        pd.Timestamp("2024-06-03 09:35",tz=ET),
        pd.Timestamp("2024-06-03 16:00",tz=ET),
        freq="5min")
    frames=[];duplicates=set()
    for b in emitted:
        bt,be=et(b.time),et(b.end_time)
        if (bt.date()!=SESSION.date() or not time(9,35)<=be.time()<=time(16,0)):
            continue
        if be in duplicates:
            raise ValueError("DUPLICATE_EMITTED_M5")
        duplicates.add(be)
        valid,reason=validate_m5_tradebar(b,be.to_pydatetime())
        full5=all((bt+timedelta(minutes=i)) in starts for i in range(5))
        frame=dict(
            end=be,open=float(b.open),high=float(b.high),
            low=float(b.low),close=float(b.close),volume=float(b.volume),
            source_m1_count=sum((bt+timedelta(minutes=i)) in starts for i in range(5)),
            native_valid=int(valid),valid_reason=reason,
            verified_m5=bool(valid and full5))
        frames.append(frame)
    if not frames:
        raise ValueError("NO_NATIVE_CONSOLIDATED_M5")
    m5=pd.DataFrame(frames).set_index("end").sort_index()
    complete=m5.loc[m5["verified_m5"]]
    missing=[ts for ts in expected if ts not in complete.index]
    print(f"QWCT 3.1 NATIVE M5 M1={len(minute)} emitted={len(m5)} "
          f"fully_verified={len(complete)}/78 "
          f"first_missing_ET={[x.strftime('%H:%M') for x in missing[:8]]}"
          f" tail_final_real5={int(tail_ok)}")
    # No claiming a whole-session BPU1 absence when minute coverage incomplete.
    return m5,complete,not missing

def m5_geometry(m5,raw_origin,median,side,tick):
    """Separate exact ORIGINAL-source wick from mere OHLC straddles.

    Counts only LEAN native 5m bars with five real native source M1 candles.
    """
    valid=m5.loc[m5["verified_m5"]].copy()
    if valid.empty:
        return dict(exact=0,span=0,median_exact=0,first_span=None,
                    best_ticks=None,checked=0)
    extremum=valid["low"] if side=="long" else valid["high"]
    tol=tick/2+tick*1e-7
    exact=(extremum-raw_origin).abs()<=tol
    span=((valid["low"]<=raw_origin)&(valid["high"]>=raw_origin)&~exact)
    medexact=(extremum-median).abs()<=tol
    best=float(((extremum-raw_origin).abs()/tick).min())
    first_span=valid.loc[span].index.min() if span.any() else None
    return dict(exact=int(exact.sum()),span=int(span.sum()),
                median_exact=int(medexact.sum()),
                first_span=first_span,best_ticks=best,checked=len(valid))

def plot_native_case(case,d1,m5,source_at,raw_origin,level,side,full):
    fig=make_subplots(rows=2,cols=1,row_heights=[.42,.58],
        vertical_spacing=.13,
        subplot_titles=("Original RAW closed D1 as-of Jun03 09:29 ET",
                        "Actually observed LEAN RAW M1→native Consolidator M5"))
    fig.add_trace(go.Candlestick(x=d1.index,open=d1["open"],
        high=d1["high"],low=d1["low"],close=d1["close"],name="RAW D1"),
        row=1,col=1)
    # Incomplete native M5 not drawn as full legitimate source evidence.
    shown=m5.loc[m5["verified_m5"]]
    if not shown.empty:
        fig.add_trace(go.Candlestick(x=shown.index,open=shown["open"],
            high=shown["high"],low=shown["low"],close=shown["close"],
            name="Native, 5 real M1→M5"),row=2,col=1)
    bad=m5.loc[~m5["verified_m5"]]
    if not bad.empty:
        fig.add_trace(go.Scatter(x=bad.index,y=bad["close"],mode="markers",
            marker=dict(symbol="x",size=10,color="black"),
            name="INCOMPLETE/UNVERIFIED M5 — EXCLUDED"),row=2,col=1)
    for row in (1,2):
        fig.add_hline(y=raw_origin,line_color="red",line_width=2,
            annotation_text="RAW first confirmed swing source",row=row,col=1)
        fig.add_hline(y=level.price,line_color="blue",line_width=2,
            line_dash="dash",annotation_text="D1 ATR-cluster median",row=row,col=1)
    fig.add_trace(go.Scatter(x=[source_at],y=[raw_origin],mode="markers",
        marker=dict(color="red",size=12,symbol="diamond"),
        name="Original first_idx source"),row=1,col=1)
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_layout(height=980,width=1200,
        title=f"QWCT 3.1 {case['ticker']} Jun03 {case['decision']} / "
              f"RAW source vs median / complete 78-native-M5={int(full)} / NO ORDERS",
        legend=dict(orientation="h",y=1.09))
    fig.show()

for case in CASES:
    ticker=case["ticker"]
    print(f"\n====== QWCT 3.1 {ticker} {case['decision']} ======")
    try:
        symbol=qb.add_equity(
            ticker,Resolution.MINUTE,fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        raw=typed_d1(symbol,DataNormalizationMode.RAW)
        d1=native_d1_frame(raw)
        level,proof,side,origin,source_at,field=mirror_morning(case,d1)
        tick=native_tick(symbol)
        delta=(level.price-origin)/tick
        ongrid=abs(origin-round(origin/tick)*tick)<=tick*1e-5
        basis,scaled_origin,scaled_close=scaled_basis(
            symbol,source_at.date(),field,origin,float(d1.iloc[-1]["close"]),tick)
        print(f"QWCT 3.1 PRICE {ticker} native_tick={tick:.6f} "
              f"RAW_origin_grid={int(ongrid)} "
              f"cluster_minus_RAW_in_ticks={delta:.2f} "
              f"RAW_SCALED_basis={basis} "
              f"scaled_origin={scaled_origin} scaled_last_close={scaled_close} "
              "NO_SOURCE_AUTHORIZATION")
        m5,full_m5,full=real_native_m5(symbol)
        geometry=m5_geometry(m5,origin,level.price,side,tick)
        print(f"QWCT 3.1 GEOMETRY {ticker} side={side} "
              f"verified_M5={geometry['checked']}/78 "
              f"origin_wick_half_tick={geometry['exact']} "
              f"origin_OHLC_straddles_not_exact={geometry['span']} "
              f"cluster_median_wick_half_tick={geometry['median_exact']} "
              f"closest_original_ticks={geometry['best_ticks']} "
              f"first_original_straddle_ET={geometry['first_span']} "
              f"FULL_SESSION_SOURCE_COVERAGE={int(full)} "
              "BPU1_BPU2_TVX_UNVERIFIED_NO_ORDERS")
        if geometry["first_span"] is not None:
            i=m5.index.get_loc(geometry["first_span"])
            print("QWCT 3.1 M5 FIRST ORIGINAL PIVOT STRADDLE AND ADJACENT CLOSED BARS")
            display(m5.iloc[max(0,i-1):min(len(m5),i+3)]
                [["open","high","low","close","source_m1_count",
                  "verified_m5"]].round(4))
        plot_native_case(case,d1,m5,source_at,origin,level,side,full)
    except Exception as exc:
        print(f"QWCT 3.1 ERROR {ticker} {type(exc).__name__}: {exc}; "
              "FAIL CLOSED / NO ORIGINAL BSU OR M5 CLAIM")
