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


def test_no_orders_market_data_or_median_price_selection():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "strategy" /
           "levels.py").read_text(encoding="utf-8")
    src = src.split("# QWCT 3.5: standalone read-only inspection", 1)[1]
    for forbidden in ("market_order(", "limit_order(", "stop_market_order(",
                      "qb.history(", "Resolution.MINUTE", "Resolution.SECOND",
                      "Resolution.TICK", "ATR(", "np.median("):
        assert forbidden not in src, forbidden
