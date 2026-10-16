"""QWCT 3.2 D1-only source/basis census: pure deterministic guards.

AST-extract the implemented native_source_audit for unit tests without
falsely running QuantConnect Cloud LEAN. No broker mocks or signals.
"""
import ast
from datetime import timedelta
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
NEW=ROOT/"research"/"source_census_cloud"/"main.py"
BASE=ROOT/"research"/"mirror_census_cloud"/"main.py"
ET=ZoneInfo("America/New_York")


def code_ast(path,name):
    root=ast.parse(path.read_text(encoding="utf8"))
    for node in root.body:
        if isinstance(node,ast.FunctionDef) and node.name==name:
            return node
        if isinstance(node,ast.ClassDef):
            for sub in node.body:
                if isinstance(sub,ast.FunctionDef) and sub.name==name:
                    return sub
    raise AssertionError(f"missing {name}: {path}")


def source_function():
    node=code_ast(NEW,"native_source_audit")
    space={"isfinite":isfinite,"et":lambda t:pd.Timestamp(t).tz_localize(ET)
           if pd.Timestamp(t).tzinfo is None else
           pd.Timestamp(t).tz_convert(ET)}
    # Only a faked confirmed-swing metadata provider in a PURE unit test;
    # no assertion that native historical pivot computation passed.
    space["_confirmed_swings"]=lambda d,k:(
        [(2,105.0,d.index[3].date()),(5,105.1,d.index[6].date())],[])
    exec(compile(ast.Module(body=[node],type_ignores=[]),
                 str(NEW),"exec"),space)
    return space["native_source_audit"]


def records(raw_origin=105.0, scaled_source=105.0, scaled_latest=102.0):
    dates=pd.date_range("2024-05-01",periods=10,freq="D",tz=ET)
    raw_close=102.0
    d1=pd.DataFrame(
        [{"high":100.0,"low":90.0,"close":raw_close,
          "bar_end":at+timedelta(days=1)} for at in dates],
        index=dates)
    d1.loc[dates[2],"high"]=raw_origin
    mirror=SimpleNamespace(
        first_idx=2,last_idx=5,price=105.25,
        formed_at=dates[5].date(),valid_from=dates[7].date())
    proof={"original_kind":"resistance","status":"PROXY_VERIFIED",
           "source":str(dates[2].date())}
    scaled=[SimpleNamespace(time=at,end_time=at+timedelta(days=1),
            high=(scaled_source if i==2 else 100.0),
            low=90.0,close=(scaled_latest if i==9 else 101.0),
            is_fill_forward=False) for i,at in enumerate(dates)]
    cfg=SimpleNamespace(swing_k=1)
    return d1,mirror,proof,scaled,cfg


def test_original_source_grid_and_scaled_match():
    fn=source_function()
    out=fn(*records()[:3],records()[3],0.01,records()[4])
    assert out["status"]=="RAW_SOURCE_CONFIRMED"
    assert out["basis"]=="MATCH" and out["raw_grid"]=="ON_GRID"
    assert out["field"]=="high" and out["origin_day"]=="2024-05-03"
    assert abs(out["median_ticks"]-25)<0.001
    assert out["source_key"]


def test_source_off_native_grid_and_rebased_are_distinct_flags():
    fn=source_function()
    d1,l,p,scaled,cfg=records(raw_origin=105.005,scaled_source=104.9)
    out=fn(d1,l,p,scaled,0.01,cfg)
    assert out["raw_grid"]=="OFF_GRID"
    assert out["basis"]=="REBASED_SOURCE_HISTORY"
    assert out["status"]=="RAW_SOURCE_CONFIRMED"


