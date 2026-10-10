"""Pure deterministic rule tests. NOT a profitability backtest or broker simulation."""
from datetime import datetime, date
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.features import FeatureResult, evaluate_all
import strategy.scenarios as scenario_module
from strategy.indicators import atr, global_trend, trend_direction
from strategy.levels import Level, detect_levels, levels_for_session, _native_atr, _score_level
from strategy.scenarios import ScenarioDecision, ScenarioEvaluator
from strategy.signals import GATE_IDS, build_intent


def daily(n=110, native_atr=True):
    dates = pd.bdate_range("2025-01-01", periods=n, tz="America/New_York")
    x = np.arange(n, dtype=float)
    prices = 100 + 0.06 * x + 4.0 * np.sin(x / 4)
    frame = pd.DataFrame({
        "open": prices - .15, "high": prices + 1.4,
        "low": prices - 1.4, "close": prices,
        "volume": np.full(n, 800_000.0),
        "atr14": np.r_[np.full(13, np.nan), np.full(n-13, 2.5)],
        "sma50": np.r_[np.full(49, np.nan), prices[49:] - .2],
    }, index=dates)
    if not native_atr:
        frame.drop(columns=["atr14"], inplace=True)
    return frame


def test_native_atr_only():
    d1 = daily()
    assert atr(d1, 14).iloc[-1] == pytest.approx(2.5)
    assert np.isnan(atr(d1.drop(columns=["atr14"]), 14).iloc[-1])


def test_levels_fail_closed_without_native_atr():
    cfg = StrategyConfig()
    # A missing LEAN indicator snapshot must reject cleanly, without
    # a NumPy nanmedian/empty-slice warning masquerading as research output.
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert detect_levels(daily(native_atr=False), cfg) == []


def test_level_strength_never_substitutes_bar_range_for_missing_native_atr():
    cfg = StrategyConfig()
    d1 = daily()
    # Make the price range deliberately small, so the old fallback
    # (substitute the candle range for missing ATR) awarded false strength.
    for column, value in (("open", 100.0), ("high", 100.1),
                          ("low", 99.9), ("close", 100.0)):
        d1[column] = value
    lvl = Level(price=100.0, kind="support", touches=2,
                first_idx=12, last_idx=12)
    assert _native_atr(d1["atr14"], 12) is None
    _score_level(lvl, d1, cfg, d1["atr14"])
    assert lvl.strength == 2.0
    assert lvl.formed_by_consolidation is False
    assert "сформирован проторговкой" not in lvl.notes


def test_levels_have_no_lookahead():
    cfg = StrategyConfig()
    d1 = daily()
    tomorrow = d1.index[-1].date()
    levels = levels_for_session(d1.iloc[:-1], tomorrow, cfg)
    assert all(level.valid_from <= tomorrow for level in levels)
    assert all(level.formed_at < tomorrow for level in levels)


def test_fourteen_original_feature_groups_preserved():
    cfg = StrategyConfig()
    d1 = daily()
    level = Level(price=float(d1.close.iloc[-1]), kind="support",
                  touches=3, strength=4.0, valid_from=date(2025, 1, 2))
    now = d1.index[-1].to_pydatetime()
    result = evaluate_all(d1, pd.DataFrame(), now, level, [level], cfg)
    assert set(result) == {f"g{i:02d}" for i in range(1, 15)}
    assert all(v.value in (True, False, None) for v in result.values())


def test_missing_native_atr_cannot_evaluate_features():
    cfg = StrategyConfig()
    d1 = daily(native_atr=False)
    lvl = Level(price=100, kind="support")
    result = evaluate_all(d1, None, d1.index[-1].to_pydatetime(), lvl, [lvl], cfg)
    assert all(x.value is None for x in result.values())
    assert all("Native LEAN ATR" in x.reason for x in result.values())


def test_market_data_is_asof_not_future():
    d1 = daily()
    now = d1.index[-1] + pd.Timedelta(hours=9)
    m5 = pd.DataFrame(
        {"open":[100.0,100.1], "high":[101.0,101.1],
         "low":[99.0,99.1], "close":[100.2,100.4]},
        index=pd.DatetimeIndex([now-pd.Timedelta(minutes=5), now+pd.Timedelta(minutes=5)]))
    market = MarketData("AAPL", d1, m5)
    assert len(market.d1_asof(now.to_pydatetime())) == len(d1)-1
    assert len(market.m5_asof(now.to_pydatetime())) == 1


def test_scenario_rejects_even_one_feature_exception(monkeypatch):
    """A 4+ point score cannot hide broken feature calculation."""
    cfg = StrategyConfig()
    d1 = daily()
    level = Level(price=float(d1["close"].iloc[-1]), kind="support",
                  touches=3, strength=4.0,
                  valid_from=date(2025, 1, 2))

    def partly_broken_features(*_args, **_kwargs):
        return {
            "g01": FeatureResult("g01", None, reason="ошибка: bad native value"),
            "g02": FeatureResult("g02", True),
            "g03": FeatureResult("g03", True),
            "g04": FeatureResult("g04", True),
        }

    monkeypatch.setattr(scenario_module, "evaluate_all", partly_broken_features)
    now = d1.index[-1].to_pydatetime()
    decision = ScenarioEvaluator(cfg).evaluate(
        "MSFT", now.date(), now, d1, None, [level])
    assert not decision.accepted
    assert any("feature calculation failed" in s
               for s in decision.rejected_reasons)


def test_eight_original_signal_gates_exist():
    assert len(GATE_IDS) == 8
    d1 = daily()
    t = d1.index[-1].to_pydatetime()
    lvl = Level(price=105., kind="support", touches=3, strength=5,
                valid_from=date(2025, 1, 2))
    decision = ScenarioDecision("AAPL", t.date(), t, lvl, "bounce", "long")
    intent = build_intent(
        decision, MarketData("AAPL", d1), t, StrategyConfig())
    assert intent is not None
    assert set(intent.gates) == set(GATE_IDS)
    assert intent.gates["m5_confirmed"].passed is False


def test_no_shadow_oms_or_trading_in_lean_entrypoint():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "class QwctGerchikAlgorithm(QCAlgorithm)" in src
    assert '"atr": AverageTrueRange(' in src
    assert '"sma": SimpleMovingAverage(' in src
    assert "self.schedule.on(" in src
    assert "self.portfolio.total_portfolio_value" in src
    assert 'self._native_exit_enabled = False' in src
    assert 'self.transactions.cancel_open_orders()' in src
    assert 'self.liquidate(tag="GERCHIK EOD FLAT")' in src
    assert not any(x in src for x in (
        "OrderManager", "BrokerAdapter", "NativeBracketGateway",
        "self.market_order(", "self.limit_order(",
        "self.bracket_order("))
