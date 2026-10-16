"""Closed-D1 QWCT 3.9 ten-reaction research; never certifies BSU or trades."""
from dataclasses import replace
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.levels import (
    BsuSourceEvidence, D1_REACTION_KINDS, ReactionHeuristics,
    _d1_wick_reaction, observe_d1_level_reactions,
)

ET=ZoneInfo("America/New_York")


def _fixture(mirror_resistance=False):
    idx=pd.date_range("2024-04-01",periods=30,freq="B",tz=ET)
    rows=[dict(open=102.,high=104.,low=101.,close=102.,atr14=5.)
          for _ in idx]
    rows[3].update(open=102.,high=103.,low=99.,close=102.)
    rows[5].update(open=101.,high=104.,low=98.5,close=101.5)
    rows[6].update(open=102.,high=104.,low=101.5,close=103.)
    rows[10].update(open=102.,high=103.,low=97.,close=98.)
    rows[11].update(open=98.,high=103.,low=97.,close=102.)
    rows[14].update(open=102.,high=103.,low=101.,close=102.)
    rows[15].update(open=102.,high=103.,low=98.,close=99.)
    rows[16].update(open=99.,high=100.,low=96.,close=97.)
    rows[18].update(open=103.,high=105.,low=100.1,close=103.)
    rows[19].update(open=102.,high=103.8,low=100.1,close=102.)
    rows[20].update(open=101.4,high=102.6,low=100.1,close=101.4)
    rows[21].update(open=100.9,high=101.4,low=100.1,close=100.9)
    for i,close in zip(range(22,28),(101.,99.,101.,99.,101.,99.)):
        rows[i].update(open=100.,high=102.,low=98.,close=close)
    d1=pd.DataFrame(rows,index=idx)
    original="resistance"
    if mirror_resistance:
        orig=d1[["open","high","low","close"]].copy()
        d1["open"]=200.-orig["open"]
        d1["high"]=200.-orig["low"]
        d1["low"]=200.-orig["high"]
        d1["close"]=200.-orig["close"]
        original="support"
    trace=dict(status="PROXY_VERIFIED",original_kind=original,
               valid_from=str(idx[4].date()),retest=str(idx[3].date()))
    role="resistance" if mirror_resistance else "support"
    wick=_d1_wick_reaction(d1.iloc[5],100.,.01,role,idx[5].date(),5.,True)
    assert wick is not None and wick.event=="TAIL_ONLY_RECLAIM"
    e=BsuSourceEvidence(
        label="FIRST_SWING",source_date=idx[0].date(),
        confirmed_date=idx[2].date(),price=100.,current_grid="ON_GRID",
        original_same_wick_dates=(),mirror_exact_wick_dates=(),
        mirror_pierce_dates=(),wick_reactions=(wick,),
        mirror_two_bar_reclaim_dates=(idx[11].date(),))
    return idx,d1,e,trace


def _run(d1,e,trace,**kwargs):
    args=dict(session=date(2024,5,31),tick_size=.01,atr_column="atr14")
    args.update(kwargs)
    return observe_d1_level_reactions(d1,e,trace,**args)


@pytest.mark.parametrize("inverted",[False,True])
def test_all_ten_reactions_emerge_in_one_causal_frozen_d1_case(inverted):
    idx,d1,e,trace=_fixture(inverted)
    out=_run(d1,e,trace)
    by={kind:[x for x in out if x.kind==kind] for kind in D1_REACTION_KINDS}
    assert len(D1_REACTION_KINDS)==10
    assert all(by.values()),{k:len(v) for k,v in by.items()}
    assert any(x.observed_on==idx[6].date() and x.anchor_on==idx[5].date()
               for x in by["BOUNCE"])
    assert any(x.observed_on==idx[6].date() for x in by["WICK_BOUNCE"])
    assert any(x.observed_on==idx[5].date() for x in by["WICK_RECLAIM"])
    assert any(x.observed_on==idx[5].date() for x in by["FALSE_BREAK_1BAR"])
    assert any(x.observed_on==idx[11].date() and x.anchor_on==idx[10].date()
               for x in by["FALSE_BREAK_2BAR"])
    assert any(x.observed_on==idx[16].date() for x in by["BREAK_FOLLOWTHROUGH"])
    assert any(x.observed_on==idx[3].date() and x.phase=="MIRROR_TRANSITION"
               for x in by["MIRROR_RETEST"])
    assert any(x.observed_on==idx[21].date() for x in by["COMPRESSION"])
    assert any(x.observed_on==idx[26].date() for x in by["CONSOLIDATION"])
    assert any(x.observed_on==idx[27].date() for x in by["CHOP"])
    assert all(not x.can_trade for x in out)
    assert all(x.observed_on >= x.anchor_on for x in out)
    assert all(x.observed_on < date(2024,5,31) for x in out)
    assert all(x.basis!="GERCHIK_CERTIFIED" for x in out)


