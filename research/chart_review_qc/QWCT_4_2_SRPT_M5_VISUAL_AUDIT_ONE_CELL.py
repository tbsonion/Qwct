# QWCT 4.3 — SRPT RAW M5 source integrity + BPU2 luft audit.
# Historical filename retained so the same GitHub link stays valid.
# Paste ALL the code into ONE NEW code cell in QuantConnect research.ipynb.
# Shows raw M5 candles, wick geometry and event source/confirmation.
# Read-only: no broker, no orders, no retroactive source selection.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from strategy.config import StrategyConfig
from strategy.levels import levels_for_session
from strategy.patterns_bsu import Bar, BsuDetector, M5BsuSequenceScanner

ET = ZoneInfo("America/New_York")
DAY = datetime(2024, 6, 3)
SESSION = DAY.date()
cfg = StrategyConfig()
qb = QuantBook()
qb.set_time_zone("America/New_York")
qb.set_start_date(2024, 7, 1)
qb.set_end_date(2024, 7, 2)

def et(value):
    value=pd.Timestamp(value)
    return value.tz_localize(ET) if value.tzinfo is None else value.tz_convert(ET)

symbol = qb.add_equity(
    "SRPT", Resolution.MINUTE, fill_forward=False,
    data_normalization_mode=DataNormalizationMode.RAW).symbol
daily = list(qb.history[TradeBar](
    symbol, DAY-timedelta(days=335), DAY, Resolution.DAILY,
    fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW))
daily = [b for b in daily if et(b.time).date()<SESSION and
         not getattr(b,"is_fill_forward",False)]
if len(daily)<180:
    raise ValueError(f"FAIL_CLOSED: only {len(daily)} historical D1")
daily=daily[-180:]
atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
rows=[]
for b in daily:
    atr.update(b)
    rows.append({"date":et(b.time),"open":float(b.open),
                 "high":float(b.high),"low":float(b.low),
                 "close":float(b.close),"volume":float(b.volume),
                 f"atr{cfg.atr_period}":
                     float(atr.current.value) if atr.is_ready else float("nan")})
frame=pd.DataFrame(rows).set_index("date")
levels=levels_for_session(frame,SESSION,cfg)
tick=float(qb.securities[symbol].symbol_properties.minimum_price_variation)
scan=M5BsuSequenceScanner(cfg,session=SESSION,d1_levels=levels,
                          d1_atr=float(atr.current.value),
                          previous_d1_close=float(frame.close.iloc[-1]),
                          tick_size=tick)
minute=list(qb.history[TradeBar](
    symbol,DAY.replace(hour=9,minute=30),DAY.replace(hour=16,minute=0),
    Resolution.MINUTE,fill_forward=False,
    data_normalization_mode=DataNormalizationMode.RAW))
minutes=set()
m5=[]
def closed(sender,b):
    stamp=et(b.end_time)
    if stamp.date()!=SESSION or not time(9,35)<=stamp.time()<=time(16,0):
        return
    if float(b.volume)<=0 or any(
            stamp-timedelta(minutes=j) not in minutes for j in range(5)):
        return
    m5.append(Bar(stamp.to_pydatetime(),float(b.open),float(b.high),
                  float(b.low),float(b.close),timeframe="M5",
                  volume=float(b.volume)))
cons=TradeBarConsolidator(timedelta(minutes=5))
cons.data_consolidated+=closed
for b in minute:
    if not getattr(b,"is_fill_forward",False):
        minutes.add(et(b.end_time))
        cons.update(b)
# Only flush a REAL five-minute buffered bar, never create synthetic OHLC.
cons.scan(DAY.replace(hour=16,minute=1))


