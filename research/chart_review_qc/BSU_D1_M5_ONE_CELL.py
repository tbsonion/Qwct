# QWCT 2.9 — SINGLE-CELL QuantConnect Research (AON and DELL)
# Replace the default SPY / BollingerBands demo cell with ALL of this file.
# Original price evidence from actual QWCT 2.8 2024-06 backtest; NO ORDERS.
# Mirror source validation is available later in the full .ipynb notebook.

# QuantConnect Cloud Research Notebook — not a trading algorithm
# 2024-06 real QC history; displays true native RAW data only in QuantConnect.
from datetime import datetime, timedelta, time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from QuantConnect.Research import QuantBook
from QuantConnect import Resolution, DataNormalizationMode

# Prior verified June 2.8 original swing-proxy evidence, never a manual BSU label.
CASES = [
    dict(ticker="AON", day="2024-06-12", src="2024-05-10", side="short",
         raw=293.5900, cluster=293.8175, first="09:35", n_cross=2, basis="MATCH"),
    dict(ticker="DELL", day="2024-06-07", src="2024-05-14", side="long",
         raw=128.7500, cluster=128.6750, first="14:15", n_cross=7, basis="MATCH"),
    dict(ticker="CRM", day="2024-06-27", src="2024-06-06", side="short",
         raw=246.7500, cluster=246.0550, first="09:40", n_cross=1, basis="MATCH"),
    dict(ticker="ABT", day="2024-06-07", src="2023-12-04", side="short",
         raw=105.5000, cluster=105.3150, first="10:20", n_cross=1, basis="REBASED"),
]
CASE_CHOICE = ["AON", "DELL"]  # Change to ["AON","DELL","CRM","ABT"] to inspect all.
qb = QuantBook()
# Research history requests cannot fetch dates AFTER qb start/time.
# Keep QuantBook as-of July 1 2024 so June 2024 is historical.
qb.set_start_date(2024, 7, 1)
qb.set_end_date(2024, 7, 2)
qb.set_time_zone("America/New_York")
assets = {
    t: qb.add_equity(t, Resolution.MINUTE, fill_forward=False,
                     data_normalization_mode=DataNormalizationMode.RAW).symbol
    for t in [c["ticker"] for c in CASES]
}
print("READ-ONLY RAW equity research. Original evidence: QWCT native run "
      "4b787847b9e5d2405b2fd97a541fa71e.")
print("No market orders, no levels chosen from future D1, no TVX inference.")


def one_symbol(frame):
    """QuantBook returns a pandas DataFrame, often Symbol x EndTime."""
    if frame is None or frame.empty:
        raise ValueError("Native RAW History returned no candles")
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.droplevel(0)
    return frame.sort_index().copy()

def et_index(frame):
    idx = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York")
    else:
        idx = idx.tz_convert("America/New_York")
    frame = frame.copy()
    frame.index = idx
    if not frame.index.is_unique:
        raise ValueError("Duplicate Native TradeBar EndTime")
    return frame

