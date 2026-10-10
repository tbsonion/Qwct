"""Regression cases that must fail under the old Qwct M5/mirror/risk code.

All examples use fixed fabricated OHLC for logical counterexamples only.
They are not a profitability test, broker simulator, or LEAN certification.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.levels import Level, _mark_mirror
from strategy.scenarios import ScenarioDecision
from strategy.signals import _check_m5, build_intent


ET = ZoneInfo("America/New_York")


def m5(rows):
    times = pd.date_range("2024-02-05 09:35", periods=len(rows), freq="5min", tz=ET)
    return pd.DataFrame(rows, index=times, columns=["open", "high", "low", "close"])


def check(rows, side, model, level=100.):
    x = m5(rows)
    lvl = Level(price=level, kind="resistance", touches=2, strength=2)
    return _check_m5(x, lvl, side, model, StrategyConfig(), x.index[-1].to_pydatetime())


def test_continuation_above_level_is_not_new_m5_breakout():
    res = check([[101, 101.6, 100.8, 101.2],
                 [101.2, 101.8, 101.1, 101.6]], "long", "breakout")
    assert res.passed is False


def test_continuation_below_level_is_not_new_m5_breakdown():
    res = check([[99.2, 99.5, 98.5, 98.9],
                 [98.9, 99.1, 98.2, 98.5]], "short", "breakout")
    assert res.passed is False


def test_genuine_closed_m5_breakout_requires_prior_close_other_side():
    assert check([[99.6, 99.9, 99.2, 99.7],
                  [99.7, 100.4, 99.6, 100.3]], "long", "breakout").passed is True
    assert check([[100.4, 100.8, 100.1, 100.3],
                  [100.3, 100.4, 99.4, 99.7]], "short", "breakout").passed is True


def test_single_bar_m5_bounce_does_not_prove_approach():
    # Intrabar straddle and favorable close alone are not Gerchik evidence.
    assert check([[99.9, 100.5, 99.8, 100.4]], "long", "bounce").passed is False


def test_bounce_requires_prior_bar_on_original_side():
    assert check([[98.8, 99.6, 98.6, 99.2],
                  [99.3, 100.5, 99.1, 100.3]], "long", "bounce").passed is False
    assert check([[101.3, 101.5, 100.7, 101.2],
                  [101.2, 101.4, 99.9, 99.8]], "short", "bounce").passed is False


def test_closed_m5_bounce_two_bar_approach():
    assert check([[100.5, 100.9, 100.3, 100.4],
                  [100.4, 100.6, 99.9, 100.3]], "long", "bounce").passed is True
    assert check([[99.7, 99.9, 99.3, 99.6],
                  [99.6, 100.1, 99.4, 99.7]], "short", "bounce").passed is True


def test_m5_bars_cannot_skip_intermediate_candle_for_confirmation():
    rows = [[99.6, 99.9, 99.2, 99.7], [99.7, 100.4, 99.6, 100.3]]
    x = m5(rows)
    x.index = [x.index[0], x.index[1] + pd.Timedelta(minutes=5)]
    lvl = Level(price=100, kind="resistance")
    assert _check_m5(x, lvl, "long", "breakout", StrategyConfig(),
                     x.index[-1].to_pydatetime()).passed is False


def test_old_mirror_wicks_without_role_change_not_allowed():
    dates = pd.date_range("2024-01-01", periods=25, freq="B", tz=ET)
    d = pd.DataFrame({"open": 100.7, "high": 101.2, "low": 99.8,
                      "close": 100.8}, index=dates)
    lvl = Level(price=100, kind="support", touches=2, first_idx=10, last_idx=19)
    _mark_mirror([lvl], d, StrategyConfig())
    assert lvl.kind == "support"


def test_support_becomes_mirror_only_after_break_and_retest_from_below():
    dates = pd.date_range("2024-01-01", periods=25, freq="B", tz=ET)
    d = pd.DataFrame({"open": 100.7, "high": 101.2, "low": 99.8,
                      "close": 100.8}, index=dates)
    d.loc[dates[20], ["open", "high", "low", "close"]] = [100.3, 100.5, 99.3, 99.5]
    d.loc[dates[21], ["open", "high", "low", "close"]] = [99.4, 100.1, 99.0, 99.3]
    lvl = Level(price=100, kind="support", touches=2, first_idx=10, last_idx=19)
    _mark_mirror([lvl], d, StrategyConfig())
    assert lvl.kind == "mirror"


def daily():
    idx = pd.date_range("2023-08-01", periods=110, freq="B", tz=ET)
    return pd.DataFrame({"open": 100.0, "high": 102.0, "low": 98.0,
                         "close": 100.0, "volume": 1_000_000,
                         "atr14": 4.0, "sma50": 100.0}, index=idx)


def test_risk_approval_fails_closed_without_real_risk_manager():
    d = daily()
    asof = (d.index[-1] + pd.Timedelta(days=1)).to_pydatetime()
    lvl = Level(price=100, kind="support", touches=2, strength=3,
                valid_from=date(2023, 8, 1))
    decision = ScenarioDecision("AAPL", asof.date(), asof, lvl, "bounce", "long")
    intent = build_intent(decision, MarketData("AAPL", d), asof, StrategyConfig())
    assert intent is not None
    assert intent.gates["risk_approved"].passed is not True
    assert intent.all_gates_passed is False


def test_stop_gate_checks_actual_entry_stop_loss_side():
    d = daily()
    # Signal's current M5 close at 97 implies stop=99 for a long,
    # which is a LOSS-invalid stop above the intended entry.
    close_at = (d.index[-1] + pd.Timedelta(days=1)).replace(hour=9, minute=35)
    m = pd.DataFrame([[96.7, 97.2, 96.6, 97.0]], index=[close_at],
                     columns=["open", "high", "low", "close"])
    lvl = Level(price=100, kind="resistance", touches=2, strength=3,
                valid_from=date(2023, 8, 1))
    decision = ScenarioDecision("AAPL", close_at.date(),
                                close_at.to_pydatetime(), lvl, "breakout", "long")
    intent = build_intent(decision, MarketData("AAPL", d, m),
                          close_at.to_pydatetime(), StrategyConfig())
    assert intent is not None
    assert intent.gates["stop_behind_d1_level"].passed is False


def test_target_gate_validates_actual_target_price_not_only_config_ratio():
    from dataclasses import replace
    d = daily()
    at = (d.index[-1] + pd.Timedelta(days=1)).to_pydatetime()
    lvl = Level(price=1, kind="resistance", touches=2, strength=3,
                valid_from=date(2023, 8, 1))
    # Short stop=2 and 3R target=1-3*(2-1)=-2 => invalid price.
    decision = ScenarioDecision("AAPL", at.date(), at, lvl, "bounce", "short")
    intent = build_intent(decision, MarketData("AAPL", d), at, StrategyConfig())
    assert intent is not None
    assert intent.gates["target_at_least_3r"].passed is False


def test_trade_intent_empty_gate_map_can_never_claim_all_gates_passed():
    from strategy.signals import TradeIntent, GateResult, GATE_IDS
    now = datetime(2024, 2, 5, 10, 0, tzinfo=ET)
    intent = TradeIntent("MSFT", now.date(), now, "long", "bounce",
                         100., 100., 99., 1., 5, 3., None)
    assert intent.all_gates_passed is False
    intent.gates = {"trend_aligned": GateResult("trend_aligned", True)}
    assert intent.all_gates_passed is False
    intent.gates = {name: GateResult(name, True) for name in GATE_IDS}
    assert intent.all_gates_passed is True


def test_m5_far_from_d1_level_rejects_no_chase_threshold():
    d = daily()
    at = (d.index[-1] + pd.Timedelta(days=1)).replace(hour=9, minute=40)
    m = pd.DataFrame([[99.7, 99.9, 99.2, 99.8],
                      [99.8, 102.0, 99.7, 101.9]],
                     index=[at - pd.Timedelta(minutes=5), at],
                     columns=["open", "high", "low", "close"])
    lvl = Level(price=100, kind="resistance", touches=2, strength=3,
                valid_from=date(2023, 8, 1))
    decision = ScenarioDecision("AAPL", at.date(), at.to_pydatetime(),
                                lvl, "breakout", "long")
    intent = build_intent(decision, MarketData("AAPL", d, m),
                          at.to_pydatetime(), StrategyConfig())
    assert intent is not None
    # 1.9 USD chase / ATR 4 = 0.475 ATR; cfg allows <=0.3 ATR.
    assert intent.gates["m5_confirmed"].passed is False
