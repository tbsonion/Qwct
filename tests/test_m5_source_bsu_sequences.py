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




def test_broken_support_source_cannot_be_reused_as_exact_bpu1():
    scan=scanner()
    scan.observe(bar(0,100.00,100.5))
    # Price ran THROUGH the earlier source, then later retouched 100.
    # A true fixed support bounce requires intact historical provenance.
    scan.observe(bar(1,99.60,100.3))
    result=scan.observe(bar(2,100.00,100.4))
    assert not any(x.event=="BPU1_EXACT" for x in result)
    assert scan.bpu1_count==0
    assert scan.rejected_counts.get("BSU_SOURCE_PIERCED_BEFORE_BPU1",0)>0


def test_broken_resistance_source_cannot_be_reused_as_exact_bpu1():
    scan=scanner(levels=[level(100.03,"resistance")])
    scan.observe(bar(0,99.4,100.00,close=99.6))
    scan.observe(bar(1,99.5,100.50,close=100.1))
    result=scan.observe(bar(2,99.5,100.00,close=99.8))
    assert not result
    assert scan.rejected_counts.get("BSU_SOURCE_PIERCED_BEFORE_BPU1",0)>0


def test_missing_closed_native_m5_resets_old_source_but_new_segment_can_pass():
    scan=scanner()
    scan.observe(bar(0))
    # Missing closed bar(1) => cannot prove no wick penetrated old source.
    assert scan.observe(bar(2))==()
    assert scan.rejected_counts.get("M5_SOURCE_CONTINUITY_GAP_RESET")==1
    assert len(scan._history)==1
    assert scan.observe(bar(3))[0].event=="BPU1_EXACT"
    assert scan.observe(bar(4,100.10,100.5))[0].event=="BPU2_CLOSED"


def test_pending_bpu1_cannot_bridge_missing_closed_m5_interval():
    scan=scanner()
    scan.observe(bar(0))
    scan.observe(bar(1))
    assert scan.bpu1_count==1 and scan._pending
    # No native bar(2). An M5 at +10min cannot be a BPU2.
    out=scan.observe(bar(3,100.1,100.5))
    assert not any(x.event=="BPU2_CLOSED" for x in out)
    assert scan.completed==0 and not scan._pending
    assert scan.rejected_counts.get("M5_SOURCE_CONTINUITY_GAP_RESET")==1


def test_unbroken_fixed_support_remains_eligible_after_many_bars():
    scan=scanner()
    scan.observe(bar(0,100.,100.5))
    for n in range(1,4):
        assert scan.observe(bar(n,100.10,100.5))==()
    result=scan.observe(bar(4,100.,100.5))
    assert result and result[0].event=="BPU1_EXACT"
    assert result[0].source_end==FIRST


def test_coverage_is_only_already_observed_same_day_m5():
    s=scanner()
    assert s.observe(bar(0))==()
    assert all(b.ts.date()==DAY for b in s._history)
    assert not s._pending and s.completed==0
