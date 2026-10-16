"""QWCT 4.7: real-time cutoff and strict BSU source protection preflight.

Synthetic bars test deterministic software invariants only; NOT a native
QuantConnect second-data run and NOT Gerchik author ground truth.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from strategy.native_second_tvx import NativeSecondTvxWindow
from strategy.patterns_bsu import Bar, M5BsuSequenceScanner
from strategy.config import StrategyConfig

ET = ZoneInfo("America/New_York")
DAY = date(2024, 6, 3)
BPU1_END = datetime(2024, 6, 3, 10, 5, tzinfo=ET)


def sec(n, *, start=BPU1_END, ff=False, symbol="SRPT"):
    t = start + timedelta(seconds=n)
    return SimpleNamespace(
        time=t-timedelta(seconds=1), end_time=t,
        period=timedelta(seconds=1), symbol=symbol,
        open=100.0, high=100.1, low=99.9, close=100.0,
        volume=2, is_fill_forward=ff)


def test_47_real_30s_sample_only_at_exact_cutoff():
    w = NativeSecondTvxWindow(BPU1_END)
    assert w.bpu2_end == BPU1_END+timedelta(minutes=5)
    assert w.cutoff == BPU1_END+timedelta(minutes=4,seconds=30)
    for i in range(1, 270):
        assert w.accept(sec(i), symbol="SRPT") is None
        assert not w.complete
    sample = w.accept(sec(270),symbol="SRPT")
    assert sample is not None
    assert sample.observed_at == w.cutoff
    assert sample.observed_bars == 270
    assert sample.unobserved_seconds == 0
    assert not sample.can_submit
    assert w.complete


def test_47_missing_cutoff_second_cannot_create_preclose():
    w = NativeSecondTvxWindow(BPU1_END)
    for i in range(1, 270):
        assert w.accept(sec(i), symbol="SRPT") is None
    assert not w.complete
    # No SEC bar at the actual cutoff. A later one must be rejected.
    assert w.accept(sec(271),symbol="SRPT") is None
    assert w.blocked_reason == "SEC_OUTSIDE_BPU2_PRECLOSE_WINDOW"


def test_47_fill_forward_or_wrong_symbol_blocks_preclose():
    for changed, reason in [
        (sec(1,ff=True),"SEC_FILL_FORWARD"),
        (sec(1,symbol="MSFT"),"SEC_SYMBOL_MISMATCH"),
    ]:
        w=NativeSecondTvxWindow(BPU1_END)
        assert w.accept(changed,symbol="SRPT") is None
        assert w.blocked_reason == reason


def test_47_m1_bar_cannot_impersonate_native_second():
    w=NativeSecondTvxWindow(BPU1_END)
    fake=sec(1)
    fake.period=timedelta(minutes=1)
    assert w.accept(fake,symbol="SRPT") is None
    assert w.blocked_reason=="SEC_NATIVE_PERIOD_INVALID"


def test_47_sparse_native_seconds_have_bounded_gap():
    w=NativeSecondTvxWindow(BPU1_END)
    for i in range(1,271,2):
        result=w.accept(sec(i),symbol="SRPT")
    assert result is None
    assert w.blocked_reason == ""  # no exact cutoff bar, no evidence
    assert not w.complete


def test_47_unobserved_gap_over_10s_blocks():
    w=NativeSecondTvxWindow(BPU1_END)
    assert w.accept(sec(1),symbol="SRPT") is None
    assert w.accept(sec(12),symbol="SRPT") is None
    assert w.blocked_reason=="SEC_UNOBSERVED_GAP_OVER_10S"


def source_scan():
    lvl=SimpleNamespace(price=100.03,kind="support",
        source="swing_cluster",valid_from=DAY,touches=3,strength=3.)
    return M5BsuSequenceScanner(StrategyConfig(),session=DAY,
        d1_levels=[lvl],d1_atr=4.,previous_d1_close=101.,tick_size=.01)


def m5(n,low=100.,high=100.5):
    t=BPU1_END+timedelta(minutes=5*n)
    return Bar(t,100.2,high,low,100.2,timeframe="M5",volume=200.)


def test_47_43_fixed_source_pierce_blocks_reuse():
    scan=source_scan()
    scan.observe(m5(0,100.,100.5))
    scan.observe(m5(1,99.99,100.5))
    events=scan.observe(m5(2,100.,100.5))
    assert not any(e.event=="BPU1_EXACT" and e.source_end==BPU1_END for e in events)
    assert scan.rejected_counts.get("BSU_SOURCE_PIERCED_BEFORE_BPU1",0)>=1


def test_47_43_missing_m5_resets_source_history():
    scan=source_scan()
    scan.observe(m5(0))
    scan.observe(m5(2))
    assert scan.rejected_counts["M5_SOURCE_CONTINUITY_GAP_RESET"]==1
    assert len(scan._history)==1
    assert scan._history[0].ts==m5(2).ts
