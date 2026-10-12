"""Fixed native-shaped inputs only; this is NOT a LEAN Cloud backtest."""
from collections import Counter
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.native_m5_validation import validate_m5_tradebar
from strategy.m5_runtime import process_m5

ET = ZoneInfo("America/New_York")


def bar(**changes):
    values = dict(open=100., high=100.5, low=99.5, close=100.1,
                  volume=150., is_fill_forward=False)
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


def test_runtime_does_not_promote_zero_volume_wick_touch_to_bpu1():
    # Use the actual extracted research callback; no fake fills/orders.
    from tests.test_native_bpu_runtime_integration import AlgorithmHarness
    a = AlgorithmHarness()
    at = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    native_bar = bar(high=50.27, low=49.9, open=50., close=50.08, volume=0)
    native_bar.symbol = "NVDA"
    native_bar.end_time = at
    process_m5(a, native_bar, pd.Timestamp)
    assert a._m5_bars_seen == 0
    assert a._m5_input_rejections["M5_NO_OBSERVED_TRADES"] == 1
    assert a._symbols["NVDA"]["touch_audit"].touches == 0
    assert a._bsu_bpu1_count == 0
    assert not a.records
