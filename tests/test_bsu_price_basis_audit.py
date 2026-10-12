"""Exact as-of native RAW vs SCALED_RAW BSU pivot diagnostic.

Pure native-shaped fixtures are source regression checks, not Cloud data.
"""
from datetime import datetime, timedelta, date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.bsu_bridge import audit_bsu_price_basis

ET = ZoneInfo("America/New_York")
SESSION = date(2024, 1, 9)


def samples():
    a = pd.Timestamp("2024-01-03", tz=ET)
    b = pd.Timestamp("2024-01-08", tz=ET)
    scaled = pd.DataFrame(
        {"high": [502.5744, 498.0122], "low": [491.11, 490.03],
         "close": [495.14, 495.2188],
         "bar_end": [a+pd.Timedelta(hours=16), b+pd.Timedelta(hours=16)]},
        index=pd.DatetimeIndex([a, b]))
    level = SimpleNamespace(first_idx=0, price=502.5744,
                            kind="resistance", source="swing_cluster")
    decision = SimpleNamespace(
        level=level, session=SESSION, symbol="NVDA",
        decided_at=datetime(2024, 1, 9, 9, 29, tzinfo=ET))
    bars = [
        SimpleNamespace(time=a.to_pydatetime(),
                        end_time=(a+pd.Timedelta(hours=16)).to_pydatetime(),
                        high=502.57, low=491.11, close=495.14),
        SimpleNamespace(time=b.to_pydatetime(),
                        end_time=(b+pd.Timedelta(hours=16)).to_pydatetime(),
                        high=498.01, low=490.03, close=495.22),
    ]
    return decision, scaled, bars


def test_real_raw_native_tick_vs_fractional_scaled_pivot_not_cluster():
    decision, d1, bars = samples()
    diagnostic = audit_bsu_price_basis(
        decision, d1, 0.01, bars, pd.Timestamp)
    assert "QWCT BSU BASIS NVDA" in diagnostic
    assert "pivot_date=2024-01-03" in diagnostic
    assert "field=high" in diagnostic
    assert "raw=502.57000000" in diagnostic
    assert "scaled=502.57440000" in diagnostic
    assert "cluster=502.57440000" in diagnostic
    assert "raw_off=0.00000000" in diagnostic
    assert "scaled_off=0.00440000" in diagnostic
    assert "last=2024-01-08" in diagnostic
    assert "raw_close=495.220000" in diagnostic
    assert "OBSERVATION ONLY / NO ORDERS" in diagnostic
    assert diagnostic.count("factor_scaled/raw=") == 1


def test_missing_or_duplicate_raw_pivot_is_not_certified():
    decision, d1, bars = samples()
    for incomplete in ([], bars[1:], [bars[0], bars[0], bars[1]]):
        with pytest.raises(ValueError, match="missing or duplicated"):
            audit_bsu_price_basis(
                decision, d1, .01, incomplete, pd.Timestamp)


def test_future_or_unclosed_history_is_rejected_before_price_use():
    decision, d1, bars = samples()
    future = SimpleNamespace(
        time=datetime(2024, 1, 9, 9, 25, tzinfo=ET),
        end_time=datetime(2024, 1, 9, 16, tzinfo=ET),
        high=900.0, low=50.0, close=900.0)
    with pytest.raises(ValueError, match="future D1"):
        audit_bsu_price_basis(
            decision, d1, .01, [*bars, future], pd.Timestamp)


def test_native_end_time_disagreement_is_not_pivot_parity():
    decision, d1, bars = samples()
    bars[0].end_time += timedelta(minutes=5)
    with pytest.raises(ValueError, match="EndTime mismatch"):
        audit_bsu_price_basis(decision, d1, .01, bars, pd.Timestamp)


def test_source_only_one_2024_01_02_bounce_probe_and_free_package():
    from pathlib import Path
    from tools.package_quantconnect_free import build_sources

    root = Path(__file__).resolve().parents[1]
    main = (root / "main.py").read_text(encoding="utf-8")
    assert "from strategy.bsu_bridge import create_bsu_research_observer, audit_bsu_price_basis" in main
    assert 'self._session_date.isoformat() == "2024-01-02"' in main
    assert "data_normalization_mode=DataNormalizationMode.RAW)" in main
    assert "self.log(audit_bsu_price_basis(" in main
    assert main.index("create_bsu_research_observer(") < main.index("audit_bsu_price_basis(")
    assert "self._native_exit_enabled = False" in main
    assert not any(k in main for k in ("self.market_order(", "self.limit_order(", "self.bracket_order("))
    sources = build_sources(root)
    assert len(sources) == 24
    assert "audit_bsu_price_basis" in sources["main.py"]
    assert "def audit_bsu_price_basis(" in sources["strategy/bsu_bridge.py"]
