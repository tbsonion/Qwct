"""A native second source must prove the entire BPU2-to-preclose interval.

These deliberately synthetic samples test the contract, not an actual
QuantConnect subscription. Tick/second data is NOT available in current
Qwct M5-only project; never manufacture it from M5 candles.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from strategy.config import StrategyConfig
from strategy.patterns_bsu import BsuDetector, Bar
from strategy.tvx_observation import NativeSecondTvxWindow

ET=ZoneInfo("America/New_York")


def native_window():
    bsu=datetime(2023,8,24,16,tzinfo=ET)
    detector=BsuDetector(StrategyConfig(),100.,"short",
                        atr_value=2.,tick_size=.01,bsu_ts=bsu)
    t=datetime(2024,1,2,10,35,tzinfo=ET)
    detector.on_bar(Bar(t,99.4,100.,99.3,99.8,"M5",100.))
    assert detector.state.phase == "bpu1"
    return detector,NativeSecondTvxWindow(detector)


def sec(at, *, high=99.99, low=99.9, close=99.95, volume=2.):
    return Bar(at,99.95,high,low,close,"SEC",volume)


def test_full_270_real_second_periods_can_only_produce_preclose_candidate():
    detector,window=native_window()
    start=detector.state.bpu1_ts
    for k in range(1,271):
        state=window.on_second(sec(start+timedelta(seconds=k)))
    assert window.count == 270
    assert state.phase == "preclose_candidate"
    assert state.preclose_seen is True
    assert state.can_submit is False
    assert state.precision == "sec_preclose_observed"
    # Later *real* completed M5 still must confirm or invalidate.
    finish=detector.on_bar(Bar(start+timedelta(minutes=5),
                       99.95,99.99,99.9,99.96,"M5",100.))
    assert finish.phase == "bpu2_confirmed"
    assert finish.can_submit is False


def test_missing_one_second_is_fail_closed_even_if_final_timestamp_matches():
    detector,window=native_window()
    start=detector.state.bpu1_ts
    for k in range(1,270):
        if k==120:
            continue
        if k==121:
            with pytest.raises(ValueError,match="gap"):
                window.on_second(sec(start+timedelta(seconds=k)))
            break
    assert detector.state.preclose_seen is False
    assert detector.state.can_submit is False


def test_zero_volume_fill_forward_is_not_native_trade_provenance():
    detector,window=native_window()
    with pytest.raises(ValueError,match="non-fill-forward"):
        window.on_second(sec(detector.state.bpu1_ts+timedelta(seconds=1),
                             volume=0.))


def test_second_data_cannot_be_mislabeled_as_closed_m5_or_tick():
    detector,window=native_window()
    start=detector.state.bpu1_ts
    with pytest.raises(ValueError):
        window.on_second(Bar(start+timedelta(seconds=1),
                             99.,100.,98.,99.,"M5",1.))


def test_wick_breaching_bpu1_extreme_in_270_second_preclose_is_invalidated():
    detector,window=native_window()
    start=detector.state.bpu1_ts
    for k in range(1,270):
        window.on_second(sec(start+timedelta(seconds=k)))
    state=window.on_second(sec(start+timedelta(seconds=270),
                           high=100.50,low=99.9,close=99.95))
    assert state.phase == "invalidated"
    assert state.can_submit is False


def test_m5_cannot_confirm_an_incompatible_sec_preclose_range():
    detector, window = native_window()
    start = detector.state.bpu1_ts
    for k in range(1, 271):
        window.on_second(sec(start + timedelta(seconds=k), high=99.99,
                             low=99.90, close=99.95))
    observed = detector.on_bar(Bar(
        start + timedelta(minutes=5), 99.95, 99.96, 99.92,
        99.95, "M5", 100.))
    assert observed.phase == "invalidated"
    assert "SEC preclose extremes" in observed.reason
    assert observed.can_submit is False


def test_sec_window_rejects_detector_state_changed_mid_bpu2():
    detector, window = native_window()
    start = detector.state.bpu1_ts
    window.on_second(sec(start + timedelta(seconds=1)))
    detector._invalidate("invalidated native upstream evidence")
    with pytest.raises(ValueError, match="no longer active"):
        window.on_second(sec(start + timedelta(seconds=2)))


def test_out_of_order_duplicate_future_second_is_rejected():
    detector,window=native_window()
    start=detector.state.bpu1_ts
    window.on_second(sec(start+timedelta(seconds=1)))
    with pytest.raises(ValueError):
        window.on_second(sec(start+timedelta(seconds=1)))
    with pytest.raises(ValueError):
        window.on_second(sec(start+timedelta(minutes=5)))
