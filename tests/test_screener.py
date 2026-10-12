"""Native Fundamental Universe prefilter and D1 eligibility contract tests.

Pure Python tests validate selection policy. Actual LEAN subscriptions and
indicator event delivery still require a LEAN engine integration smoke test.
"""
from dataclasses import dataclass
from math import nan, inf
from pathlib import Path

from strategy.config import StrategyConfig
from strategy.screener import (
    select_liquid_fundamentals, passes_gerchik_screener,
)


@dataclass(frozen=True)
class SymbolFake:
    value: str


@dataclass
class FundamentalFake:
    symbol: SymbolFake
    price: float
    volume: float
    dollar_volume: float
    has_fundamental_data: bool = True


def candidate(symbol, price=20., volume=1_000_000., dollar_volume=40_000_000.,
              has_fundamental_data=True):
    return FundamentalFake(SymbolFake(symbol), price, volume, dollar_volume,
                           has_fundamental_data)


def test_native_universe_filter_rejects_invalid_fields_but_not_single_day_volume_dip():
    cfg = StrategyConfig()
    records = [
        candidate("GOOD", 10, 500_000, 20_000_000),
        candidate("LOW_PRICE", 5, 800_000, 40_000_000),
        candidate("LOW_SHARES", 30, 499_999, 41_000_000),
        candidate("NO_FUND", 30, 1_000_000, 42_000_000, False),
        candidate("BAD_PRICE", nan, 1_000_000, 42_000_000),
        candidate("BAD_VOLUME", 30, inf, 42_000_000),
        candidate("BAD_DOLLARS", 30, 1_000_000, nan),
    ]
    selected = select_liquid_fundamentals(records, cfg)
    assert [s.value for s in selected] == ["LOW_SHARES", "GOOD"]
    # The prior-day 499,999 share dip does not prove the 20-day SMA <500k.
    # Stage-2 native D1 SMA must make that decision.


def test_20_day_qualified_stock_survives_one_low_volume_day():
    cfg = StrategyConfig()
    item = candidate("SURVIVES", price=40, volume=100_000,
                     dollar_volume=4_000_000)
    assert select_liquid_fundamentals([item], cfg) == [item.symbol]
    assert passes_gerchik_screener(40, 2.0, 650_000, cfg)


def test_universe_prefilter_sorted_by_dollar_volume_and_capped():
    cfg = StrategyConfig()
    records = [
        candidate("B", dollar_volume=10_000_000),
        candidate("C", dollar_volume=20_000_000),
        candidate("A", dollar_volume=20_000_000),
    ]
    assert [s.value for s in select_liquid_fundamentals(records, cfg)] == [
        "A", "C", "B"]
    cfg = StrategyConfig(screener_candidate_limit=2)
    assert [s.value for s in select_liquid_fundamentals(records, cfg)] == [
        "A", "C"]


def test_gerchik_second_stage_uses_native_d1_atr_and_20day_volume():
    cfg = StrategyConfig()
    assert passes_gerchik_screener(5.01, 1.0, 500_000, cfg)
    assert not passes_gerchik_screener(5, 1.0, 500_000, cfg)
    assert not passes_gerchik_screener(10, .999, 500_000, cfg)
    assert not passes_gerchik_screener(10, 1.0, 499_999, cfg)


def test_missing_nan_and_zero_indicators_reject():
    cfg = StrategyConfig()
    for value in (None, 0, -1, nan, inf, -inf, "invalid"):
        assert not passes_gerchik_screener(20, value, 800_000, cfg)
        assert not passes_gerchik_screener(20, 2.0, value, cfg)
        assert not passes_gerchik_screener(value, 2.0, 800_000, cfg)


def test_screener_only_uses_official_lean_market_and_indicator_apis():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "self.add_universe(self._select_screen_universe)" in src
    assert "def on_securities_changed(" in src
    assert "def _on_m5(" in src
    assert "AverageTrueRange(" in src
    assert "SimpleMovingAverage(self.cfg.volume_lookback_days)" in src
    assert "self.history[TradeBar](" in src
    assert "self._refresh_screen_watchlist()" in src
    assert "self.screen_watchlist = " in src
    assert "self.universe_settings.resolution = (" in src
    assert "Resolution.SECOND if self._tvx_seconds_enabled" in src
    assert "else Resolution.MINUTE" in src
    assert "anchor, (Resolution.SECOND if self._tvx_seconds_enabled" in src
    assert "else Resolution.MINUTE), fill_forward=False," in src
    assert "max_results=limit" in src
    # Current native research basis: RAW subscriptions in BOTH Minute
    # and Second modes, with SCALED_RAW as-of native D1 warmup.
    # The previous SEC-only RAW branch was removed in the Oct-12 fix.
    assert "self._equity_normalization_mode = DataNormalizationMode.RAW" in src
    assert "data_normalization_mode=DataNormalizationMode.SCALED_RAW" in src
    assert "self._tvx_normalization_mode" not in src
    assert "else DataNormalizationMode.SPLIT_ADJUSTED" not in src
    assert "data_normalization_mode=self._equity_normalization_mode).symbol" in src
    assert "self._native_exit_enabled = False" in src
    assert not any(x in src for x in (
        "self.market_order(", "self.limit_order(",
        "self.bracket_order(", "OrderManager("))


def test_second_mode_cap_is_explicit_without_changing_default_screener():
    cfg = StrategyConfig(screener_candidate_limit=50, screener_watchlist_limit=10)
    records = [
        candidate(f"T{i:02d}", dollar_volume=100_000_000 - i * 1_000)
        for i in range(45)
    ]
    assert len(select_liquid_fundamentals(records, cfg)) == 45
    assert len(select_liquid_fundamentals(
        records, cfg, max_results=cfg.screener_watchlist_limit)) == 10
    assert [s.value for s in select_liquid_fundamentals(
        records, cfg, max_results=2)] == ["T00", "T01"]
    for bad in (0, -1, True, 1.5):
        import pytest
        with pytest.raises(ValueError):
            select_liquid_fundamentals(records, cfg, max_results=bad)
