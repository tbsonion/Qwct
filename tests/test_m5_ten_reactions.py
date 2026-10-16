"""QWCT 5.0 closed M5 research ten reactions; synthetic checks only."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from strategy.m5_reaction_taxonomy import (
    KINDS, M5ReactionHeuristics, M5TenReactionObserver,
)

ET = ZoneInfo("America/New_York")
AT = datetime(2024, 6, 3, 10, 0, tzinfo=ET)


def bar(i, *, o, h, l, c, vol=100):
    assert l <= min(o,c) <= max(o,c) <= h
    return SimpleNamespace(ts=AT+timedelta(minutes=5*i),
                           timeframe="M5",open=o,high=h,low=l,close=c,
                           volume=vol)


def obs(side="long"):
    return M5TenReactionObserver(100., side, 0.01)


def kinds(s,b,atr=1.0):
    return {e.kind for e in s.observe(b, atr)}


def test_all_ten_defined_and_never_promote_to_trades():
    assert KINDS == (
        "BOUNCE", "WICK_BOUNCE", "WICK_RECLAIM", "FALSE_BREAK_1BAR",
        "FALSE_BREAK_2BAR", "BREAK_FOLLOWTHROUGH", "MIRROR_RETEST",
        "COMPRESSION", "CONSOLIDATION", "CHOP")
    s=obs()
    assert not any(e.can_trade for e in s.observe(
        bar(0,o=100.4,h=100.6,l=99.7,c=100.2),1.0))


def test_bounce_and_long_wick_bounce_require_next_completed_m5():
    s=obs()
    first=kinds(s,bar(0,o=100.5,h=100.6,l=99.8,c=100.3))
    assert "BOUNCE" not in first and "WICK_BOUNCE" not in first
    assert {"BOUNCE","WICK_BOUNCE"} <= kinds(
        s,bar(1,o=100.35,h=100.9,l=100.15,c=100.7))


def test_wick_reclaim_and_single_bar_false_break_are_distinct():
    s=obs()
    assert {"WICK_RECLAIM","FALSE_BREAK_1BAR"} <= kinds(
        s,bar(0,o=100.2,h=100.6,l=99.7,c=100.1))
    s=obs()
    out=s.observe(bar(0,o=99.5,h=100.5,l=99.0,c=100.2))
    assert {e.kind for e in out} == {"WICK_RECLAIM"}
    assert out[0].reason == "BODY_CROSS_RECLAIM"


def test_two_bar_false_break_requires_prior_defended_side():
    s=obs()
    kinds(s,bar(0,o=100.2,h=100.4,l=100.05,c=100.2))
    kinds(s,bar(1,o=100.1,h=100.2,l=99.5,c=99.7))
    assert "FALSE_BREAK_2BAR" in kinds(
        s,bar(2,o=99.9,h=100.4,l=99.7,c=100.2))
    t=obs()
    kinds(t,bar(0,o=99.4,h=99.8,l=99.3,c=99.5))
    kinds(t,bar(1,o=99.5,h=99.8,l=99.3,c=99.6))
    assert "FALSE_BREAK_2BAR" not in kinds(
        t,bar(2,o=99.8,h=100.4,l=99.5,c=100.2))


def test_break_followthrough_and_later_mirror_retest_do_not_look_ahead():
    s=obs()
    kinds(s,bar(0,o=100.2,h=100.4,l=100.05,c=100.2))
    kinds(s,bar(1,o=100.1,h=100.2,l=99.5,c=99.8))
    confirm=kinds(s,bar(2,o=99.8,h=99.9,l=99.5,c=99.6))
    assert "BREAK_FOLLOWTHROUGH" in confirm
    assert "MIRROR_RETEST" not in confirm
    assert "MIRROR_RETEST" in kinds(
        s,bar(3,o=99.6,h=100.1,l=99.3,c=99.7))
    assert "MIRROR_RETEST" not in kinds(
        s,bar(4,o=99.7,h=100.4,l=99.6,c=100.2))


def test_compression_requires_four_shrinking_approaches_and_native_atr():
    sequence=[
        bar(0,o=101.0,h=101.4,l=100.2,c=100.6),
        bar(1,o=100.6,h=100.85,l=100.22,c=100.45),
        bar(2,o=100.45,h=100.55,l=100.12,c=100.30),
        bar(3,o=100.30,h=100.35,l=100.05,c=100.15),
    ]
    s=obs()
    for b in sequence[:-1]:
        assert "COMPRESSION" not in kinds(s,b,atr=2.)
    assert "COMPRESSION" in kinds(s,sequence[-1],atr=2.)
    n=obs()
    for b in sequence:
        result=n.observe(b, atr_m5=None)
    assert "COMPRESSION" not in {x.kind for x in result}


def test_consolidation_multiple_intersections_is_not_exact_bpu():
    s=obs()
    for i in range(4):
        kinds(s,bar(i,o=100.05,h=100.3,l=99.85,c=100.10))
    tagged=s.observe(bar(4,o=100.05,h=100.3,l=99.85,c=100.10),1.)
    assert "CONSOLIDATION" in {x.kind for x in tagged}
    assert all(e.can_trade is False for e in tagged)


def test_chop_needs_close_crosses_not_overnight_gaps_only():
    s=obs()
    for i,c in enumerate((100.1,99.9,100.1,99.9,100.1,99.9)):
        out=kinds(s,bar(i,o=100.,h=100.4,l=99.6,c=c))
    assert "CHOP" in out
    t=obs()
    for i,c in enumerate((100.1,99.9,100.1,99.9,100.1,99.9)):
        if c > 100:
            b=bar(i,o=100.1,h=100.4,l=100.06,c=c)
        else:
            b=bar(i,o=99.9,h=99.94,l=99.6,c=c)
        out=kinds(t,b)
    assert "CHOP" not in out


def test_missing_m5_resets_history_and_mirror_provenance():
    s=obs()
    kinds(s,bar(0,o=100.2,h=100.4,l=100.05,c=100.2))
    kinds(s,bar(1,o=100.1,h=100.2,l=99.5,c=99.8))
    assert "BREAK_FOLLOWTHROUGH" not in kinds(
        s,bar(3,o=99.8,h=99.9,l=99.5,c=99.6))
    assert s.gap_resets==1
    assert "MIRROR_RETEST" not in kinds(
        s,bar(4,o=99.6,h=100.1,l=99.3,c=99.7))


def test_short_side_symmetric_wick_reclaim():
    s=obs("short")
    out=kinds(s,bar(0,o=99.8,h=100.3,l=99.4,c=99.9))
    assert {"WICK_RECLAIM","FALSE_BREAK_1BAR"} <= out


def test_no_duplicate_no_off_grid_no_zero_volume_or_wrong_tf():
    s=obs()
    first=bar(0,o=100.1,h=100.4,l=99.8,c=100.2)
    kinds(s,first)
    with pytest.raises(ValueError,match="DUPLICATE"):
        s.observe(first,1.)
    with pytest.raises(ValueError,match="INVALID_M5_ATR"):
        s.observe(bar(1,o=100.1,h=100.4,l=99.8,c=100.2),0)
    assert s._last == first.ts
    misaligned=bar(1,o=100.1,h=100.4,l=99.8,c=100.2)
    misaligned.ts += timedelta(minutes=1)
    with pytest.raises(ValueError,match="CLOSED_NATIVE_TIME"):
        s.observe(misaligned,1.)
    missing=bar(1,o=100.1,h=100.4,l=99.8,c=100.2,vol=0)
    with pytest.raises(ValueError,match="INVALID_OHLCV"):
        s.observe(missing,1.)
    with pytest.raises(ValueError,match="CLOSED_NATIVE_TIME"):
        s.observe(SimpleNamespace(**{**vars(first), "timeframe":"M1"}),1.)


def test_event_times_are_closed_bar_end_not_source_or_future():
    s=obs()
    b1=bar(0,o=100.5,h=100.6,l=99.8,c=100.3)
    b2=bar(1,o=100.35,h=100.9,l=100.15,c=100.7)
    s.observe(b1,1.)
    ev=s.observe(b2,1.)
    assert ev
    assert all(e.bar_end==b2.ts and e.anchor_end <= b2.ts
               and not e.can_trade for e in ev)


def test_heuristics_are_explicitly_not_author_thresholds():
    with pytest.raises(ValueError,match="INVALID_WINDOW"):
        M5TenReactionObserver(100.,"long",.01,
             M5ReactionHeuristics(compression_bars=2))
    with pytest.raises(ValueError,match="WINDOW_NOT_INTEGER"):
        M5TenReactionObserver(100.,"long",.01,
             M5ReactionHeuristics(chop_min_flips=3.5))
