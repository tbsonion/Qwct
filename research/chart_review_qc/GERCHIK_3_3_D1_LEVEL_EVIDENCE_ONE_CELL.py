# QWCT 3.3 — single-cell QuantConnect Research, only preselected 2024-06-03 cases
# Paste the entire script into ONE NEW QuantConnect Research Notebook cell.
# Existing chart and 3.0 Cloud backtest code remain unchanged.
# 3 original positive June 3 cohort candidates and 1 preselected rejected control.
# ONLY original LEAN RAW D1 TradeBar source; NO M1/M5 requests or orders.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session, native_cluster_tolerance, _confirmed_swings
from strategy.levels import frozen_mirror_source_evidence
from strategy.indicators import observe_d1_level_reactions, D1_REACTION_KINDS
from strategy.indicators import (
    discover_bsu_price_candidates, audit_author_bsu_labels,
    audit_author_reaction_labels,
)
from strategy.indicators import global_trend, trend_direction
from strategy import passes_gerchik_screener
from datetime import datetime, timedelta
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
# IMPORTANT: these are EMPTY because no authenticated per-ticker D1 annotated
# source-bar / price / dated-reaction labels for the 2024-06-03 cohort exist.
# Never guess them from unrelated Brent charts or from synthetic BSU examples.
AUTHOR_BSU_MARKUPS = {}     # ticker -> tuple[GerchikChartLabel, ...]
AUTHOR_REACTION_MARKUPS = {}  # ticker -> tuple[GerchikChartLabel, ...]
qb=QuantBook()
qb.set_start_date(2024,7,1)
qb.set_end_date(2024,7,2)
qb.set_time_zone("America/New_York")
print("QWCT 3.3 NATIVE SOURCE REVIEW: three Jun03 positives + one rejected control; "
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
    print(f"QWCT 3.3 FROZEN {case['ticker']} date=2024-06-03 "
          f"decision={case['decision']} stage2={int(stage2)} "
          f"near={int(near)} role_ok={int(role_ok)} trend_ok={int(trend_ok)} "
          f"strong={int(strong)} proof={trace['status']} "
          f"research_eligible={int(eligible)} "
          f"prior_close={close:.4f} ATR14={a:.4f}")
    print(f"QWCT 3.3 SOURCE {case['ticker']} original={old} new_role={role} "
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


def asof_d1_event(frame,iso):
    """Resolve causal D1 event by EXCHANGE-LOCAL SESSION DATE, not midnight.

    Native QC daily bar indexes may retain a non-midnight timestamp.
    audit_mirror deliberately reports source/breach/retest as D1 dates.
    Preserve the original native index timestamp and reject duplicates.
    """
    if iso is None:
        raise ValueError("MISSING_CAUSAL_D1_BREACH_OR_RETEST")
    if (frame is None or not isinstance(frame.index,pd.DatetimeIndex)
            or frame.index.tz is None
            or not frame.index.is_monotonic_increasing):
        raise ValueError("INVALID_NATIVE_D1_DATE_INDEX")
    try:
        date=pd.Timestamp(iso).date()
    except (ValueError,TypeError,OverflowError) as ex:
        raise ValueError("INVALID_HISTORICAL_D1_EVENT_DATE") from ex
    matching=[i for i,day in enumerate(frame.index)
              if day.date()==date]
    if not matching:
        raise ValueError(f"HISTORICAL_D1_EVENT_NOT_IN_ASOF_FRAME_{iso}")
    if len(matching)!=1:
        raise ValueError(f"AMBIGUOUS_HISTORICAL_D1_EVENT_DATE_{iso}")
    index=matching[0]
    # Never invent a midnight/close candle; use original native RAW D1 bar.
    return frame.index[index],frame.iloc[index]

def price_hypotheses(d1,level,trace,side,tick):
    if trace["status"]!="PROXY_VERIFIED":
        raise ValueError("MIRROR_D1_CHRONOLOGY_NOT_PROVEN")
    source_at=d1.index[level.first_idx]
    last_at=d1.index[level.last_idx]
    breach_at,breach=asof_d1_event(d1,trace["breach"])
    retest_at,retest=asof_d1_event(d1,trace["retest"])
    if not (source_at<=last_at<breach_at<retest_at<d1.index[-1]+timedelta(days=1)):
        raise ValueError("SOURCE_LAST_BREACH_RETEST_NOT_STRICTLY_CAUSAL")
    # New support is touched by LOW from above; new resistance by HIGH
    # from below. Mirror confirmation alone DOES NOT establish a BPU1.
    # Mirror's NEW ROLE, not a disqualified trade-side (MSFT negative), fixes
    # which D1 retest wick is appropriate. In old resistance -> support the
    # retest is LOW even if algorithmic morning trade-side=short (rejected).
    field="low" if trace["original_kind"]=="resistance" else "high"
    origfield="high" if trace["original_kind"]=="resistance" else "low"
    prices=[
        ("FIRST_SWING",source_at,float(d1.iloc[level.first_idx][origfield]),origfield),
        ("LAST_SWING",last_at,float(d1.iloc[level.last_idx][origfield]),origfield),
        ("CLUSTER_MEDIAN",None,float(level.price),"software_only"),
        ("D1_ROLE_RETEST",retest_at,float(retest[field]),field)]
    for name,at,price,barfield in prices:
        if price<=0 or not isfinite(price):
            raise ValueError("BAD_D1_FIXED_PRICE_HYPOTHESIS")
    print(f"QWCT 3.3 HISTORICAL EVENTS "
          f"breach={breach_at.date()} breach_OHLC="
          f"{tuple(round(float(breach[k]),4) for k in ('open','high','low','close'))} "
          f"retest={retest_at.date()} retest_OHLC="
          f"{tuple(round(float(retest[k]),4) for k in ('open','high','low','close'))} "
          f"mirror_valid_from={level.valid_from}")
    for name,at,price,barfield in prices:
        delta=(price-prices[0][2])/tick
        ongrid=(abs(price-round(price/tick)*tick)<=tick*1e-5)
        print(f"QWCT 3.3 D1 CANDIDATE {name} "
              f"date={at.date() if at is not None else 'NONE_software'} "
              f"field={barfield} price={price:.6f} "
              f"delta_from_FIRST_ticks={delta:+.2f} "
              f"current_native_grid={int(ongrid)} "
              "NOT_AUTHOR_BSU / NOT_BPU1")
    return prices,(breach_at,breach),(retest_at,retest)

# QWCT 3.8: read-only mapping for annotation of ALREADY VERIFIED frozen D1.
# Never use these rendering records for ranking, screening or author BSU.
def chart_reaction_markers(d1,evidences):
    if (not isinstance(d1,pd.DataFrame) or
            not isinstance(d1.index,pd.DatetimeIndex) or
            d1.index.tz is None or not d1.index.is_unique or
            not d1.index.is_monotonic_increasing):
        raise ValueError("QWCT38_INVALID_FROZEN_D1_INDEX")
    by_day={}
    for i,stamp in enumerate(d1.index):
        if stamp.date() in by_day:
            raise ValueError("QWCT38_DUPLICATE_D1_SESSION")
        by_day[stamp.date()]=(stamp,d1.iloc[i])
    out=[]
    for e in evidences:
        if (e.label not in ("FIRST_SWING","LAST_SWING") or
                e.status!="AUTHOR_UNVERIFIED" or e.can_trade):
            raise ValueError("QWCT38_ONLY_UNVERIFIED_SOURCES")
        if not e.source_date in by_day:
            raise ValueError("QWCT38_SOURCE_MISSING")
        if not e.confirmed_date in by_day:
            raise ValueError("QWCT38_CONFIRMATION_MISSING")
        if not e.price>0:
            raise ValueError("QWCT38_INVALID_SOURCE_PRICE")
        for obs in e.wick_reactions:
            if obs.event not in ("TAIL_ONLY_RECLAIM","BODY_CROSS_RECLAIM",
                                  "CLOSED_WRONG_SIDE"):
                continue  # 'TOUCH_OR_STRADDLE' has no approved annotation.
            if obs.at not in by_day or obs.at <= e.confirmed_date:
                raise ValueError("QWCT38_NONCAUSAL_WICK_DATE")
            stamp,candle=by_day[obs.at]
            if obs.role not in ("support","resistance"):
                raise ValueError("QWCT38_INVALID_D1_ROLE")
            # Green/orange: show the side actually defended (tip of wick).
            # Red: the CLOSE that ended on the wrong side of the level.
            price=(float(candle.close) if obs.event=="CLOSED_WRONG_SIDE"
                   else float(candle.low) if obs.role=="support"
                   else float(candle.high))
            if not float(candle.low)<=price<=float(candle.high):
                raise ValueError("QWCT38_EVENT_OUTSIDE_CANDLE")
            body_ratio=("N/A" if obs.wick_to_body is None else
                        f"{obs.wick_to_body:.2f}")
            atr_ratio=("N/A" if obs.wick_to_atr is None else
                       f"{obs.wick_to_atr:.2f}")
            tip=(f"source={e.label} @ {e.price:.4f}<br>"
                 f"date={obs.at}; role={obs.role}<br>"
                 f"event={obs.event}<br>"
                 f"tail/body={body_ratio}; tail/native D1 ATR={atr_ratio}<br>"
                 f"OHLC={candle.open:.4f}/{candle.high:.4f}/"
                 f"{candle.low:.4f}/{candle.close:.4f}<br>"
                 "OBSERVATION ONLY, NOT APPROVED BSU/BPU1")
            out.append(dict(at=stamp,date=obs.at,kind=obs.event,
                            y=price,source=e.label,role=obs.role,
                            tip=tip))
        # Purple: the SECOND closed D1 candle of a two-bar reentry.
        # This might have no wick intersection and must be marked at its
        # actual close, not inferred from a wick signal.
        for role,events in (
                ("ORIGINAL",e.original_two_bar_reclaim_dates),
                ("MIRROR",e.mirror_two_bar_reclaim_dates)):
            for at in events:
                if at not in by_day or at <= e.confirmed_date:
                    raise ValueError("QWCT38_NONCAUSAL_TWO_BAR_DATE")
                stamp,candle=by_day[at]
                tip=(f"source={e.label} @ {e.price:.4f}<br>"
                     f"date={at}; phase={role}<br>"
                     "event=TWO_CLOSED_D1_REENTRY (second close)<br>"
                     f"OHLC={candle.open:.4f}/{candle.high:.4f}/"
                     f"{candle.low:.4f}/{candle.close:.4f}<br>"
                     "NOT AN AUTHOR-CERTIFIED FALSE BREAK / BPU1")
                out.append(dict(at=stamp,date=at,kind="TWO_BAR_REENTRY",
                                y=float(candle.close),source=e.label,
                                role=role,tip=tip))
    return tuple(out)


def chart_taxonomy_markers(d1, tags):
    """Chart adapter: only precomputed closed D1 dated observations."""
    if (not isinstance(d1.index,pd.DatetimeIndex) or
            d1.index.tz is None or not d1.index.is_unique or
            not d1.index.is_monotonic_increasing):
        raise ValueError("QWCT39_BAD_D1_CHART_INDEX")
    days={}
    for stamp in d1.index:
        if stamp.date() in days:
            raise ValueError("QWCT39_DUPLICATE_DATE")
        days[stamp.date()]=stamp
    points=[]
    for tag in tags:
        if (tag.kind not in D1_REACTION_KINDS or
                tag.can_trade or
                tag.observed_on not in days or
                tag.anchor_on not in days or
                tag.observed_on<tag.anchor_on or
                not isfinite(tag.reference_price) or tag.reference_price<=0):
            raise ValueError("QWCT39_BAD_OR_FUTURE_TAG")
        stamp=days[tag.observed_on]
        row=d1.loc[stamp]
        tip=(f"QWCT 3.9 {tag.kind}<br>"
             f"source={tag.source_label} reference={tag.reference_price:.4f}<br>"
             f"confirmed_on={tag.observed_on}; window_from={tag.anchor_on}<br>"
             f"phase={tag.phase}; basis={tag.basis}<br>"
             f"OHLC={row.open:.4f}/{row.high:.4f}/{row.low:.4f}/"
             f"{row.close:.4f}<br>"
             "HEURISTIC/OBSERVATION ONLY, NOT APPROVED BSU/BPU1")
        points.append(dict(kind=tag.kind,at=stamp,y=float(row.close),tip=tip))
    return tuple(points)


def plot_d1_evidence(case,d1,prices,breach,retest,markers,taxonomy_marks):
    # Exactly the SAME historical candles as the ORIGINAL QWCT 3.0
    # morning freeze. No candle from 2024-06-03 or later appears.
    fig=make_subplots(rows=2,cols=1,row_heights=[.44,.56],
                      vertical_spacing=.12,
                      subplot_titles=("FULL original 180 RAW D1 (prior closes only)",
                                      "EVENT REGION D1 ONLY; no future M5"))
    recent=d1.loc[d1.index>=d1.index[max(0,len(d1)-85)]]
    datasets=(d1,recent)
    reactions=(
        ("TAIL_ONLY_RECLAIM","3.8 Tail-only wick reclaim","forestgreen","circle"),
        ("BODY_CROSS_RECLAIM","3.8 Body-cross reclaim","darkorange","diamond"),
        ("CLOSED_WRONG_SIDE","3.8 D1 close wrong side","firebrick","x"),
        ("TWO_BAR_REENTRY","3.8 Two D1 close reentry","darkviolet","star"),
    )
    # 10 separate observed event categories; labels are research-only,
    # not author-certified setups. Dense patterns can be hidden by legend.
    taxonomy_style=(
        ("BOUNCE","Bounce (next close)","#168139","triangle-up"),
        ("WICK_BOUNCE","Wick bounce (next close)","#008080","triangle-down"),
        ("WICK_RECLAIM","Wick reclaim","#089c67","circle-open"),
        ("FALSE_BREAK_1BAR","One-bar false-break proxy","#d47b00","diamond-open"),
        ("FALSE_BREAK_2BAR","Two-bar false-break proxy","#8a40b8","star-open"),
        ("BREAK_FOLLOWTHROUGH","Break + 2 closes (proxy)","#bd1f32","square"),
        ("MIRROR_RETEST","Mirror retest (cluster audit)","#3374a5","cross"),
        ("COMPRESSION","Compression proxy","#916c1b","triangle-right"),
        ("CONSOLIDATION","Consolidation proxy","#5d6f7a","pentagon"),
        ("CHOP","Chop proxy","#515151","hourglass"),
    )
    for row,frame in enumerate(datasets,start=1):
        fig.add_trace(go.Candlestick(
            x=frame.index,open=frame["open"],high=frame["high"],
            low=frame["low"],close=frame["close"],
            name="RAW D1 closed",showlegend=(row==1)),row=row,col=1)
        shapes=[
            ("FIRST source RAW high/low",prices[0][2],"crimson"),
            ("LAST confirmed swing",prices[1][2],"darkorange"),
            ("ATR cluster median: SOFTWARE",prices[2][2],"royalblue"),
            ("prior D1 mirror retest low/high",prices[3][2],"forestgreen"),
        ]
        for title,p,col in shapes:
            fig.add_trace(go.Scatter(
                x=[frame.index[0],frame.index[-1]],y=[p,p],mode="lines",
                name=title,showlegend=(row==1),
                line=dict(color=col,width=2,
                          dash="dash" if title.startswith("ATR") else "solid")
                ),row=row,col=1)
        for event,title,col,field in (
            (prices[0][1],"FIRST D1 swing","crimson",prices[0][3]),
            (prices[1][1],"LAST D1 swing","darkorange",prices[1][3]),
            (breach[0],"D1 close-through breach","gray","close"),
            (retest[0],"D1 role reversal retest","forestgreen",
             prices[3][3])):
            if event in frame.index:
                fig.add_trace(go.Scatter(
                    x=[event],y=[float(frame.loc[event][field])],
                    mode="markers",name=title,showlegend=(row==1),
                    marker=dict(color=col,size=12,symbol="diamond")),
                    row=row,col=1)
        # Four distinct event layers; legend toggles both FIRST and LAST
        # candidates. Events before the zoom window stay on the full panel.
        for kind,label,color,symbol in reactions:
            subset=[p for p in markers if p["kind"]==kind and
                    p["at"] in frame.index]
            if not subset:
                continue
            fig.add_trace(go.Scatter(
                x=[p["at"] for p in subset],
                y=[p["y"] for p in subset],
                mode="markers",name=label,legendgroup=kind,
                showlegend=(row==1),
                marker=dict(color=color,symbol=symbol,size=9,
                            line=dict(width=1,color="white"),opacity=.85),
                text=[p["tip"] for p in subset],
                hovertemplate="%{text}<extra></extra>"),row=row,col=1)
        for kind,label,color,symbol in taxonomy_style:
            subset=[p for p in taxonomy_marks
                    if p["kind"]==kind and p["at"] in frame.index]
            if not subset:
                continue
            fig.add_trace(go.Scatter(
                x=[p["at"] for p in subset],y=[p["y"] for p in subset],
                mode="markers",name="3.9 "+label,
                legendgroup="QWCT39_"+kind,showlegend=(row==1),
                marker=dict(color=color,size=10,symbol=symbol,
                            line=dict(width=1,color=color),opacity=.75),
                text=[p["tip"] for p in subset],
                hovertemplate="%{text}<extra></extra>",
                visible=True if kind in ("BOUNCE","BREAK_FOLLOWTHROUGH",
                                          "MIRROR_RETEST","COMPRESSION") else
                        "legendonly"
                ),row=row,col=1)
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_layout(
        width=1440,height=980,margin=dict(t=125,r=270,b=60,l=65),
        title=f"QWCT 3.9 {case['ticker']} / 2024-06-03 "
              f"{case['decision']} / D1 REACTIONS NOT APPROVED BSU",
        legend=dict(orientation="v",x=1.02,y=1.0,
                    bgcolor="rgba(255,255,255,0.9)"),
        hovermode="closest")
    fig.show()

for case in CASES:
    ticker=case["ticker"]
    print(f"\\n======== QWCT 3.3 SOURCE DECISION {ticker} ========")
    try:
        symbol=qb.add_equity(
            ticker,Resolution.DAILY,fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        d1=native_d1_frame(typed_d1(symbol,DataNormalizationMode.RAW))
        lvl,trace,side,original,source_at,old_field=mirror_morning(case,d1)
        tick=native_tick(symbol)
        print(f"QWCT 3.3 NATIVE TICK {ticker} {tick:.6f}; "
              "source prices are AS-OF ORIGINAL RAW, no M1/M5 requests.")
        prices,breach,retest=price_hypotheses(d1,lvl,trace,side,tick)
        # QWCT 3.5: actual already-fetched as-of D1 observations, not author
        # BSU approval, not BPU1, no new history queries and no orders.
        evidences=frozen_mirror_source_evidence(
            d1,lvl,trace,session=SESSION.date(),
            tick_size=tick,swing_k=cfg.swing_k,
            atr_column=f"atr{cfg.atr_period}")
        for e in evidences:
            print("QWCT 3.5 SOURCE WICK EVIDENCE",ticker,e.label,
                  e.price,e.current_grid,len(e.mirror_wick_reclaim_dates),
                  len(e.mirror_two_bar_reclaim_dates),"AUTHOR_UNVERIFIED")
            # Tail length = real D1 OHLC geometry; do not manufacture author
            # thresholds, and never call this a confirmed BSU/BPU1.
            observations = e.wick_reactions
            tail_only = [x for x in observations if x.event == "TAIL_ONLY_RECLAIM"]
            body_cross = [x for x in observations if x.event == "BODY_CROSS_RECLAIM"]
            strong_tail = [x.wick_to_atr for x in tail_only
                           if x.wick_to_atr is not None]
            print(f"QWCT 3.7 D1 TAIL GEOMETRY {ticker} {e.label} "
                  f"observed={len(observations)} "
                  f"tail_only_reclaim={len(tail_only)} "
                  f"body_cross_reclaim={len(body_cross)} "
                  f"max_tail_vs_historical_LEAN_ATR="
                  f"{max(strong_tail):.3f}" if strong_tail else
                  f"QWCT 3.7 D1 TAIL GEOMETRY {ticker} {e.label} "
                  f"observed={len(observations)} "
                  f"tail_only_reclaim={len(tail_only)} "
                  f"body_cross_reclaim={len(body_cross)} "
                  "max_tail_vs_historical_LEAN_ATR=UNKNOWN")
            print(f"QWCT 3.7 TAIL DATES {ticker} {e.label} "
                  f"{','.join(map(str,(x.at for x in tail_only))) or 'NONE'} "
                  "NO_AUTO_STRONG_WEAK_NO_AUTHOR_BSU_NO_ORDERS")
        markers=chart_reaction_markers(d1,evidences)
        print(f"QWCT 3.8 CHART MARKERS {ticker} "
              + " ".join(f"{kind}={sum(p['kind']==kind for p in markers)}"
                         for kind in ("TAIL_ONLY_RECLAIM","BODY_CROSS_RECLAIM",
                                      "CLOSED_WRONG_SIDE","TWO_BAR_REENTRY"))
              + " READ_ONLY NOT_AUTHOR_BSU NOT_BPU1 NO_ORDERS")
        ten=[]
        for e in evidences:
            found=observe_d1_level_reactions(
                d1,e,trace,session=SESSION.date(),tick_size=tick,
                atr_column=f"atr{cfg.atr_period}")
            ten.extend(found)
            counts=" ".join(
                f"{kind}={sum(t.kind==kind for t in found)}"
                for kind in D1_REACTION_KINDS)
            print(f"QWCT 3.9 ALL TEN D1 REACTIONS {ticker} {e.label} "
                  + counts + " HEURISTIC_NOT_GERCHIK_APPROVAL NO_ORDERS")
        taxonomy_marks=chart_taxonomy_markers(d1,ten)
        hypotheses=discover_bsu_price_candidates(
            d1,session=SESSION.date(),swing_k=cfg.swing_k,
            tick_size=tick,atr_column=f"atr{cfg.atr_period}")
        print("QWCT 4.0 BSU SOURCES",ticker,len(hypotheses))
        for h in sorted(hypotheses,key=lambda x:
                        abs(x.price-case["cluster"]))[:12]:
            print("QWCT 4.0 RAW",ticker,h.origin,h.role,h.field,
                  h.price,h.source_date,h.known_on,h.native_grid,
                  len(h.exact_d1_revisits),"AUTHOR_UNVERIFIED")
        bs=audit_author_bsu_labels(
            hypotheses,tuple(AUTHOR_BSU_MARKUPS.get(ticker,())),
            ticker=ticker,session=SESSION.date(),tick_size=tick)
        rs=audit_author_reaction_labels(
            tuple(ten),tuple(AUTHOR_REACTION_MARKUPS.get(ticker,())),
            ticker=ticker,session=SESSION.date(),tick_size=tick)
        print("QWCT 4.0 MANUAL CHART AUDIT",ticker,bs.status,rs.status,
              bs.matches,rs.matches,"ACCURACY_UNKNOWN NO_ORDERS")
        plot_d1_evidence(case,d1,prices,breach,retest,markers,taxonomy_marks)
        print(f"QWCT 3.3 MANUAL LABEL {ticker} "
              "author_BSU_price=UNKNOWN price_reference=UNKNOWN "
              "fixed_or_floating=UNKNOWN author_graph_label=UNVERIFIED "
              "status=INDETERMINATE; NO_ORDERS")
    except Exception as exc:
        print(f"QWCT 3.3 ERROR {ticker}: {type(exc).__name__}: {exc}; "
              "FAIL CLOSED / NO SOURCE CONFIRMATION")
