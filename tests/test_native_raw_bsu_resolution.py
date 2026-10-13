"""RAW D1 BSU reconciliation regression: read-only evidence, never orders."""
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from strategy.bsu_bridge import (
    create_bsu_research_observer, resolve_raw_bsu_evidence)
from strategy.config import StrategyConfig
from tests.test_bsu_native_bridge import evidence


def sample():
    decision, daily = evidence(
        kind="resistance", side="short", level_price=502.57439794)
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
        confirm(decision, daily, bars[1:])
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
