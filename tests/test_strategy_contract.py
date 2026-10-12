"""Pure deterministic rule tests. NOT a profitability backtest or broker simulation."""
from datetime import datetime, date
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.features import FeatureResult, evaluate_all, g14_liquidity_sweep, g09_context, g07_close_at_extreme, g08_small_bars_approach, g03_near_retest
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


def test_false_breakout_needs_real_level_breach_and_return():
    cfg = StrategyConfig()
    d1 = daily()
    level = Level(price=100.0, kind="resistance",
                  touches=3, strength=3.0)
    d1.loc[d1.index[-3], "close"] = 99.4
    # Previous day and crossing-day high are BELOW 100; a next-day
    # close ABOVE 100 is *not* a failed upward breakout.
    d1.loc[d1.index[-2], ["open", "high", "low", "close"]] = [
        99.2, 99.5, 99.1, 99.3]
    d1.loc[d1.index[-1], "close"] = 100.1
    at = d1.index[-1].to_pydatetime()
    assert g14_liquidity_sweep(d1, None, at, level, [level], cfg).value is False

    # An actual 0.4 USD poke above resistance, followed by a daily
    # close back below it, is a valid SIMPLE failed-breakout feature.
    d1.loc[d1.index[-2], ["open", "high", "low", "close"]] = [
        99.2, 100.4, 99.1, 99.3]
    d1.loc[d1.index[-1], "close"] = 99.5
    assert g14_liquidity_sweep(d1, None, at, level, [level], cfg).value is True


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
    src = ("\n".join((Path(__file__).resolve().parents[1] / name).read_text() for name in ("main.py", "strategy/m5_runtime.py", "strategy/runtime_reporting.py")))
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


def test_g09_pullback_free_bars_moving_away_from_level_are_not_an_approach():
    cfg = StrategyConfig()
    d1 = daily()
    closes = [100.0, 100.4, 100.8, 101.2, 101.6]
    for i, cl in enumerate(closes):
        row = d1.index[-5+i]
        d1.loc[row, ["open", "close", "high", "low"]] = [
            cl, cl, cl + 2.3, cl - 2.3]
    level = Level(price=100.0, kind="resistance")
    f = g09_context(d1, None, d1.index[-1].to_pydatetime(),
                    level, [level], cfg)
    assert f.detail["approaching_level"] is False
    assert f.detail["long_pullback_free"] is False
    assert not bool(f.detail["big_bars_approach"])


def test_g09_clean_zone_looks_past_candidate_level_not_from_daily_close():
    cfg = StrategyConfig()
    d1 = daily()
    d1.loc[d1.index[-1], "close"] = 98.
    target = Level(price=100.0, kind="resistance")
    behind = Level(price=110.0, kind="resistance")
    f = g09_context(d1, None, d1.index[-1].to_pydatetime(),
                    target, [target, behind], cfg)
    assert bool(f.detail["clean_zone"]) is True
    assert f.detail["room_atr"] == 4.0
    unknown = g09_context(d1, None, d1.index[-1].to_pydatetime(),
                          target, [target], cfg)
    assert unknown.detail["clean_zone"] is None
    assert unknown.detail["room_atr"] is None


def test_g07_close_at_lower_extreme_cannot_support_breakout_above_last_close():
    cfg = StrategyConfig()
    d1 = daily()
    d1.loc[d1.index[-2], "close"] = 98.6
    d1.loc[d1.index[-1], ["open", "high", "low", "close"]] = [
        99.9, 100.3, 98.9, 99.0]
    lvl = Level(price=100., kind="resistance")
    observed = g07_close_at_extreme(
        d1, None, d1.index[-1].to_pydatetime(), lvl, [lvl], cfg)
    assert not bool(observed.value)
    assert bool(observed.detail["closed_at_low"])
    # The same setup with a genuine close near the upper extreme may
    # support an upward-breakout *feature*, not an executable order.
    d1.loc[d1.index[-1], ["open", "high", "low", "close"]] = [
        99.1, 100.1, 98.8, 100.0]
    observed = g07_close_at_extreme(
        d1, None, d1.index[-1].to_pydatetime(), lvl, [lvl], cfg)
    assert bool(observed.value)


