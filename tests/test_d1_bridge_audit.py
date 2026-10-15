"""Pure read-only D1 bridge tests. Not a substitute for native LEAN."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.d1_bridge_audit import evaluate_d1, _status
from strategy.levels import Level
from strategy import d1_bridge_audit as audit


ET = ZoneInfo("America/New_York")


def et(value):
    t = pd.Timestamp(value)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


PROOF = (
    "AAPL", "2024-04-03 12:20", "long", 170.28,
    "2024-03-15T16:00:00-04:00", "2024-03-20T16:00:00-04:00",
    .01, ("2024-04-03 12:15", 170.36, 170.45, 170.28,
          170.41, 500.0),
    (170.41, 170.44, 170.345, 170.41, 900.0),
    169.46, .164,
)


def d1_rows():
    days = pd.bdate_range(end="2024-04-02", periods=180, tz=ET)
    base = pd.DataFrame(index=days)
    base["open"] = 172.0
    base["high"] = 174.0
    base["low"] = 171.0
    base["close"] = 173.0
    base["volume"] = 2000000.0
    base["atr14"] = 2.0
    base["sma50"] = [168 + 3*i/179 for i in range(180)]
    base["bar_end"] = days + pd.Timedelta(hours=16)
    orig = base.index.get_loc(pd.Timestamp("2024-03-15", tz=ET))
    base.loc[base.index[orig], "low"] = 170.28
    return base, orig


def fake_level(original_idx, price=175.0, source="swing_cluster"):
    return Level(price=price, kind="support", touches=2,
                 strength=2.0, first_idx=original_idx,
                 valid_from=date(2024, 3, 21), source=source)


def test_new_pphl_pivot_never_promoted_to_original_two_touch_level(monkeypatch):
    d1, idx = d1_rows()
    monkeypatch.setattr(audit, "levels_for_session", lambda *args: [
        fake_level(idx, price=175.0)])
    result = evaluate_d1(d1, PROOF, StrategyConfig(), et)
    assert result["origin"] == "PASS"
    assert result["cluster"] == "FAIL"
    assert result["model"] == "UNKNOWN"
    assert result["trend"] == "PASS"
    assert result["room4r"] == "PASS"
    assert result["room3r"] == "PASS"
    assert result["risk"] > 0


def test_matching_two_touch_source_is_causal_exact_origin(monkeypatch):
    d1, idx = d1_rows()
    matching = fake_level(idx, price=170.28)
    barrier = fake_level(idx, price=174.99)
    monkeypatch.setattr(audit, "levels_for_session", lambda *args: [
        matching, barrier])
    result = evaluate_d1(d1, PROOF, StrategyConfig(), et)
    assert result["origin"] == "PASS"
    assert result["cluster"] == "PASS"
    assert result["room_r"] is not None
    # Theoretical detector stop/entry ONLY; not observed fills.
    assert result["entry"] == pytest.approx(170.44)
    assert result["stop"] == pytest.approx(169.46)


def test_missing_barrier_is_unknown_not_approved(monkeypatch):
    d1, _ = d1_rows()
    monkeypatch.setattr(audit, "levels_for_session", lambda *args: [])
    x = evaluate_d1(d1, PROOF, StrategyConfig(), et)
    assert x["room4r"] == x["room3r"] == "UNKNOWN"
    assert x["room_r"] is None
    assert x["cluster"] == "FAIL"


def test_unknown_sma_never_passes_trend(monkeypatch):
    d1, _ = d1_rows()
    d1["sma50"] = float("nan")
    monkeypatch.setattr(audit, "levels_for_session", lambda *args: [])
    x = evaluate_d1(d1, PROOF, StrategyConfig(), et)
    assert x["trend"] == "UNKNOWN"


def test_future_daily_is_rejected_even_when_other_data_looks_good(monkeypatch):
    d1, _ = d1_rows()
    d1.loc[d1.index[-1], "bar_end"] = et("2024-04-03 16:00")
    with pytest.raises(ValueError, match="non-as-of"):
        evaluate_d1(d1, PROOF, StrategyConfig(), et)


def test_source_mismatch_cannot_pass_provenance(monkeypatch):
    d1, _ = d1_rows()
    monkeypatch.setattr(audit, "levels_for_session", lambda *args: [])
    wrong = list(PROOF)
    wrong[3] = 171.50
    assert evaluate_d1(d1, tuple(wrong), StrategyConfig(), et)["origin"] == "FAIL"


def test_cloud_wiring_and_no_order_path_added():
    app = (Path(__file__).parents[1] / "research" /
           "bsu_cloud" / "main.py").read_text(encoding="utf-8")
    mod = (Path(__file__).parents[1] / "strategy" /
           "d1_bridge_audit.py").read_text(encoding="utf-8")
    assert "from strategy.d1_bridge_audit import premarket_audit" in app
    assert "BSU D1 BRIDGE" in app
    assert "Resolution.DAILY" in mod
    assert "data_normalization_mode=DataNormalizationMode.RAW" in mod
    assert "levels_for_session" in mod and "global_trend" in mod
    assert "next_level" in mod and "SimpleMovingAverage" in mod
    assert len(app.encode("utf-8")) < 32_000
    assert len(mod.encode("utf-8")) < 32_000
    for cmd in ("market_order(", "limit_order(", "set_holdings(",
                "self.buy(", "self.sell("):
        assert cmd not in mod
