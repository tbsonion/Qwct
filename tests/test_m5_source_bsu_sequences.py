"""QWCT 4.1: native RAW M5 source -> exact BPU1 -> BPU2.

Pure tests only: NOT proof of author-labelled BSU or actual LEAN feed.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest
from strategy.config import StrategyConfig
from strategy.patterns_bsu import Bar, M5BsuSequenceScanner, M5LevelReactionObserver, FixedFloatingLimitObserver

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
        scan.observe(bar(n,100.10,100.5))  # Other source prices may match.
    result=scan.observe(bar(4,100.,100.5))
    assert result and result[0].event=="BPU1_EXACT"
    assert result[0].source_end==FIRST


def test_unaligned_native_m5_is_rejected_without_polluting_history():
    scan=scanner()
    first=bar(0)
    invalid=Bar(FIRST+timedelta(minutes=1),100.2,100.5,100.,
                100.2,timeframe="M5",volume=900.)
    with pytest.raises(ValueError,match="M5_BSU_INVALID_FIVE_MINUTE_END"):
        scan.observe(invalid)
    assert not scan._history and scan._last is None
    assert scan.observe(first)==()
    assert len(scan._history)==1


def test_utc_native_m5_end_still_valid_when_et_grid_aligned():
    scan=scanner()
    from datetime import timezone
    source=bar(0)
    utc=Bar(source.ts.astimezone(timezone.utc),source.open,source.high,
            source.low,source.close,timeframe="M5",volume=source.volume)
    assert scan.observe(utc)==()
    assert scan.bpu1_count==0 and scan.completed==0


def test_coverage_is_only_already_observed_same_day_m5():
    s=scanner()
    assert s.observe(bar(0))==()
    assert all(b.ts.date()==DAY for b in s._history)
    assert not s._pending and s.completed==0


def reaction_bar(n, o, h, l, c):
    return Bar(FIRST+timedelta(minutes=5*n),o,h,l,c,timeframe="M5",volume=1000)


def kinds(observer, bar):
    return {e.kind for e in observer.observe(bar)}


def test_44_support_touch_without_wick_pierce():
    s=M5LevelReactionObserver(100.0,"long",.01)
    assert kinds(s,reaction_bar(0,100.2,100.4,100.0,100.3))=={"TOUCH_HOLD"}


def test_44_support_wick_pierce_and_close_back_inside():
    s=M5LevelReactionObserver(100.0,"long",.01)
    assert kinds(s,reaction_bar(0,100.2,100.4,99.7,100.3))=={"WICK_PIERCE_RECLAIM"}


def test_44_resistance_wick_pierce_and_close_back_inside():
    s=M5LevelReactionObserver(100.0,"short",.01)
    assert kinds(s,reaction_bar(0,99.7,100.3,99.5,99.8))=={"WICK_PIERCE_RECLAIM"}


def test_44_two_bar_false_break_support():
    s=M5LevelReactionObserver(100.0,"long",.01)
    s.observe(reaction_bar(0,100.2,100.3,100.1,100.2))
    assert kinds(s,reaction_bar(1,100.1,100.1,99.7,99.8))=={"FIRST_CLOSE_BEYOND_LEVEL"}
    assert kinds(s,reaction_bar(2,99.8,100.3,99.7,100.2))=={"TWO_BAR_FALSE_BREAK_RECLAIM"}


def test_44_two_bar_false_break_resistance():
    s=M5LevelReactionObserver(100.0,"short",.01)
    s.observe(reaction_bar(0,99.8,99.9,99.7,99.8))
    assert kinds(s,reaction_bar(1,99.9,100.3,99.8,100.2))=={"FIRST_CLOSE_BEYOND_LEVEL"}
    assert kinds(s,reaction_bar(2,100.2,100.3,99.7,99.8))=={"TWO_BAR_FALSE_BREAK_RECLAIM"}


def test_44_two_closes_beyond_and_mirror_retest():
    s=M5LevelReactionObserver(100.0,"long",.01)
    s.observe(reaction_bar(0,100.3,100.4,100.2,100.3))
    assert kinds(s,reaction_bar(1,100.2,100.2,99.6,99.8))=={"FIRST_CLOSE_BEYOND_LEVEL"}
    assert kinds(s,reaction_bar(2,99.8,99.9,99.5,99.7))=={"TWO_CLOSES_BEYOND_LEVEL"}
    assert kinds(s,reaction_bar(3,99.7,100.0,99.5,99.8))=={"MIRROR_RETEST_AFTER_BREAK"}
    assert kinds(s,reaction_bar(4,99.8,100.2,99.7,100.2))=={"RECLAIM_AFTER_SUSTAINED_BREAK"}


def test_44_no_two_bar_false_label_after_multiple_beyond_closes():
    s=M5LevelReactionObserver(100.0,"long",.01)
    s.observe(reaction_bar(0,100.3,100.4,100.2,100.3))
    s.observe(reaction_bar(1,100.2,100.2,99.6,99.8))
    s.observe(reaction_bar(2,99.8,99.9,99.5,99.7))
    out=kinds(s,reaction_bar(3,99.7,100.3,99.6,100.2))
    assert "TWO_BAR_FALSE_BREAK_RECLAIM" not in out
    assert "RECLAIM_AFTER_SUSTAINED_BREAK" in out


def test_44_missing_m5_does_not_fabricate_two_bar_reclaim():
    s=M5LevelReactionObserver(100.0,"long",.01)
    s.observe(reaction_bar(0,100.3,100.4,100.2,100.3))
    s.observe(reaction_bar(1,100.2,100.2,99.6,99.8))
    assert "TWO_BAR_FALSE_BREAK_RECLAIM" not in kinds(
        s,reaction_bar(3,99.7,100.3,99.6,100.2))


def test_44_reaction_evidence_cannot_trade_and_does_not_promote_bpu():
    s=M5LevelReactionObserver(100.0,"long",.01)
    evidence=s.observe(reaction_bar(0,100.2,100.4,99.7,100.3))
    assert evidence[0].kind=="WICK_PIERCE_RECLAIM"
    assert not evidence[0].can_trade
    assert not hasattr(evidence[0],"event")


def test_44_invalid_bar_does_not_mutate_history():
    s=M5LevelReactionObserver(100.0,"long",.01)
    with pytest.raises(ValueError,match="REACTION_INVALID_OHLC"):
        s.observe(reaction_bar(0,100.2,100.1,99.9,100.3))
    assert s._last is None
    assert kinds(s,reaction_bar(0,100.2,100.4,99.7,100.3))=={"WICK_PIERCE_RECLAIM"}


def test_45_exact_three_unpierced_hits_fixed_limit():
    o=FixedFloatingLimitObserver(100.,"long",.01)
    for i in range(2):
        result=o.observe(reaction_bar(i,100.2,100.4,100.,100.3))
        assert result.status=="INDETERMINATE"
    result=o.observe(reaction_bar(2,100.2,100.4,100.,100.3))
    assert result.status=="FIXED_LIMIT_CANDIDATE"
    assert result.hits==3 and result.adverse_pierces==0
    assert not result.can_trade


def test_45_single_pierce_without_prior_hits_is_not_floating_zone():
    o=FixedFloatingLimitObserver(100.,"long",.01)
    result=o.observe(reaction_bar(0,100.1,100.3,99.9,100.2))
    assert result.status=="INDETERMINATE"
    assert result.adverse_pierces==0


def test_45_support_wick_pierce_disqualifies_exact_fixed_limit():
    o=FixedFloatingLimitObserver(100.,"long",.01)
    for i in range(3):
        o.observe(reaction_bar(i,100.2,100.4,100.,100.3))
    result=o.observe(reaction_bar(3,100.2,100.4,99.99,100.3))
    assert result.status=="FLOATING_ZONE"
    assert result.adverse_pierces==1


def test_45_resistance_pierce_disqualifies_exact_fixed_limit():
    o=FixedFloatingLimitObserver(100.,"short",.01)
    for i in range(3):
        o.observe(reaction_bar(i,99.8,100.,99.6,99.7))
    assert o.observe(reaction_bar(3,99.8,100.01,99.6,99.7)).status=="FLOATING_ZONE"


def test_45_nearby_prices_are_not_exact_limit_hits():
    o=FixedFloatingLimitObserver(100.,"long",.01)
    for i in range(4):
        result=o.observe(reaction_bar(i,100.2,100.4,100.01,100.3))
    assert result.status=="INDETERMINATE"
    assert result.hits==0


def test_45_missing_native_m5_resets_fixed_evidence():
    o=FixedFloatingLimitObserver(100.,"long",.01)
    for i in range(3):
        o.observe(reaction_bar(i,100.2,100.4,100.,100.3))
    result=o.observe(reaction_bar(4,100.2,100.4,100.,100.3))
    assert result.status=="INDETERMINATE"
    assert result.hits==1
    assert "GAP_RESET" in result.reason


def test_45_reject_off_grid_source_and_out_of_order():
    with pytest.raises(ValueError,match="OFF_NATIVE_TICK"):
        FixedFloatingLimitObserver(100.005,"long",.01)
    o=FixedFloatingLimitObserver(100.,"long",.01)
    b=reaction_bar(0,100.2,100.4,100.,100.3)
    o.observe(b)
    with pytest.raises(ValueError,match="OUT_OF_ORDER"):
        o.observe(b)