def test_g08_small_bars_moving_away_must_not_be_called_approach():
    cfg = StrategyConfig()
    d1 = daily()
    closes = [100., 100.4, 100.8, 101.2, 101.4]
    for j, cl in enumerate(closes):
        d1.loc[d1.index[-5+j], ["open", "high", "low", "close"]] = [
            cl, cl + .2, cl - .2, cl]
    lvl = Level(price=100., kind="resistance")
    fr = g08_small_bars_approach(
        d1, None, d1.index[-1].to_pydatetime(), lvl, [lvl], cfg)
    assert bool(fr.detail["small_bars"])
    assert bool(fr.detail["trending"])
    assert not bool(fr.detail["approaching_level"])
    assert not bool(fr.value)


def test_g03_includes_yesterday_closed_d1_retest_and_real_previous_close_gap():
    # The morning scanner passes only completed D1 candles. Excluding the
    # final row would discard a real retest made on the last session.
    cfg = StrategyConfig()
    d1 = daily()
    dates = d1.index[-11:]
    d1.loc[dates, ["open", "high", "low", "close"]] = [
        102.0, 102.4, 101.6, 102.0]
    # Last CLOSED session crosses 100 and gaps down from yesterday's 102.
    d1.loc[dates[-1], ["open", "high", "low", "close"]] = [
        100.1, 100.5, 99.8, 100.2]
    lvl = Level(price=100., kind="support")
    result = g03_near_retest(
        d1, None, dates[-1].to_pydatetime(), lvl, [lvl], cfg)
    assert result.value is True
    assert result.detail["touched_in_window"] is True
    assert result.detail["three_bar_retest"] is True
    assert result.detail["gap_retest"] is True


def test_g03_first_lookback_bar_uses_prior_closed_bar_for_gap_check():
    cfg = StrategyConfig()
    d1 = daily()
    dates = d1.index[-11:]
    d1.loc[dates, ["open", "high", "low", "close"]] = [
        102.0, 102.3, 101.7, 102.0]
    # First bar in the 10-session window touches 100; its true previous
    # D1 close is available immediately before the 10-bar window.
    d1.loc[dates[0], ["open", "high", "low", "close"]] = [
        104.0, 104.5, 103.5, 104.0]
    d1.loc[dates[1], ["open", "high", "low", "close"]] = [
        100.1, 100.5, 99.8, 100.2]
    lvl = Level(price=100., kind="support")
    result = g03_near_retest(
        d1, None, dates[-1].to_pydatetime(), lvl, [lvl], cfg)
    assert result.detail["gap_retest"] is True
    assert result.detail["touched_in_window"] is True


def test_g03_gap_retest_bonus_requires_gap_closer_to_daily_level():
    cfg = StrategyConfig()
    d1 = daily()
    dates = d1.index[-11:]
    # Prior close at 99 is already ONE dollar from level 100.
    # Today opens at 102 (now TWO dollars from that level), then
    # trades down through it. This is an intraday wick retest,
    # but certainly not a gap TOWARD the level.
    d1.loc[dates, ["open", "high", "low", "close"]] = [
        102., 102.4, 101.6, 102.]
    d1.loc[dates[-2], ["open", "high", "low", "close"]] = [
        99., 99.5, 98.7, 99.]
    d1.loc[dates[-1], ["open", "high", "low", "close"]] = [
        102., 102.3, 99.8, 100.2]
    lvl = Level(price=100., kind="support")
    r = g03_near_retest(d1, None, dates[-1].to_pydatetime(),
                        lvl, [lvl], cfg)
    assert r.detail["touched_in_window"] is True
    assert r.detail["gap_retest"] is False

    # A genuine DOWNWARD gap TOWARD support does earn the bonus.
    d1.loc[dates[-2], ["open", "high", "low", "close"]] = [
        102., 102.4, 101.6, 102.]
    d1.loc[dates[-1], ["open", "high", "low", "close"]] = [
        100.1, 100.5, 99.8, 100.2]
    r = g03_near_retest(d1, None, dates[-1].to_pydatetime(),
                        lvl, [lvl], cfg)
    assert r.detail["gap_retest"] is True
