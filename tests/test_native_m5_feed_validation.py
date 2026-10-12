"""Fixed native-shaped inputs only; this is NOT a LEAN Cloud backtest."""
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.native_m5_validation import validate_m5_tradebar
from strategy.m5_runtime import process_m5

ET = ZoneInfo("America/New_York")


def bar(**changes):
    at = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    values = dict(open=100., high=100.5, low=99.5, close=100.1,
                  volume=150., is_fill_forward=False,
                  time=at - timedelta(minutes=5), end_time=at,
                  period=timedelta(minutes=5))
    values.update(changes)
    return SimpleNamespace(**values)


def test_valid_completed_m5_tradebar_is_accepted_for_research():
    accepted, reason = validate_m5_tradebar(
        bar(), datetime(2024, 1, 2, 9, 35, tzinfo=ET))
    assert accepted is True
    assert reason == "M5_NATIVE_VALIDATED_SHAPE"


@pytest.mark.parametrize("changes,reason", [
    ({"open": 101.}, "M5_OHLC_INVALID"),
    ({"high": 99.}, "M5_OHLC_INVALID"),
    ({"low": 101.}, "M5_OHLC_INVALID"),
    ({"close": float("nan")}, "M5_OHLCV_NOT_FINITE"),
    ({"volume": -1}, "M5_NO_OBSERVED_TRADES"),
    ({"volume": 0}, "M5_NO_OBSERVED_TRADES"),
    ({"volume": float("inf")}, "M5_OHLCV_NOT_FINITE"),
    ({"volume": "bad"}, "M5_OHLCV_NOT_NUMERIC"),
    ({"is_fill_forward": True}, "M5_FILL_FORWARD_UNVERIFIED"),
])
def test_invalid_m5_shape_or_untraded_data_never_validates(changes, reason):
    accepted, actual = validate_m5_tradebar(
        bar(**changes), datetime(2024, 1, 2, 9, 35, tzinfo=ET))
    assert accepted is False
    assert actual == reason


@pytest.mark.parametrize("end,reason", [
    (datetime(2024, 1, 2, 9, 35), "M5_END_TIMESTAMP_UNVERIFIED"),
    (datetime(2024, 1, 2, 9, 36, tzinfo=ET), "M5_PERIOD_BOUNDARY_INVALID"),
    (datetime(2024, 1, 2, 9, 35, 30, tzinfo=ET), "M5_PERIOD_BOUNDARY_INVALID"),
])
def test_m5_endtime_must_be_native_aware_aligned(end, reason):
    accepted, actual = validate_m5_tradebar(bar(), end)
    assert accepted is False
    assert actual == reason




@pytest.mark.parametrize("changes,reason", [
    ({"period": timedelta(minutes=1)}, "M5_SOURCE_PERIOD_NOT_FIVE_MINUTES"),
    ({"period": timedelta(minutes=10)}, "M5_SOURCE_PERIOD_NOT_FIVE_MINUTES"),
    ({"period": None}, "M5_SOURCE_PERIOD_MISSING"),
    ({"time": datetime(2024, 1, 2, 9, 31, tzinfo=ET)},
     "M5_SOURCE_START_END_INCONSISTENT"),
])
def test_native_m5_rejects_wrong_period_even_if_endtime_is_0935(changes, reason):
    # A 09:34-09:35 M1 candle is NOT a real 09:30-09:35 M5 bar.
    accepted, actual = validate_m5_tradebar(
        bar(**changes), datetime(2024, 1, 2, 9, 35, tzinfo=ET))
    assert accepted is False
    assert actual == reason


def test_native_m5_rejects_missing_source_start_datetime():
    x = bar()
    del x.time
    accepted, reason = validate_m5_tradebar(
        x, datetime(2024, 1, 2, 9, 35, tzinfo=ET))
    assert not accepted
    assert reason == "M5_SOURCE_PERIOD_OR_CHRONOLOGY_UNVERIFIED"
