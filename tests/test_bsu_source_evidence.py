"""Pure checks for causal RAW D1 source-price evidence; no LEAN or trades."""
from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.levels import frozen_mirror_source_evidence

ET = ZoneInfo("America/New_York")


def _sample():
    idx = pd.date_range("2024-04-01", periods=24, freq="B", tz=ET)
    rows = [{"open": 95., "high": 99., "low": 90., "close": 96.} for _ in idx]
    rows[4].update(open=99., high=105., close=101.)
    rows[8]["high"] = 105.  # independently observed repeated historical high
    rows[12].update(open=99., high=104., close=101.)
    rows[17].update(open=106., high=107., low=105., close=106.)
    rows[18].update(open=105., high=107., low=103., close=106.)
    d1 = pd.DataFrame(rows, index=idx)
    lvl = SimpleNamespace(kind="mirror", source="swing_cluster", first_idx=4,
                          last_idx=12, price=104.5, valid_from=idx[16].date())
    trace = {"status": "PROXY_VERIFIED", "original_kind": "resistance",
             "valid_from": str(lvl.valid_from)}
    return d1, lvl, trace, idx


def _run(d1, level, trace, **kwargs):
    kwargs = {"session": date(2024, 5, 6), "tick_size": 0.01, "swing_k": 3} | kwargs
    return frozen_mirror_source_evidence(d1, level, trace, **kwargs)


def test_first_and_last_sources_are_not_approved():
    d1, level, trace, idx = _sample()
    out = _run(d1, level, trace)
    assert [(x.label, x.price) for x in out] == [
        ("FIRST_SWING", 105.), ("LAST_SWING", 104.)]
    assert all(x.status == "AUTHOR_UNVERIFIED" and not x.can_trade for x in out)
    assert idx[8].date() in out[0].original_same_wick_dates
    assert idx[17].date() in out[0].mirror_exact_wick_dates
    assert idx[18].date() in out[0].mirror_pierce_dates
    assert out[0].source_date == idx[4].date()
    assert all(x.price != level.price for x in out)  # median not selected


def test_asof_rejects_target_day_candle():
    d1, level, trace, idx = _sample()
    with pytest.raises(ValueError, match="NONCAUSAL"):
        _run(d1, level, trace, session=idx[-1].date())


