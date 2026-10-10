"""Gerchik BSU/BPU/TVX behavioral requirements.

Synthetic OHLC examples exercise PURE PATTERN RULES, never broker fills or
backtest profitability. Their expected outcomes are fixed BEFORE patching.
Source: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from strategy.config import StrategyConfig
from strategy.patterns_bsu import Bar, BsuDetector


ET = ZoneInfo("America/New_York")
DAY = datetime(2026, 10, 9, 9, 30, tzinfo=ET)
BPU1_END = DAY + timedelta(minutes=35)  # 10:05 ET
BPU2_END = BPU1_END + timedelta(minutes=5)
BSU_TS = DAY - timedelta(days=2)


def m5(end, low, high, close=None, op=None):
    if close is None:
        close = (low + high) / 2
    if op is None:
        op = close
    return Bar(end, op, high, low, close, timeframe="M5")


def detector(side="long", level=100.0, atr=4.0):
    # Tick tolerance must come from native security data; not 5% of ATR.
    return BsuDetector(StrategyConfig(), level, side,
                       atr_value=atr, tick_size=0.01, bsu_ts=BSU_TS)


def initiate(side="long"):
    d = detector(side)
    bpu1 = (m5(BPU1_END, 100.0, 100.40, 100.2) if side == "long"
            else m5(BPU1_END, 99.60, 100.0, 99.8))
    assert d.on_bar(bpu1).phase == "bpu1"
    return d


@pytest.mark.parametrize("side,bpu1", [
    ("long", m5(BPU1_END, 100.03, 100.40)),
    ("short", m5(BPU1_END, 99.60, 99.97)),
])
def test_bpu1_touch_is_tick_accurate_not_atr_accurate(side, bpu1):
    # Old code accepted $0.03 distance from a $100 level on ATR=$4.
    assert detector(side).on_bar(bpu1).phase == "watch_bpu1"


@pytest.mark.parametrize("side,bpu2", [
    ("long", m5(BPU2_END, 99.99, 100.45, 100.20)),
    ("short", m5(BPU2_END, 99.55, 100.01, 99.80)),
])
def test_bpu2_wick_piercing_bpu1_breaks_model_even_if_close_recovers(side, bpu2):
    assert initiate(side).on_bar(bpu2).phase == "invalidated"


@pytest.mark.parametrize("side,bpu2", [
    ("long", m5(BPU2_END, 100.25, 100.50)),
    ("short", m5(BPU2_END, 99.50, 99.75)),
])
def test_bpu2_missing_level_by_more_than_luft_invalidates(side, bpu2):
    # ATR=4, stop buffer ATR*.25=1; luft = .2; $0.25 misses.
    assert initiate(side).on_bar(bpu2).phase == "invalidated"


@pytest.mark.parametrize("side,bpu2", [
    ("long", m5(BPU2_END + timedelta(minutes=5), 100.10, 100.45)),
    ("short", m5(BPU2_END + timedelta(minutes=5), 99.55, 99.90)),
])
def test_bpu2_must_immediately_follow_bpu1_no_missing_candle(side, bpu2):
    assert initiate(side).on_bar(bpu2).phase == "invalidated"


def test_repeated_or_out_of_order_bars_must_not_form_bpu2():
    d = initiate()
    assert d.on_bar(m5(BPU1_END, 100.05, 100.45)).phase == "invalidated"


def test_unknown_source_bsu_or_native_tick_size_cannot_be_guessed():
    with pytest.raises(ValueError):
        BsuDetector(StrategyConfig(), 100., "long", atr_value=4.)
    with pytest.raises(ValueError):
        BsuDetector(StrategyConfig(), 100., "long", atr_value=4.,
                    tick_size=0.01)
    with pytest.raises(ValueError):
        BsuDetector(StrategyConfig(), 100., "long", atr_value=4.,
                    tick_size=0.0, bsu_ts=BSU_TS)


@pytest.mark.parametrize("bad", [
    m5(BPU1_END, -1., 100.),
    m5(BPU1_END, 100., 99.),
    m5(BPU1_END, float("nan"), 101.),
    Bar(BPU1_END.replace(tzinfo=None), 100., 101., 100., 100.5, "M5"),
])
def test_invalid_prices_or_naive_timestamp_rejected(bad):
    with pytest.raises(ValueError):
        detector().on_bar(bad)


def test_bsu_time_must_precede_bpu1():
    d = BsuDetector(StrategyConfig(), 100., "long", atr_value=4.,
                    tick_size=.01, bsu_ts=BPU1_END)
    assert d.on_bar(m5(BPU1_END, 100., 100.4)).phase == "invalidated"


def test_completed_bpu2_is_not_fictional_preclose_tvx():
    d = initiate()
    st = d.on_bar(m5(BPU2_END, 100.10, 100.40))
    assert st.phase == "bpu2_confirmed"
    assert not st.preclose_seen
    assert "30" in d.tvx_timing_note()   # unattainable from completed M5


def test_next_bar_ohlc_touch_is_not_retroactive_entry_or_fill():
    d = initiate()
    d.on_bar(m5(BPU2_END, 100.10, 100.40))
    st = d.on_bar(m5(BPU2_END + timedelta(minutes=5), 99.0, 99.5))
    # No crossing of entry=100.20; old code reported 'triggered'.
    assert st.phase != "triggered"


def test_subminute_preclose_observation_is_only_unconfirmed_research():
    d = initiate()
    at = BPU2_END - timedelta(seconds=30)
    st = d.observe_preclose(
        observed_at=at, bpu2_end=BPU2_END,
        observed_low=100.10, observed_high=100.45,
        last_price=100.2, source="SEC")
    assert st.phase == "preclose_candidate"
    assert st.preclose_seen
    assert not st.can_submit
    assert st.entry_price == pytest.approx(100.2)
    # A candle can later invalidate even a valid preclose observation.
    assert d.on_bar(m5(BPU2_END, 99.99, 100.45)).phase == "invalidated"


@pytest.mark.parametrize("source,at_delta", [
    ("M5", 30), ("M1", 30), ("SEC", 31), ("SEC", 29), ("TICK", -1),
])
def test_preclose_fails_closed_without_precise_timing(source, at_delta):
    d = initiate()
    at = BPU2_END - timedelta(seconds=at_delta)
    with pytest.raises(ValueError):
        d.observe_preclose(
            observed_at=at, bpu2_end=BPU2_END,
            observed_low=100.10, observed_high=100.45,
            last_price=100.2, source=source)


def test_observed_preclose_cannot_be_called_without_bpu1():
    with pytest.raises(ValueError):
        detector().observe_preclose(
            observed_at=BPU2_END - timedelta(seconds=30),
            bpu2_end=BPU2_END,
            observed_low=100.1, observed_high=100.45,
            last_price=100.2, source="SEC")


def test_valid_bpu2_with_precise_preclose_observation_is_research_only():
    d = initiate()
    d.observe_preclose(
        observed_at=BPU2_END - timedelta(seconds=30),
        bpu2_end=BPU2_END, observed_low=100.1, observed_high=100.4,
        last_price=100.2, source="TICK")
    st = d.on_bar(m5(BPU2_END, 100.1, 100.45))
    assert st.phase == "bpu2_confirmed"
    assert st.preclose_seen
    assert not st.can_submit