def audit_bpu2_luft(source, bpu1, bpu2, price, side, atr_value, tick_size, cfg):
    """Re-check completed M5 BPU1/BPU2, never mistake it for SEC TVX.

    Stop and luft come from the SAME StrategyConfig and observed D1 ATR as
    the native scanner. Independently verify the geometry and chronology
    before agreeing with the BsuDetector state. Does not validate BSU origin
    or any author-defined pattern (that is checked separately).
    """
    if not (source.ts < bpu1.ts < bpu2.ts):
        raise ValueError("BPU_CHRONOLOGY_INVALID")
    d = BsuDetector(cfg, price, side, atr_value=atr_value,
                    tick_size=tick_size, bsu_ts=source.ts)
    first = d.on_bar(bpu1)
    if first.phase != "bpu1":
        raise ValueError("BPU1_NOT_EXACT_IN_LUFT_AUDIT")
    final = d.on_bar(bpu2)
    tol = tick_size * (0.5 + 1e-7)
    extreme = float(bpu2.low if side == "long" else bpu2.high)
    signed_offset = (extreme - price if side == "long"
                     else price - extreme)
    pierces = (bpu2.low < bpu1.low - tol if side == "long"
               else bpu2.high > bpu1.high + tol)
    beyond_luft = signed_offset > final.luft + tol
    next_m5 = bpu2.ts - bpu1.ts == timedelta(minutes=5)
    geometry_pass = next_m5 and not pierces and not beyond_luft
    detector_pass = final.phase == "bpu2_confirmed"
    if geometry_pass != detector_pass:
        raise ValueError("BPU2_DETECTOR_GEOMETRY_MISMATCH")
    return {
        "passed": detector_pass, "stop": float(final.stop_price),
        "luft": float(final.luft), "extreme": extreme,
        "signed_offset": signed_offset, "tolerance": tol,
        "pierced_bpu1": pierces, "beyond_luft": beyond_luft,
        "next_m5": next_m5, "phase": final.phase,
    }

evidence=[]
for b in m5:
    evidence.extend(scan.observe(b))
completed=[e for e in evidence if e.event=="BPU2_CLOSED"]
by_end={et(b.ts):b for b in m5}
expected=((123.51,"12:35","13:40","13:45"),
          (123.87,"14:15","14:35","14:40"))
fmt=lambda t: et(t).strftime("%H:%M")
fig=make_subplots(rows=2,cols=1,shared_xaxes=False,
                  vertical_spacing=0.17,
                  subplot_titles=("SRPT $123.51 | source 12:35 → BPU1 13:40 → BPU2 13:45",
                                  "SRPT $123.87 | source 14:15 → BPU1 14:35 → BPU2 14:40"))