def test_trace_cannot_approve_itself():
    d1, level, trace, _ = _sample()
    trace["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="MIRROR_CHRONOLOGY_NOT_VERIFIED"):
        _run(d1, level, trace)


def test_off_grid_does_not_manufacture_exact_touches():
    d1, level, trace, idx = _sample()
    d1.loc[idx[4], "high"] = 105.005
    d1.loc[idx[8], "high"] = 105.005
    out = _run(d1, level, trace)
    assert out[0].current_grid == "OFF_GRID"
    assert not out[0].mirror_exact_wick_dates
    assert out[0].status == "AUTHOR_UNVERIFIED"


def test_same_date_native_bars_fail_closed():
    d1, level, trace, idx = _sample()
    ix = list(d1.index)
    ix[7] = ix[6] + pd.Timedelta(hours=1)
    d1.index = pd.DatetimeIndex(ix)
    with pytest.raises(ValueError, match="NONCAUSAL_OR_DUPLICATE_D1_DATE"):
        _run(d1, level, trace)


def test_corrupt_ohlc_fails_closed():
    d1, level, trace, idx = _sample()
    d1.loc[idx[6], "low"] = 150.
    with pytest.raises(ValueError, match="INVALID_RAW_D1_OHLC_SHAPE"):
        _run(d1, level, trace)


def test_original_swing_and_available_from_are_verified():
    d1, level, trace, idx = _sample()
    level.last_idx = 13  # not a confirmed old-side high
    with pytest.raises(ValueError, match="SOURCE_IS_NOT_CONFIRMED_SWING"):
        _run(d1, level, trace)
    level.last_idx = 12
    level.valid_from = idx[15].date()  # last pivot confirmed on day 15
    trace["valid_from"] = str(level.valid_from)
    with pytest.raises(ValueError, match="SOURCE_CONFIRMED_AFTER_LEVEL_IS_VALID"):
        _run(d1, level, trace)



def test_one_bar_mirror_wick_reclaim_is_different_from_close_through():
    d1, level, trace, idx = _sample()
    out = _run(d1, level, trace)[0]
    # At 18: low breaches FIRST support at 105, but close recovers above.
    assert idx[18].date() in out.mirror_wick_reclaim_dates
    assert idx[18].date() not in out.mirror_close_through_dates
    assert idx[18].date() in out.mirror_range_cross_dates
    # A bar that simply stays wholly below the reference is NOT a bounce.
    assert idx[16].date() in out.mirror_close_through_dates
    assert idx[16].date() not in out.mirror_wick_reclaim_dates
    assert idx[16].date() not in out.mirror_range_cross_dates
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_original_resistance_overshoot_and_return_is_not_exact_touch():
    d1, level, trace, idx = _sample()
    # This historical wick crosses resistance, but its CLOSE is below.
    d1.loc[idx[8], "high"] = 106.
    out = _run(d1, level, trace)[0]
    assert idx[8].date() in out.original_wick_reclaim_dates
    assert idx[8].date() not in out.original_same_wick_dates
    assert out.status == "AUTHOR_UNVERIFIED"


def test_one_bar_mirror_close_through_not_mislabeled_as_reclaim():
    d1, level, trace, idx = _sample()
    d1.loc[idx[19], ["open","high","low","close"]] = [104.,107.,103.,104.]
    out = _run(d1, level, trace)[0]
    assert idx[19].date() in out.mirror_close_through_dates
    assert idx[19].date() not in out.mirror_wick_reclaim_dates
    assert idx[19].date() in out.mirror_range_cross_dates
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_mirror_two_closed_bar_reentry_requires_second_d1_close():
    d1, level, trace, idx = _sample()
    # First session CLOSES below old resistance -> new support,
    # next session CLOSES back above it; neither is BPU1 by itself.
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [106., 107., 103., 104.]
    d1.loc[idx[20], ["open", "high", "low", "close"]] = [104., 107., 103., 106.]
    out = _run(d1, level, trace)[0]
    assert idx[19].date() in out.mirror_close_through_dates
    assert idx[19].date() not in out.mirror_two_bar_reclaim_dates
    assert idx[20].date() in out.mirror_two_bar_reclaim_dates
    # The seed contains an earlier independent close reentry as well.
    assert out.mirror_two_bar_reclaim_dates[-1] == idx[20].date()
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_original_two_bar_reentry_before_new_mirror_role():
    d1, level, trace, idx = _sample()
    # The confirmed source swings still have the same original highs.
    level.valid_from = idx[20].date()
    trace["valid_from"] = str(level.valid_from)
    d1.loc[idx[17], ["open", "high", "low", "close"]] = [103., 107., 101., 106.]
    d1.loc[idx[18], ["open", "high", "low", "close"]] = [106., 107., 101., 102.]
    out = _run(d1, level, trace)[0]
    assert out.original_two_bar_reclaim_dates == (idx[18].date(),)
    assert not out.mirror_two_bar_reclaim_dates
    assert out.status == "AUTHOR_UNVERIFIED"


def test_role_transition_cannot_fake_two_bar_mirror_reentry():
    d1, level, trace, idx = _sample()
    level.valid_from = idx[19].date()
    trace["valid_from"] = str(level.valid_from)
    # Prior close below line happened BEFORE mirror effective date.
    d1.loc[idx[18], ["open", "high", "low", "close"]] = [105., 107., 103., 104.]
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [104., 107., 103., 106.]
    out = _run(d1, level, trace)[0]
    assert idx[19].date() not in out.mirror_two_bar_reclaim_dates
    assert idx[19].date() not in out.original_two_bar_reclaim_dates


def test_original_support_to_mirror_resistance_symmetric_two_bar():
    d1, level, trace, idx = _sample()
    orig = d1[["open", "high", "low", "close"]].copy()
    d1["open"] = 200 - orig["open"]
    d1["high"] = 200 - orig["low"]
    d1["low"] = 200 - orig["high"]
    d1["close"] = 200 - orig["close"]
    level.price = 95.5
    trace["original_kind"] = "support"
    # Break above new resistance and close back below.
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [94., 97., 93., 96.]
    d1.loc[idx[20], ["open", "high", "low", "close"]] = [96., 97., 93., 94.]
    out = _run(d1, level, trace)[0]
    assert out.price == 95.
    assert idx[20].date() in out.mirror_two_bar_reclaim_dates
    # The seed contains an earlier independent close reentry as well.
    assert out.mirror_two_bar_reclaim_dates[-1] == idx[20].date()
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_no_orders_market_data_or_median_price_selection():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "strategy" /
           "levels.py").read_text(encoding="utf-8")
    src = src.split("# QWCT 3.5: standalone read-only inspection", 1)[1]
    for forbidden in ("market_order(", "limit_order(", "stop_market_order(",
                      "qb.history(", "Resolution.MINUTE", "Resolution.SECOND",
                      "Resolution.TICK", "ATR(", "np.median("):
        assert forbidden not in src, forbidden
