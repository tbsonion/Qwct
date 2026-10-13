"""RAW D1 BSU reconciliation regression: read-only evidence, never orders."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.bsu_bridge import (
    create_bsu_research_observer, resolve_raw_bsu_evidence)
from strategy.config import StrategyConfig
from strategy.levels import Level
from strategy.scenarios import ScenarioDecision


def sample():
    et = ZoneInfo("America/New_York")
    idx = pd.date_range("2024-01-01", periods=70, freq="B", tz=et)
    daily = pd.DataFrame({
        "high": 502.57439794, "low": 490.0,
        "open": 495.0, "close": 495.22, "atr14": 12.02,
        "bar_end": [x + pd.Timedelta(hours=16) for x in idx],
    }, index=idx)
    lvl = Level(price=502.57439794, kind="resistance", touches=2,
                strength=3, first_idx=10, last_idx=20,
                formed_at=idx[20].date(), valid_from=idx[24].date(),
                source="swing_cluster")
    decision = ScenarioDecision(
        "AAPL", date(2024, 4, 15),
        datetime(2024, 4, 15, 9, 29, tzinfo=et),
        lvl, "bounce", "short", score=4)
    # NVDA 2024 shape: original raw swing 502.66, as-of scaled
    # swing 502.57439794, latest completed close equal on both bases.
    daily["high"] = 502.57439794
    daily["low"] = 490.00
    daily["open"] = 495.00
    daily["close"] = 495.22
    daily["atr14"] = 12.02
    bars = [
        SimpleNamespace(
            time=x.to_pydatetime(),
            end_time=daily.iloc[i]["bar_end"].to_pydatetime(),
            high=502.66 if i == decision.level.first_idx else 502.57,
            low=490.0, close=495.22,
            symbol="AAPL")
        for i, x in enumerate(daily.index)
    ]
    return decision, daily, bars


def confirm(decision, daily, bars):
    return resolve_raw_bsu_evidence(
        decision, daily, 0.01, bars, pd.Timestamp)


def test_native_raw_pivot_unblocks_adjusted_off_grid_only_with_provenance():
    decision, daily, bars = sample()
    # Old SCALED_RAW off-tick pivot is not a native tradable extreme.
    blocked, why = create_bsu_research_observer(
        decision, daily, 0.01, StrategyConfig())
    assert blocked is None and "tick grid" in why
    evidence_raw = confirm(decision, daily, bars)
    assert evidence_raw.origin_price == 502.66
    assert evidence_raw.scaled_origin == pytest.approx(502.57439794)
    link, why = create_bsu_research_observer(
        decision, daily, 0.01, StrategyConfig(),
        raw_evidence=evidence_raw, require_raw=True)
    assert link is not None, why
    assert link.origin_price == 502.66
    assert link.cluster_price == pytest.approx(502.57439794)
    assert link.detector.state.level_price == 502.66
    assert "native RAW" in why
    assert link.detector.state.can_submit is False


def test_cloud_path_never_falls_back_to_scaled_without_raw_proof():
    decision, daily, _ = sample()
    link, why = create_bsu_research_observer(
        decision, daily, .01, StrategyConfig(), require_raw=True)
    assert link is None
    assert "RAW" in why


def test_raw_missing_origin_latest_mismatch_and_offgrid_are_blocked():
    decision, daily, bars = sample()
    with pytest.raises(ValueError, match="missing or duplicated"):
        confirm(decision, daily, [b for i, b in enumerate(bars)
                                  if i != decision.level.first_idx])
    bars[-1].close += .02
    with pytest.raises(ValueError, match="latest close"):
        confirm(decision, daily, bars)
    bars[-1].close -= .02
    bars[decision.level.first_idx].high = 502.665
    with pytest.raises(ValueError, match="tick grid"):
        confirm(decision, daily, bars)


def test_future_duplicate_timestamp_and_symbol_mismatch_block():
    decision, daily, bars = sample()
    with pytest.raises(ValueError, match="missing or duplicated"):
        confirm(decision, daily, [bars[0], bars[0], *bars[1:]])
    bars[decision.level.first_idx].end_time += timedelta(minutes=1)
    with pytest.raises(ValueError, match="EndTime mismatch"):
        confirm(decision, daily, bars)
    bars[decision.level.first_idx].end_time -= timedelta(minutes=1)
    bars[0].symbol = "MSFT"
    with pytest.raises(ValueError, match="symbol mismatch"):
        confirm(decision, daily, bars)



class LeanStyleSymbol:
    """Mock an official LEAN Symbol with a ticker and a serialized SID."""
    def __init__(self, ticker, sid="R735QTJ8XC9X"):
        self.value = ticker
        self.id = sid

    def __str__(self):
        return f"{self.value} {self.id}"


def test_real_lean_symbol_value_used_instead_of_sid_string():
    decision, daily, bars = sample()
    for bar in bars:
        bar.symbol = LeanStyleSymbol("AAPL")
    # LEAN string repr may include SID even when .value matches the ticker.
    assert str(bars[0].symbol) != decision.symbol
    raw = confirm(decision, daily, bars)
    assert raw.origin_price == pytest.approx(502.66)
    link, why = create_bsu_research_observer(
        decision, daily, .01, StrategyConfig(),
        raw_evidence=raw, require_raw=True)
    assert link is not None, why
    assert link.detector.state.can_submit is False


def test_lean_symbol_value_mismatch_still_blocks():
    decision, daily, bars = sample()
    bars[0].symbol = LeanStyleSymbol("MSFT")
    with pytest.raises(ValueError, match="symbol mismatch"):
        confirm(decision, daily, bars)


def test_untyped_symbol_without_ticker_value_fails_closed():
    decision, daily, bars = sample()
    bars[0].symbol = SimpleNamespace(id="AAPL R735QTJ8XC9X")
    with pytest.raises(ValueError, match="symbol mismatch"):
        confirm(decision, daily, bars)

def test_historical_split_sized_raw_pivot_is_not_silently_relabelled():
    decision, daily, bars = sample()
    bars[decision.level.first_idx].high = 5026.60
    raw = confirm(decision, daily, bars)
    link, reason = create_bsu_research_observer(
        decision, daily, .01, StrategyConfig(),
        raw_evidence=raw, require_raw=True)
    assert link is None
    assert "cluster" in reason.lower()


def test_real_main_uses_raw_once_per_bounce_with_orders_disabled():
    from pathlib import Path
    from tools.package_quantconnect_free import build_sources

    repo = Path(__file__).resolve().parents[1]
    main = (repo / "main.py").read_text(encoding="utf-8")
    assert "resolve_raw_bsu_evidence(" in main
    assert "raw_evidence=raw_evidence, require_raw=True" in main
    assert "data_normalization_mode=DataNormalizationMode.RAW)" in main
    assert "self._native_exit_enabled = False" in main
    assert not any(k in main for k in (
        "self.market_order(", "self.limit_order(", "self.bracket_order("))
    sources = build_sources(repo)
    assert len(sources) == 24
    assert "resolve_raw_bsu_evidence" in sources["main.py"]