for row,(price,bsu,bpu1,bpu2) in enumerate(expected,start=1):
    match=[e for e in completed
           if abs(e.level_price-price)<tick/2 and
           (fmt(e.source_end),fmt(e.bpu1_end),fmt(e.bpu2_end))==
           (bsu,bpu1,bpu2)]
    print("QWCT 4.2 SRPT",price,"EXACT_CHRONOLOGY",
          "FOUND" if len(match)==1 else "MISSING_OR_AMBIGUOUS",
          "matches",len(match),"NO_AUTHOR_APPROVAL")
    if len(match)>1:
        raise ValueError("AMBIGUOUS_EVIDENCE")
    at=lambda h: et(DAY.replace(hour=int(h[:2]),minute=int(h[3:])))
    ts=[at(t) for t in (bsu,bpu1,bpu2)]
    actual=[by_end.get(t) for t in ts]
    if any(x is None for x in actual):
        raise ValueError("MISSING_RECORDED_CANDLE")
    # Infer the actual BSU-facing side from the TWO original RAW M5
    # extrema; do not assume lows on a hypothetical resistance case.
    sides=[
        side for side,field in (("long","low"),("short","high"))
        if all(abs(float(getattr(x,field))-price)<=tick/2+tick*1e-7
               for x in actual[:2])
    ]
    if len(sides)!=1:
        raise ValueError("M5_SOURCE_ROLE_UNKNOWN_OR_AMBIGUOUS")
    side=sides[0]
    if match and match[0].side!=side:
        raise ValueError("RESEARCH_ROLE_DOES_NOT_MATCH_NATIVE_BARS")
    prior=[x for x in m5 if ts[0]<et(x.ts)<ts[1]]
    gaps=[t for t in pd.date_range(ts[0]+timedelta(minutes=5),
          ts[1]-timedelta(minutes=5),freq="5min") if t not in by_end]
    pierced=[x for x in prior
             if (x.low<price-tick/2 if side=="long"
                 else x.high>price+tick/2)]
    rejected=bool(gaps or pierced)
    if rejected and match:
        raise ValueError("CONTRADICTORY_SOURCE_STATUS")
    if rejected:
        # A broken provenance is NOT rescued by a plausible BPU2 luft.
        status = "REJECTED_SOURCE"
        print("QWCT 4.3 LUFT AUDIT", price,
              "SKIPPED_SOURCE_INVALID NOT_SEC_TVX")
    else:
        outcome = audit_bpu2_luft(
            actual[0], actual[1], actual[2], price, side,
            float(atr.current.value), tick, cfg)
        if outcome["passed"] != (len(match) == 1):
            raise ValueError("SCANNER_VS_BPU2_LUFT_MISMATCH")
        status = ("PASSES_SOFTWARE" if outcome["passed"]
                  else "REJECTED_BPU2_GEOMETRY")
        print("QWCT 4.3 LUFT AUDIT", price,
              f"STOP={outcome['stop']:.4f}",
              f"LUFT={outcome['luft']:.4f}",
              f"BPU2_EXTREME={outcome['extreme']:.4f}",
              f"SIGNED_OFFSET={outcome['signed_offset']:.4f}",
              f"TOL={outcome['tolerance']:.5f}",
              f"WITHIN_LUFT={not outcome['beyond_luft']}",
              f"NEXT_M5={outcome['next_m5']}",
              f"BPU1_UNBROKEN={not outcome['pierced_bpu1']}",
              f"PASS={outcome['passed']}",
              "NO_PRE_CLOSE_SEC_TVX AUTHOR_UNVERIFIED NO_ORDERS")
    print("QWCT 4.3",price,status,
          "SIDE=",side,
          "prior_pierces=",[(fmt(x.ts),x.low if side=="long" else x.high)
                           for x in pierced[:8]],
          "missing_M5=",[fmt(t) for t in gaps],"NO_AUTHOR_APPROVAL")
    for label,x in zip(("source","retouch","next_bar"),actual):
        print("SRPT",price,label,fmt(x.ts),
              "O",x.open,"H",x.high,"L",x.low,"C",x.close)
    start=ts[0]-timedelta(minutes=35)
    stop=ts[2]+timedelta(minutes=30)
    bars=[x for x in m5 if start<=et(x.ts)<=stop]
    fig.add_trace(go.Candlestick(
        x=[et(b.ts) for b in bars],open=[b.open for b in bars],
        high=[b.high for b in bars],low=[b.low for b in bars],
        close=[b.close for b in bars],
        name="RAW M5 OHLC",showlegend=(row==1)),row=row,col=1)
    fig.add_hline(y=price,line_width=1.6,line_color="blue",
                  annotation_text=f"M5 source RAW {price:.2f}",row=row,col=1)
    for stage,b,color,symbol in zip(
        ("SOURCE CANDIDATE", "RETOUCH", "FOLLOWING BAR"),actual,
        ("#c43d39","#f29d24","#258c51"),("diamond","star","triangle-up")):
        y=b.low if side=="long" else b.high
        fig.add_trace(go.Scatter(
            x=[et(b.ts)],y=[y],mode="markers",
            marker=dict(size=13,color=color,symbol=symbol),
            name=stage,showlegend=(row==1),
            hovertemplate=(f"{stage} @ {fmt(b.ts)}<br>"
                f"O={b.open:.4f} H={b.high:.4f} "
                f"L={b.low:.4f} C={b.close:.4f}<br>"
                f"{status}; NOT AUTHOR VERIFIED; NOT SEC TVX<extra></extra>")
        ),row=row,col=1)
fig.update_xaxes(rangeslider_visible=False)
fig.update_layout(
    width=1180,height=870,margin=dict(t=90,b=45,l=65,r=130),
    title="QWCT 4.3 | SRPT broken vs surviving RAW M5 source; NO ORDERS",
    xaxis_type="date",xaxis2_type="date",hovermode="closest")
fig.show()
if len(completed) != scan.completed:
    raise ValueError("NATIVE_BPU2_COUNT_MISMATCH")
print("QWCT 4.3 SRPT native_M5=",len(m5),"BPU1=",scan.bpu1_count,
      "BPU2=",scan.completed,"AUTHOR_BSU=UNKNOWN NO_ORDERS")