def native_raw_windows(case):
    symbol = assets[case["ticker"]]
    target = datetime.strptime(case["day"], "%Y-%m-%d")
    source = datetime.strptime(case["src"], "%Y-%m-%d")
    # D1 end strictly before session; the day being reviewed is never a D1 input.
    d = one_symbol(qb.history(
        symbol, target-timedelta(days=330), target.replace(hour=9,minute=29),
        Resolution.DAILY, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    d = et_index(d)
    if (d.index >= pd.Timestamp(target.replace(hour=9,minute=29),tz="America/New_York")).any():
        raise ValueError("Noncausal D1 history at or after morning decision")
    # A native daily bar often ends 00:00 the NEXT day; map back to its
    # actual session without consulting future prices.
    native_day = [
        ((x-timedelta(microseconds=1)).date() if x.time()==time(0,0)
         else x.date()) for x in d.index]
    d["session_day"] = pd.to_datetime(native_day)
    d = d.set_index("session_day", drop=True)
    d = d.loc[d.index < pd.Timestamp(target.date())].tail(180)
    if len(d)<180:
        raise ValueError("Fewer than 180 original closed daily bars; do not compare to cohort")
    if d.empty or pd.Timestamp(case["src"]) not in d.index:
        raise ValueError("D1 source missing in historical RAW data")
    m1 = one_symbol(qb.history(
        symbol, target.replace(hour=9,minute=30),
        target.replace(hour=16,minute=1),
        Resolution.MINUTE, fill_forward=False, extended_market_hours=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    m1 = et_index(m1)
    m1 = m1.loc[
        (m1.index.date == target.date()) &
        (m1.index.time > time(9,30)) & (m1.index.time <= time(16,0))]
    if not m1.index.is_monotonic_increasing or m1.empty:
        raise ValueError("Empty or unordered native RAW minute history")
    m5 = m1.resample("5min", closed="right", label="right").agg({
        "open":"first", "high":"max", "low":"min",
        "close":"last", "volume":"sum"})
    n_m1 = m1["close"].resample("5min", closed="right", label="right").count()
    m5["native_m1_count"] = n_m1
    m5 = m5.loc[
        (m5.index.date == target.date()) &
        (m5.index.time >= time(9,35)) & (m5.index.time <= time(16,0))]
    m5 = m5.dropna(subset=["open","high","low","close"])
    return d, m1, m5

def review_geometry(case, d, m1, m5):
    src = d.loc[pd.Timestamp(case["src"])]
    field = "high" if case["side"]=="short" else "low"
    actual_source = float(src[field])
    raw_ok = abs(actual_source-case["raw"]) <= 0.0001
    extrema = m5["high"] if case["side"]=="short" else m5["low"]
    # Same half-native-tick equality as research BsuDetector.
    tol = .005000001
    raw = case["raw"]
    exact = (extrema-raw).abs()<=tol
    short = extrema < raw-tol if case["side"]=="short" else extrema > raw+tol
    crossed = ~exact & ~short & (m5["low"]<=raw) & (m5["high"]>=raw)
    beyond = ~exact & ~short & ~crossed
    labels = pd.Series("BEYOND_NO_SPAN",index=m5.index)
    labels.loc[short]="SHORT_OF"
    labels.loc[crossed]="RANGE_CROSSED"
    labels.loc[exact]="EXACT_WICK"
    # For this case, the independently observed approved native detector
    # baseline required a particular number of range-crossing buckets.
    n_cross=int(crossed.sum())
    same_cross=n_cross == case["n_cross"]
    first_cross = m5.loc[crossed].index.min() if n_cross else None
    first_expected = (first_cross is not None and
                      first_cross.strftime("%H:%M")==case["first"])
    expected=pd.date_range(pd.Timestamp(case["day"]+" 09:35",tz="America/New_York"),
                           pd.Timestamp(case["day"]+" 16:00",tz="America/New_York"),
                           freq="5min")
    full_buckets=(m5["native_m1_count"]==5)
    incomplete=m5.loc[~full_buckets,"native_m1_count"]
    valid_counts=(m5.index.equals(expected) and full_buckets.all())
    if not incomplete.empty:
        print("INCOMPLETE M5 SOURCE MINUTE BUCKETS (ET):",
              [(t.strftime("%H:%M"),int(n)) for t,n in incomplete.items()])
        print("WARNING: Full 78-bar M5 SOURCE coverage is NOT verified; "
              "a missing minute bar need not mean a feed outage.")
    print("\n==",case["ticker"],case["day"],case["side"],"==")
    print("D1 original:",case["src"],"recorded:",raw,
          "native source:",actual_source,"MATCH" if raw_ok else "MISMATCH")
    print("Source-vs-cluster:",case["cluster"],"ticks:",
          round((case["cluster"]-raw)/.01,2),
          "source basis:",case["basis"])
    print("Real native M1:",len(m1),"derived 5m time buckets:",len(m5),
          "M5 with all five native M1:",int((m5["native_m1_count"]==5).sum()))
    print("Ranges: exact",int(exact.sum()),"short",int(short.sum()),
          "cross",n_cross,"beyond",int(beyond.sum()))
    print("Cross count vs June2.8 native:",same_cross,
          "first crossing:",str(first_cross),
          "first timestamp match:",first_expected,
          "ALL 78 M5 HAVE 5 ORIGINAL M1:",valid_counts)
    print("MANUAL BSU/TVX status: INDETERMINATE / UNVERIFIED.")
    if not raw_ok or not same_cross or not first_expected or not valid_counts:
        print("WARNING: SOURCE/GEOMETRY CHECK FAILED. Do not mark BSU; "
              "investigate native history timing/normalization.")
    cols=["open","high","low","close","native_m1_count"]
    if first_cross is not None:
        i = m5.index.get_loc(first_cross)
        print("First crossing and following TWO CLOSED M5 candles:")
        display(m5.iloc[max(0,i-1):min(len(m5),i+3)][cols].round(4))
    return labels, bool(raw_ok and same_cross and first_expected and valid_counts)

def show_charts(case, d, m5, labels, checked):
    fig=make_subplots(rows=2,cols=1,
        row_heights=[.44,.56],vertical_spacing=.13,
        subplot_titles=(
          "D1 RAW history AS-OF prior close (never sees the target day)",
          "M5 from current-day native RAW minute data, after close"))
    fig.add_trace(go.Candlestick(
        x=d.index,open=d["open"],high=d["high"],
        low=d["low"],close=d["close"],name="RAW D1"),
        row=1,col=1)
    fig.add_trace(go.Candlestick(
        x=m5.index,open=m5["open"],high=m5["high"],
        low=m5["low"],close=m5["close"],name="RAW M5 from M1"),
        row=2,col=1)
    for row in (1,2):
        fig.add_hline(y=case["raw"],line_color="red",line_width=2,
                      annotation_text="Original RAW pivot",row=row,col=1)
        fig.add_hline(y=case["cluster"],line_color="blue",line_dash="dash",
                      line_width=2,annotation_text="D1 swing median",row=row,col=1)
    if pd.Timestamp(case["src"]) in d.index:
        fig.add_trace(go.Scatter(
            x=[pd.Timestamp(case["src"])],y=[case["raw"]],
            mode="markers",marker=dict(size=12,color="red",symbol="diamond"),
            name="D1 first_idx origin"),row=1,col=1)
    crosses=m5.loc[labels=="RANGE_CROSSED"]
    if not crosses.empty:
        mids=(crosses["high"]+crosses["low"])/2
        fig.add_trace(go.Scatter(
            x=crosses.index,y=mids,mode="markers",
            marker=dict(size=12,color="orange",symbol="x"),
            name="M5 range straddled pivot ≠ BPU1"),row=2,col=1)
    incomplete=m5.loc[m5["native_m1_count"]<5]
    if not incomplete.empty:
        fig.add_trace(go.Scatter(
            x=incomplete.index,y=incomplete["close"],mode="markers",
            marker=dict(size=12,color="black",symbol="circle-open"),
            name="Missing source M1 in 5m bucket"),row=2,col=1)
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_layout(
        height=1000, width=1200,hovermode="x unified",
        title=(case["ticker"]+"  "+case["day"]+" / "
               +("RAW MATCHED" if checked else "CHECK FAILED — DO NOT LABEL")),
        legend=dict(orientation="h",y=1.09))
    fig.show()

for case in CASES:
    if case["ticker"] not in CASE_CHOICE:
        continue
    d,m1,m5=native_raw_windows(case)
    labels,checked=review_geometry(case,d,m1,m5)
    show_charts(case,d,m5,labels,checked)
