"""Source-level safety tests for D1 session freezes and NY exchange clocks.

The test fixtures are deterministic historical views, not broker/order
simulations and not a QuantConnect Cloud integration test.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.levels import Level
from strategy.sessions import SessionPolicy
from strategy.signals import _session_levels, evaluate_gates, TradeIntent
from strategy.scenarios import ScenarioDecision

ET = ZoneInfo("America/New_York")


def d1():
    idx = pd.date_range("2024-01-01", periods=60, freq="B", tz=ET)
    return pd.DataFrame({
        "open": 100., "high": 101., "low": 99., "close": 100.,
        "volume": 1000000, "atr14": 2.0, "sma50": 100.,
    }, index=idx)


def test_m5_uses_frozen_morning_levels_for_room_r_and_no_new_daily_recomputation():
    d = d1()
    session = date(2024, 4, 1)
    at = datetime(2024, 4, 1, 11, 0, tzinfo=ET)
    source = Level(price=100., kind="support", touches=3, strength=4,
                   valid_from=date(2024, 2, 1))
    next_resistance = Level(price=115., kind="resistance", touches=3,
                            strength=4, valid_from=date(2024, 2, 1))
    original = (source, next_resistance)
    market = MarketData("AAPL", d, session_levels=original)
    # The accepted levels are the immutable morning snapshot even when D1
    # source data would otherwise be recomputed by _session_levels.
    assert _session_levels(market, at, StrategyConfig(), session) == original
    decision = ScenarioDecision("AAPL", session, at, source, "bounce", "long")
    intent = TradeIntent("AAPL", session, at, "long", "bounce",
                         100., 100., 99.5, 0.5, 10, 3.0, None)
    gates = evaluate_gates(intent, decision, market, at, StrategyConfig())
    assert gates["room_at_least_4r"].passed is True


def test_known_empty_morning_levels_do_not_reconstruct_unverified_levels():
    market = MarketData("AAPL", d1(), session_levels=())
    at = datetime(2024, 4, 1, 11, 0, tzinfo=ET)
    assert _session_levels(market, at, StrategyConfig(), at.date()) == ()


def test_entry_windows_consistently_normalize_utc_to_new_york():
    p = SessionPolicy(StrategyConfig())
    ny = datetime(2024, 2, 5, 11, 0, tzinfo=ET)
    utc = ny.astimezone(timezone.utc)
    assert p.is_entry_allowed("breakout", ny)[0] is True
    assert p.is_entry_allowed("breakout", utc)[0] is True


def test_missing_timezone_cannot_approve_entry():
    p = SessionPolicy(StrategyConfig())
    assert p.is_entry_allowed("breakout", datetime(2024, 2, 5, 11, 0))[0] is False


def test_marketdata_refuses_naive_asof_timestamps():
    # Naive timestamps are ambiguous at DST transitions. Do not silently
    # assume UTC or exchange time when evaluating a past-bar decision.
    from pytest import raises
    frame = d1()
    market = MarketData("AAPL", frame, pd.DataFrame())
    at = datetime(2024, 4, 1, 11, 0)
    with raises(ValueError):
        market.d1_asof(at)
    with raises(ValueError):
        market.m5_asof(at)


def test_marketdata_et_and_utc_asof_same_closed_d1():
    frame = d1()
    market = MarketData("AAPL", frame)
    at = datetime(2024, 4, 1, 11, 0, tzinfo=ET)
    pd.testing.assert_frame_equal(market.d1_asof(at),
                                  market.d1_asof(at.astimezone(timezone.utc)))


def test_daylight_saving_window_uses_new_york_clock():
    p = SessionPolicy(StrategyConfig())
    et_summer = datetime(2024, 7, 1, 10, 45, tzinfo=ET)
    assert p.is_entry_allowed("breakout", et_summer)[0] is True
    assert p.is_entry_allowed("breakout", et_summer.astimezone(timezone.utc))[0] is True


def test_overnight_close_is_not_entry_window():
    p = SessionPolicy(StrategyConfig())
    at = datetime(2024, 2, 5, 3, 0, tzinfo=ET)
    assert p.is_entry_allowed("breakout", at)[0] is False