def test_scaled_history_fail_closed_no_original_source_invention():
    fn=source_function()
    d1,l,p,scaled,cfg=records()
    out=fn(d1,l,p,None,0.01,cfg)
    assert out["status"]=="RAW_SOURCE_CONFIRMED"
    assert out["basis"]=="UNKNOWN_SCALED_HISTORY"
    assert out["raw_grid"]=="ON_GRID"
    assert fn(d1,l,p,scaled,0.0,cfg)["status"]=="NATIVE_TICK_UNKNOWN"
    assert fn(d1,l,p,scaled,0.0,cfg)["basis"]=="UNKNOWN"
    out=fn(d1,l,p,scaled[:-1],0.01,cfg)
    assert out["basis"]=="UNKNOWN_ORIGIN_OR_LATEST_MISSING"
    scaled[2].end_time+=timedelta(minutes=1)
    out=fn(d1,l,p,scaled,0.01,cfg)
    assert out["basis"]=="UNKNOWN_ENDTIME_MISMATCH"


def test_latest_close_basis_discrepancy_overrides_source_match():
    fn=source_function()
    d1,l,p,scaled,cfg=records(scaled_latest=101.5)
    out=fn(d1,l,p,scaled,0.01,cfg)
    assert out["basis"]=="LATEST_CLOSE_DIFFERENCE"


def test_original_confirmed_swing_and_causal_validation_mandatory():
    fn=source_function()
    d1,l,p,scaled,cfg=records()
    p["status"]="UNKNOWN"
    assert fn(d1,l,p,scaled,0.01,cfg)["status"]=="CAUSAL_MIRROR_PROOF_UNVERIFIED"
    p["status"]="PROXY_VERIFIED"
    p["source"]="2024-01-01"
    assert fn(d1,l,p,scaled,0.01,cfg)["status"]=="SOURCE_NOT_CONFIRMED_IN_NATIVE_D1"
    p["source"]="2024-05-03"
    l.last_idx=9
    assert fn(d1,l,p,scaled,0.01,cfg)["status"]=="INVALID_CONFIRMED_SOURCE_INDICES"


def test_same_native_pit_membership_and_morning_gates_no_m1_order_logic():
    for name in ("audit_mirror","mirror_gates","et","_select",
                 "_daily_history","_native_frame"):
        assert ast.dump(code_ast(NEW,name))==ast.dump(code_ast(BASE,name)),name
    code=NEW.read_text(encoding="utf8")
    ast.parse(code)
    assert len(code.encode("utf8"))<32000
    assert "self.get_parameter(\"scan_start\") or \"2024-06-01\"" in code
    assert "self.get_parameter(\"scan_end\") or \"2024-06-30\"" in code
    assert "next_session_fundamentals(" in code
    assert "freeze_fundamental_event(" in code
    assert "self.callback_at[day]>et(self.time)" in code
    assert "self.history[TradeBar](" in code
    assert "data_normalization_mode=DataNormalizationMode.SCALED_RAW" in code
    assert "self._scaled_daily_history(list(ready_frames),day)" in code
    assert 'ready_records.append((sym,lvl,proof,gates))' in code
    assert "self.source_records+=1" in code
    assert 'seen==self.source_count[\'status_RAW_SOURCE_CONFIRMED\']' in code
    assert "self.source_records==self.count['mirror_ready']" in code
    assert "QWCT 3.2 SOURCE SUMMARY" in code
    assert "QWCT 3.2 SAMPLE" in code
    assert "QWCT 3.2 SOURCE RECORD" not in code
    assert "self.source_samples={}" in code
    assert 'if len(samples)<2:' in code
    assert "for row in self.near_examples:" not in code
    assert "for row in self.ready_examples[:50]:" not in code
    assert "individual_records_suppressed_due_to_10KB_LOG_LIMIT" in code
    assert "distinct_source_lineages=" in code
    assert "median_drift_lineages=" in code
    assert "float(lvl.price)" in code
    assert "actual M5" not in code
    for banned in ("Resolution.SECOND","Resolution.TICK",
                   "TradeBarConsolidator(", "Resolution.MINUTE,fill_forward=False,extended",
                   "self.market_order(", "self.limit_order(", "self.stop_market_order(",
                   "self.set_holdings(", "self.liquidate(", "self.buy(", "self.sell("):
        assert banned not in code,banned