def test_two_closes_not_the_same_as_verified_true_break():
    idx,d1,e,trace=_fixture()
    out=_run(d1,e,trace)
    events=[x for x in out if x.kind=="BREAK_FOLLOWTHROUGH"]
    assert any(x.observed_on==idx[16].date()
               and x.basis=="TWO_BEYOND_CLOSES_NOT_PERMANENT_BREAK"
               for x in events)
    assert not any(x.observed_on==idx[15].date() for x in events)


def test_bounce_requires_later_closed_d1_reaction_and_not_same_bar():
    idx,d1,e,trace=_fixture()
    out=_run(d1,e,trace)
    assert not any(x.kind=="BOUNCE" and x.observed_on==idx[5].date() for x in out)
    d1.loc[idx[6],"close"]=101.0
    assert not any(x.kind=="BOUNCE" and x.anchor_on==idx[5].date()
                   for x in _run(d1,e,trace))


def test_compression_chop_consolidation_are_separate_research_proxies():
    idx,d1,e,trace=_fixture()
    out=_run(d1,e,trace)
    assert any(x.kind=="COMPRESSION" and x.observed_on==idx[21].date()
               for x in out)
    d1.loc[idx[21],"high"]=112.
    out=_run(d1,e,trace)
    assert not any(x.kind=="COMPRESSION" and x.observed_on==idx[21].date()
                   for x in out)
    d1.loc[idx[21],"high"]=101.4
    d1.loc[idx[25],"high"]=115.
    out=_run(d1,e,trace)
    assert not any(x.kind=="CONSOLIDATION" and x.observed_on==idx[26].date()
                   for x in out)
    assert not any(x.kind=="CHOP" and x.observed_on==idx[27].date()
                   for x in out)


def test_asof_and_closed_candle_source_validation_fail_closed():
    idx,d1,e,trace=_fixture()
    with pytest.raises(ValueError,match="NONCAUSAL_REACTION_DATE"):
        _run(d1,e,trace,session=idx[-1].date())
    e2=replace(e,status="APPROVED")
    with pytest.raises(ValueError,match="REACTION_SOURCE_UNVERIFIED"):
        _run(d1,e2,trace)
    e2=replace(e,mirror_two_bar_reclaim_dates=(date(2024,5,30),))
    with pytest.raises(ValueError,match="NONCAUSAL_REACTION_TWO_BAR"):
        _run(d1,e2,trace)
    d1.loc[idx[5],"low"]=100.1
    with pytest.raises(ValueError,match="STALE_REACTION_WICK_OR_BAR"):
        _run(d1,e,trace)


def test_asof_mirror_role_transition_not_spanned():
    idx,d1,e,trace=_fixture()
    # The one-bar interaction is on the new support side after valid_from;
    # moving the role date into the future must not let it be reused.
    trace2=dict(trace,valid_from=str(idx[8].date()))
    with pytest.raises(ValueError,match="REACTION_ROLE_MISMATCH"):
        _run(d1,e,trace2)


def test_missing_native_atr_and_invalid_heuristics_not_silent():
    idx,d1,e,trace=_fixture()
    d1.loc[idx[21],"atr14"]=float("nan")
    out=_run(d1,e,trace)
    assert not any(x.kind=="COMPRESSION" and x.observed_on==idx[21].date()
                   for x in out)
    d1.loc[idx[21],"atr14"]=0.
    with pytest.raises(ValueError,match="INVALID_NATIVE_REACTION_ATR"):
        _run(d1,e,trace)
    with pytest.raises(ValueError,match="INVALID_REACTION_WINDOW"):
        _run(d1,e,trace,heuristics=ReactionHeuristics(chop_bars=3))
    with pytest.raises(ValueError,match="INVALID_REACTION_HEURISTIC"):
        _run(d1,e,trace,heuristics=ReactionHeuristics(proximity_atr=-1))


def test_future_bar_cannot_shift_existing_reaction_into_past():
    idx,d1,e,trace=_fixture()
    old=_run(d1.iloc[:23].copy(),e,trace)
    extended=_run(d1,e,trace)
    cutoff=idx[22].date()
    assert tuple(x for x in extended if x.observed_on<=cutoff)==old


def test_no_orders_portfolio_or_live_broker_in_taxonomy():
    from pathlib import Path
    txt=(Path(__file__).resolve().parents[1]/"strategy"/"levels.py").read_text(
        encoding="utf-8").split("# QWCT 3.9",1)[1]
    for forbidden in ("market_order(", "limit_order(", "set_holdings(",
                      "place_order(", "qb.history(", "np.median("):
        assert forbidden not in txt
