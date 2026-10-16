"""QWCT 5.1 audit tests: independent native-shape M5 geometry, no labels."""
import ast
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from strategy.m5_reaction_taxonomy import M5TenReactionObserver

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"research/chart_review_qc/QWCT_5_1_REACTION_AUDIT_CORE.py"
CELL=ROOT/"research/chart_review_qc/QWCT_5_1_SRPT_M5_REACTION_VISUAL_AUDIT_ONE_CELL.py"
ET=ZoneInfo("America/New_York")
AT=datetime(2024,6,3,10,0,tzinfo=ET)


def audit_fn():
    s=AUDIT.read_text(encoding="utf-8")
    node=next(x for x in ast.parse(s).body if isinstance(x,ast.FunctionDef)
              and x.name=="audit_reaction_event")
    ns={"timedelta":timedelta,"isfinite":__import__("math").isfinite}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),
                 str(AUDIT),"exec"),ns)
    return ns["audit_reaction_event"]


def b(i,o,hi,lo,c):
    assert lo<=min(o,c)<=max(o,c)<=hi
    return SimpleNamespace(
        ts=AT+timedelta(minutes=5*i),timeframe="M5",
        open=o,high=hi,low=lo,close=c,volume=100.0)


def run(bars,atr=2.0,side="long"):
    ob=M5TenReactionObserver(100.,side,.01)
    d, a, events={}, {}, []
    fn=audit_fn()
    for bar in bars:
        d[bar.ts]=bar
        a[bar.ts]=atr
        current=ob.observe(bar, atr)
        for e in current:
            valid,reason=fn(e,d,a,level=100.,side=side,
                            tick=.01,h=ob.h)
            assert valid, (e.kind,e.bar_end,reason)
        events.extend(current)
    return {e.kind for e in events},events,d,a,ob


def test_reaction_bounce_wick_and_reclaim_geometries():
    tags,*_=run([
        b(0,100.5,100.6,99.8,100.3),
        b(1,100.35,100.9,100.15,100.7)])
    assert {"BOUNCE","WICK_BOUNCE"}<=tags
    tags,*_=run([b(0,100.2,100.6,99.7,100.1)])
    assert {"WICK_RECLAIM","FALSE_BREAK_1BAR"}<=tags
    tags,*_=run([b(0,99.5,100.5,99.0,100.2)])
    assert tags=={"WICK_RECLAIM"}


def test_reaction_two_bar_false_break_and_break_retest():
    tags,*_=run([
        b(0,100.2,100.4,100.05,100.2),
        b(1,100.1,100.2,99.5,99.7),
        b(2,99.9,100.4,99.7,100.2)])
    assert "FALSE_BREAK_2BAR" in tags
    tags,*_=run([
        b(0,100.2,100.4,100.05,100.2),
        b(1,100.1,100.2,99.5,99.8),
        b(2,99.8,99.9,99.5,99.6),
        b(3,99.6,100.1,99.3,99.7)])
    assert {"BREAK_FOLLOWTHROUGH","MIRROR_RETEST"}<=tags


def test_reaction_windows_recomputed_from_independent_bar_geometry():
    tags,*_=run([
        b(0,101.0,101.4,100.2,100.6),
        b(1,100.6,100.85,100.22,100.45),
        b(2,100.45,100.55,100.12,100.30),
        b(3,100.30,100.35,100.05,100.15)])
    assert "COMPRESSION" in tags
    tags,*_=run([
        b(i,100.05,100.30,99.85,100.10) for i in range(5)])
    assert "CONSOLIDATION" in tags
    tags,*_=run([
        b(i,100.0,100.4,99.6,v) for i,v in enumerate(
            (100.1,99.9,100.1,99.9,100.1,99.9))])
    assert "CHOP" in tags


def test_short_mirrored_wick_and_false_break():
    tags,*_=run([b(0,99.8,100.3,99.4,99.9)],side="short")
    assert {"WICK_RECLAIM","FALSE_BREAK_1BAR"}<=tags


def test_wrong_anchor_future_stale_reason_is_fail_closed():
    tags,ev,d,a,ob=run([
        b(0,100.2,100.4,100.05,100.2),
        b(1,100.1,100.2,99.5,99.7),
        b(2,99.9,100.4,99.7,100.2)])
    fn=audit_fn()
    e=next(e for e in ev if e.kind=="FALSE_BREAK_2BAR")
    assert not fn(replace(e,anchor_end=AT),d,a,level=100.,side="long",
                  tick=.01,h=ob.h)[0]
    assert not fn(replace(e,can_trade=True),d,a,level=100.,side="long",
                  tick=.01,h=ob.h)[0]
    assert not fn(replace(e,bar_end=AT+timedelta(minutes=55)),
                  d,a,level=100.,side="long",tick=.01,h=ob.h)[0]
    x=next(e for e in ev if e.kind=="WICK_RECLAIM")
    assert not fn(replace(x,reason="TAIL_ONLY_RECLAIM"),d,a,
                  level=100.,side="long",tick=.01,h=ob.h)[0]


def test_gap_never_reconnects_old_candle_provenance():
    bars=[
        b(0,100.2,100.4,100.05,100.2),
        b(1,100.1,100.2,99.5,99.8),
        b(3,99.8,99.9,99.5,99.6),
        b(4,99.6,100.1,99.3,99.7)]
    tags,*_=run(bars)
    assert "BREAK_FOLLOWTHROUGH" not in tags
    assert "MIRROR_RETEST" not in tags


def test_embedded_independent_auditor_is_identical_and_research_only():
    original=ast.parse(AUDIT.read_text(encoding="utf-8"))
    notebook=ast.parse(CELL.read_text(encoding="utf-8"))
    fn=lambda x: next(n for n in x.body if isinstance(n,ast.FunctionDef)
                      and n.name=="audit_reaction_event")
    assert ast.dump(fn(original))==ast.dump(fn(notebook))
    text=CELL.read_text(encoding="utf-8")
    assert "level=float(lvl.price)" in text
    assert "atr_by_end[end] = known_atr" in text
    assert "QWCT 5.1 AUDIT SUMMARY" in text
    assert "GERCHIK_GROUND_TRUTH_LABELS=0" in text
    assert "MECHANICAL_AUDIT_PASSED" in text
    assert "AUTHOR_REACTION_ACCURACY=UNKNOWN" in text
    assert "GAP_RESETS=" in text
    assert "TradeBarConsolidator(timedelta(minutes=5))" in text
    assert "NO_BROKER_NO_ORDERS" in text
    for forbid in ("market_order(", "limit_order(", "set_holdings(",
                   "submit_order(", "place_order(", "live_deploy("):
        assert forbid not in text.lower()
