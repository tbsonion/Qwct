"""QWCT 4.1: native RAW M5 source -> exact BPU1 -> BPU2.

Pure tests only: NOT proof of author-labelled BSU or actual LEAN feed.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest
from strategy.config import StrategyConfig
from strategy.patterns_bsu import Bar, M5BsuSequenceScanner

ET=ZoneInfo("America/New_York")
DAY=date(2026,10,16)
FIRST=datetime(2026,10,16,10,5,tzinfo=ET)


def level(price=100.03,kind="support",source="swing_cluster",confirmed=True):
    return SimpleNamespace(price=price,kind=kind,
        source=source,valid_from=DAY if confirmed else date(2026,10,17),
        touches=3,strength=3.)


def scanner(*,levels=None,at_close=101.,history_limit=80,max_pairs=24):
    return M5BsuSequenceScanner(
        StrategyConfig(),session=DAY,
        d1_levels=[level()] if levels is None else levels,
        d1_atr=4.,previous_d1_close=at_close,tick_size=.01,
        history_limit=history_limit,max_pairs=max_pairs)


def bar(n,low=100.,high=100.5,side="long",close=None):
    t=FIRST+timedelta(minutes=5*n)
    if close is None:
        close=(low+high)/2
    return Bar(t,close,high,low,close,timeframe="M5",volume=900.)


def test_bsu_is_prior_m5_extreme_not_daily_cluster_median():
    s=scanner()
    assert s.observe(bar(0,100.00,100.4))==()
    events=s.observe(bar(1,100.00,100.5))
    assert len(events)==1
    e=events[0]
    assert e.event=="BPU1_EXACT"
    assert e.level_price==100.0 != e.d1_context_price
    assert e.d1_context_price==100.03
    assert e.source_end==FIRST
    assert e.bpu1_end==FIRST+timedelta(minutes=5)
    assert not e.can_trade and not e.preclose_tvx_verified
    last=s.observe(bar(2,100.10,100.5))
    assert len(last)==1 and last[0].event=="BPU2_CLOSED"
    assert last[0].bpu2_end==FIRST+timedelta(minutes=10)
    assert last[0].level_price==100.0
    assert s.completed==1
    assert not s._pending


def test_approximate_touch_is_never_promoted_to_exact_bpu1():
    s=scanner()
    s.observe(bar(0,100.,100.4))
    assert s.observe(bar(1,100.03,100.5))==()
    assert s.completed==0
    assert not s._pending


def test_range_crossing_reference_is_not_exact_touch():
    s=scanner()
    s.observe(bar(0,100.10,100.4))
    # Price range crosses the source low but extreme is lower at 99.9.
    assert s.observe(bar(1,99.9,100.6))==()


@pytest.mark.parametrize("bpu2_low,bpu2_time,valid",[
    (99.99,2,False),  # piercing BPU1 extreme, despite close recovery
    (100.25,2,False), # BPU2 too far from support given .20 luft
    (100.1,3,False),  # one M5 interval missing after BPU1
    (100.10,2,True)])
def test_bpu2_is_immediately_next_completed_bar_and_respects_luft(
        bpu2_low,bpu2_time,valid):
    s=scanner()
    s.observe(bar(0))
    assert s.observe(bar(1))[0].event=="BPU1_EXACT"
    out=s.observe(bar(bpu2_time,bpu2_low,100.5))
    assert any(x.event=="BPU2_CLOSED" for x in out)==valid
    assert s.completed==int(valid)


def test_new_sources_not_considered_on_the_same_bar():
    s=scanner()
    assert s.observe(bar(0,99.9,100.5))==()
    assert len(s._history)==1


def test_multiple_independent_sources_are_observations_not_orders():
    s=scanner(levels=[level(100.03),level(100.04)])
    s.observe(bar(0))
    out=s.observe(bar(1))
    assert len(out)==1  # one same RAW source, despite two D1 zones
    assert not out[0].can_trade
    s.observe(bar(2,100.10,100.4))
    assert s.completed==1


def test_no_approved_daily_level_means_no_source_confirmation():
    s=scanner(levels=[level(confirmed=False),level(source="round_number")])
    assert s.zones==()
    for i in range(3):
        assert s.observe(bar(i))==()
    assert s.bpu1_count==s.completed==0


def test_bad_daily_zone_is_not_m5_bsu():
    s=scanner(levels=[level(120.)])
    assert not s.observe(bar(0))
    assert not s.observe(bar(1))
    assert s.completed==0


def test_mirror_role_uses_pre_session_daily_close_not_future_m5():
    s=scanner(levels=[level(100.03,"mirror")],at_close=101.)
    assert s.zones and s.zones[0].side=="long"
    t=scanner(levels=[level(100.03,"mirror")],at_close=99.)
    assert t.zones and t.zones[0].side=="short"
    undecided=scanner(levels=[level(100.03,"mirror")],at_close=100.03)
    assert not undecided.zones


def test_short_side_uses_actual_m5_high_and_no_wick_pierce():
    s=scanner(levels=[level(100.03,"resistance")])
    s.observe(bar(0,99.6,100.,close=99.8))
    out=s.observe(bar(1,99.5,100.,close=99.8))
    assert out and out[0].event=="BPU1_EXACT"
    assert out[0].level_price==100.0 and out[0].side=="short"
    out=s.observe(bar(2,99.5,99.9,close=99.8))
    assert out and out[0].event=="BPU2_CLOSED"


def test_missing_one_bar_between_bsu_and_bpu1_is_allowed():
    s=scanner()
    s.observe(bar(0))
    s.observe(bar(1,100.2,100.5))
    assert s.observe(bar(2,100.,100.4))[0].event=="BPU1_EXACT"


def test_duplicate_and_wrong_session_rejected_without_state_rewind():
    s=scanner()
    s.observe(bar(0))
    with pytest.raises(ValueError,match="DUPLICATE_OR_OUT_OF_ORDER"):
        s.observe(bar(0))
    assert len(s._history)==1
    with pytest.raises(ValueError,match="WRONG_SESSION"):
        s.observe(Bar(FIRST+timedelta(days=1),100.2,100.5,100.,100.2,
                      timeframe="M5",volume=900.))


def test_price_grid_mismatch_is_explicit_not_silently_rounded():
    s=scanner()
    s.observe(bar(0,100.005,100.4))
    # Historical price off current grid: never fabricate its BSU level.
    assert s.observe(bar(1,100.005,100.5))==()
    assert s.rejected_counts.get("SOURCE_OFF_CURRENT_NATIVE_GRID",0)>0


def test_zero_volume_native_m5_never_becomes_a_source():
    s=scanner()
    bad=Bar(FIRST,100.2,100.4,100.,100.2,
            timeframe="M5",volume=0.)
    with pytest.raises(ValueError,match="TRADED_NATIVE_VOLUME"):
        s.observe(bad)
    assert not s._history and s.bpu1_count==0


def test_coverage_is_only_already_observed_same_day_m5():
    s=scanner()
    assert s.observe(bar(0))==()
    assert all(b.ts.date()==DAY for b in s._history)
    assert not s._pending and s.completed==0
