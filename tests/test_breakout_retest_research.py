"""Deterministic research-only breakout/retest lifecycle; not LEAN/backtest."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from strategy.breakout_retest import BreakoutRetestObserver

ET = ZoneInfo("America/New_York")
T0 = datetime(2024, 1, 2, 10, 30, tzinfo=ET)


def observer(side="long", **kwargs):
    params = dict(symbol="NVDA", session=T0.date(), side=side,
                  level_price=100., atr_value=2.,
                  max_confirm_chase_atr=0.3)
    params.update(kwargs)
    return BreakoutRetestObserver(**params)


def deliver(obs, minute, o, h, l, c, v=1000):
    return obs.on_m5(at=T0 + timedelta(minutes=minute),
                     open_price=o, high=h, low=l, close=c, volume=v)


def ready_long(obs):
    assert deliver(obs, 0, 99.8, 99.9, 99.6, 99.8).phase == "WATCH_BREAKOUT"
    assert deliver(obs, 5, 99.8, 100.4, 99.7, 100.2).phase == "WAIT_RETEST"
    assert deliver(obs, 10, 100.2, 100.3, 99.9, 100.08).phase == "WAIT_CONFIRMATION"


def test_three_distinct_completed_m5_bars_for_long_and_no_earlier_signal():
    obs = observer()
    ready_long(obs)
    assert obs.evidence.can_submit is False
    assert obs.evidence.confirmed_at is None
    result = deliver(obs, 15, 100.08, 100.5, 100.01, 100.42)
    assert result.phase == "CONFIRMED"
    assert result.confirmed_at == T0 + timedelta(minutes=15)
    assert result.breakout_at == T0 + timedelta(minutes=5)
    assert result.retest_at == T0 + timedelta(minutes=10)
    assert result.matches(symbol="NVDA", session=T0.date(), side="long",
                          level_price=100., observed_at=result.confirmed_at)
    assert result.can_submit is False


def test_short_breakdown_retest_held_then_close_below_retest_low():
    obs = observer("short")
    assert deliver(obs, 0, 100.2, 100.3, 100.1, 100.2).phase == "WATCH_BREAKOUT"
    assert deliver(obs, 5, 100.2, 100.3, 99.6, 99.8).phase == "WAIT_RETEST"
    assert deliver(obs, 10, 99.8, 100.1, 99.7, 99.92).phase == "WAIT_CONFIRMATION"
    result = deliver(obs, 15, 99.92, 100.02, 99.5, 99.55)
    assert result.phase == "CONFIRMED"
    assert result.can_submit is False


def test_cross_from_wrong_side_or_only_wick_never_arms():
    obs = observer()
    assert deliver(obs, 0, 100.1, 100.3, 100., 100.2).phase == "WATCH_BREAKOUT"
    assert deliver(obs, 5, 100.2, 100.5, 100.1, 100.3).phase == "WATCH_BREAKOUT"
    assert deliver(obs, 10, 100.3, 100.5, 99.5, 99.8).phase == "WATCH_BREAKOUT"
    assert deliver(obs, 15, 99.8, 100.5, 99.6, 99.9).phase == "WATCH_BREAKOUT"
    assert obs.evidence.breakout_at is None


def test_breakout_and_touch_on_same_bar_cannot_be_retroactive_confirmation():
    obs = observer()
    deliver(obs, 0, 99.7, 99.9, 99.6, 99.8)
    result = deliver(obs, 5, 99.8, 100.45, 99.8, 100.2)
    assert result.phase == "WAIT_RETEST"
    assert result.retest_at is None
    assert result.confirmed_at is None


def test_no_retest_expires_after_eight_future_completed_m5():
    obs = observer()
    deliver(obs, 0, 99.7, 99.9, 99.6, 99.8)
    deliver(obs, 5, 99.8, 100.4, 99.7, 100.2)
    for n in range(1, 9):
        result = deliver(obs, 5 + 5*n, 100.65, 100.9, 100.61, 100.7)
        assert result.phase == "WAIT_RETEST"
    assert deliver(obs, 50, 100.65, 100.9, 100.61, 100.7).phase == "EXPIRED"


def test_breach_loss_side_invalidates_before_any_retest():
    obs = observer()
    deliver(obs, 0, 99.8, 99.9, 99.5, 99.8)
    deliver(obs, 5, 99.8, 100.4, 99.7, 100.2)
    result = deliver(obs, 10, 99.8, 100.3, 98.8, 98.9)
    assert result.phase == "INVALIDATED"
    assert result.reason == "CLOSED_BEYOND_LOSS_SIDE"


def test_retest_must_hold_reclaimed_level_not_just_touch_with_wick():
    obs = observer()
    deliver(obs, 0, 99.8, 99.9, 99.5, 99.8)
    deliver(obs, 5, 99.8, 100.4, 99.7, 100.2)
    assert deliver(obs, 10, 100.1, 100.3, 99.5, 99.7).phase == "WAIT_RETEST"


def test_confirmation_must_be_next_bar_not_old_breakout_extreme():
    obs = observer()
    ready_long(obs)
    result = deliver(obs, 15, 100.08, 100.2, 99.8, 100.16)
    assert result.phase == "INVALIDATED"
    assert result.reason == "NEXT_M5_DID_NOT_CONFIRM"
    # Once rejected, no retroactive successful signal on a later candle.
    assert deliver(obs, 20, 100.16, 100.8, 100.1, 100.6).phase == "INVALIDATED"


def test_confirm_close_far_beyond_level_is_no_chase_blocker():
    obs = observer()
    ready_long(obs)
    result = deliver(obs, 15, 100.08, 101.2, 100., 101.)
    assert result.phase == "INVALIDATED"
    assert result.reason == "CONFIRM_OVEREXTENDED_NO_CHASE"


def test_missing_m5_timestamp_between_retest_and_confirmation_fails_closed():
    obs = observer()
    ready_long(obs)
    result = deliver(obs, 20, 100.08, 100.5, 100.01, 100.42)
    assert result.phase == "INVALIDATED"
    assert result.reason == "M5_GAP_DUPLICATE_OR_LATE"


def test_duplicate_preconfirmation_m5_cannot_advance_state():
    obs = observer()
    ready_long(obs)
    result = deliver(obs, 10, 100.2, 100.3, 99.9, 100.08)
    assert result.phase == "INVALIDATED"


def test_isolation_and_replay_timestamp_guard():
    obs = observer()
    ready_long(obs)
    evidence = deliver(obs, 15, 100.08, 100.5, 100.01, 100.42)
    assert not evidence.matches(symbol="TSLA", session=T0.date(),
                                side="long", level_price=100.,
                                observed_at=evidence.confirmed_at)
    assert not evidence.matches(symbol="NVDA", session=T0.date(),
                                side="short", level_price=100.,
                                observed_at=evidence.confirmed_at)
    assert not evidence.matches(symbol="NVDA", session=T0.date(),
                                side="long", level_price=101.,
                                observed_at=evidence.confirmed_at)
    assert not evidence.matches(symbol="NVDA", session=T0.date(),
                                side="long", level_price=100.,
                                observed_at=evidence.confirmed_at+timedelta(minutes=5))
    assert deliver(obs, 20, 100.42, 100.6, 100.1, 100.5) == evidence


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), -1, 0])
def test_missing_native_d1_atr_or_unverified_config_never_arms(bad):
    with pytest.raises(ValueError):
        observer(atr_value=bad)


def test_invalid_m5_input_is_terminal_no_synthetic_retest():
    obs = observer()
    ready_long(obs)
    result = deliver(obs, 15, 100.08, 100.4, 100.01, 100.3, v=0)
    assert result.phase == "INVALIDATED"
    assert result.confirmed_at is None


def test_session_end_or_wrong_day_never_confirm():
    obs = observer()
    ready_long(obs)
    result = obs.on_m5(
        at=T0 + timedelta(days=1, minutes=15),
        open_price=100.08, high=100.5, low=100.01, close=100.42,
        volume=1000)
    assert result.phase == "INVALIDATED"
    assert result.can_submit is False
