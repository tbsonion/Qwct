"""QWCT 3.3 source-price alternatives, D1-only author-evidence guards.

These pure tests do not claim QuantConnect native D1 history was rerun or
a particular Gerchik BSU/BPU1 manually approved.
"""
import ast
from datetime import timedelta
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd


ROOT=Path(__file__).resolve().parents[1]
ONE=ROOT/"research"/"chart_review_qc"/"GERCHIK_3_3_D1_LEVEL_EVIDENCE_ONE_CELL.py"
SPEC=ROOT/"research"/"chart_review_qc"/"QWCT_3_3_GERCHIK_BSU_SOURCE_DECISION_RU.md"
ET=ZoneInfo("America/New_York")


def review_funcs():
    tree=ast.parse(ONE.read_text(encoding="utf8"))
    names={"asof_d1_event","price_hypotheses"}
    body=[node for node in tree.body
          if isinstance(node,ast.FunctionDef) and node.name in names]
    assert {node.name for node in body}==names
    globs=dict(pd=pd,isfinite=isfinite,timedelta=timedelta,ET=ET)
    exec(compile(ast.Module(body=body,type_ignores=[]),str(ONE),"exec"),globs)
    return globs


def test_d1_role_retest_low_must_follow_new_support_not_rejected_trade_side(capsys):
    funcs=review_funcs()
    dates=pd.date_range("2024-05-01",periods=10,freq="D",tz=ET)
    rows=[{"open":102., "high":105., "low":99., "close":103.} for _ in dates]
    d1=pd.DataFrame(rows,index=dates)
    d1.iloc[1,d1.columns.get_loc("high")]=106.0
    d1.iloc[2,d1.columns.get_loc("high")]=105.5
    d1.iloc[5,d1.columns.get_loc("close")]=107.0
    d1.iloc[7,d1.columns.get_loc("low")]=103.5
    # Disqualified control's inferred trading side may be SHORT. This must
    # still plot the historical retest LOW when mirror old role=resistance.
    level=SimpleNamespace(first_idx=1,last_idx=2,price=105.75,
                           valid_from=dates[8].date())
    proof=dict(status="PROXY_VERIFIED",original_kind="resistance",
               breach=str(dates[5].date()),retest=str(dates[7].date()))
    prices,breach,retest=funcs["price_hypotheses"](
        d1,level,proof,"short",0.01)
    assert [p[0] for p in prices]==[
        "FIRST_SWING","LAST_SWING","CLUSTER_MEDIAN","D1_ROLE_RETEST"]
    assert prices[0][2]==106.0 and prices[0][3]=="high"
    assert prices[1][2]==105.5 and prices[1][3]=="high"
    assert prices[2][2]==105.75 and prices[2][3]=="software_only"
    assert prices[3][2]==103.5 and prices[3][3]=="low"
    assert "NOT_AUTHOR_BSU / NOT_BPU1" in capsys.readouterr().out


def test_support_to_resistance_retest_high():
    funcs=review_funcs()
    dates=pd.date_range("2024-05-01",periods=10,freq="D",tz=ET)
    d1=pd.DataFrame([{"open":101.,"high":102.,"low":99.,"close":100.}
                     for _ in dates],index=dates)
    d1.iloc[1,d1.columns.get_loc("low")]=98.5
    d1.iloc[2,d1.columns.get_loc("low")]=98.75
    d1.iloc[7,d1.columns.get_loc("high")]=100.25
    level=SimpleNamespace(first_idx=1,last_idx=2,price=99.0,
                          valid_from=dates[8].date())
    proof=dict(status="PROXY_VERIFIED",original_kind="support",
               breach=str(dates[5].date()),retest=str(dates[7].date()))
    prices,_,_=funcs["price_hypotheses"](d1,level,proof,"long",0.01)
    assert prices[0][3]=="low"
    assert prices[3][3]=="high" and prices[3][2]==100.25


def test_retest_must_precede_decision_and_be_on_same_asof_frame():
    funcs=review_funcs()
    dates=pd.date_range("2024-05-01",periods=10,freq="D",tz=ET)
    d1=pd.DataFrame([{"high":105.,"low":99.,"close":102.} for _ in dates],
                    index=dates)
    level=SimpleNamespace(first_idx=1,last_idx=2,price=101.0,
                          valid_from=dates[8].date())
    proof=dict(status="PROXY_VERIFIED",original_kind="resistance",
               breach=str(dates[5].date()),retest="2024-07-02")
    try:
        funcs["price_hypotheses"](d1,level,proof,"long",0.01)
    except ValueError as ex:
        assert "HISTORICAL_D1_EVENT_NOT_IN_ASOF_FRAME" in str(ex)
    else:
        raise AssertionError("Future retest must reject")


def test_predeclared_first_day_and_no_m1_second_pass_or_ordering():
    s=ONE.read_text(encoding="utf8")
    assert len(s.encode("utf8"))<32000
    ast.parse(s)
    assert "SESSION=datetime(2024,6,3)" in s
    for ticker,median in [
        ("AMAT","214.4600"),("NFLX","633.7750"),
        ("SRPT","125.0000"),("MSFT","415.5900")]:
        assert f'ticker="{ticker}",cluster={median}' in s
    assert 'decision="NEGATIVE_ROLE_CONTROL"' in s
    assert "Resolution.DAILY,fill_forward=False" in s
    assert "ticker,Resolution.DAILY,fill_forward=False" in s
    assert "qb.history[TradeBar](" in s
    assert "D1_180_ASOF_CHECK_FAILED" in s
    assert "MIRROR_COHORT_FREEZE_MISMATCH" in s
    assert "FROZEN_3_0_ELIGIBILITY_MISMATCH" in s
    for call in ("TradeBarConsolidator(", "Resolution.MINUTE",
                 "Resolution.SECOND","Resolution.TICK",
                 "qb.history[QuoteBar]", "self.market_order(",
                 "market_order(", "limit_order(", "stop_market_order(",
                 "set_holdings(", "ffill(", "resample("):
        assert call not in s,call


def test_author_grounding_and_no_auto_approval():
    s=SPEC.read_text(encoding="utf8")
    assert "gerchik.com/torgovye-patterny/bsu-bpu-teoriya" in s
    assert "gerchik.com/pdf/algoritm_forts.pdf" in s
    assert "studylib.net/doc/27688195" in s
    for k in ("FIRST_SWING","LAST_SWING","D1_RETEST","CLUSTER_MEDIAN",
              "INDETERMINATE","UNKNOWN","БПУ1"):
        assert k in s
    assert "manual_status=INDETERMINATE" in s
