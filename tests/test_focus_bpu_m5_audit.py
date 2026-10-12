"""Regression research: select first actual setup, quantify BPU1 M5 distances,
and prove that six M5 passes are not a 450-bar logic error.

Synthetic candles are labeled synthetic and never used as market claims.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.focus import choose_focus
from strategy.research_trace import BpuTouchAudit, SetupTrace
from strategy.signals import _check_m5
from strategy.config import StrategyConfig
from strategy.levels import Level
from strategy.scenarios import ScenarioDecision


ET = ZoneInfo("America/New_York")


def make_decision(symbol, model, side, level, when="2024-01-02"):
    day = date.fromisoformat(when)
    lvl = Level(level, "resistance" if side == "short" else "support",
                2, 3., valid_from=day, formed_at=date(2023, 12, 20),
                first_idx=40, last_idx=60)
    return ScenarioDecision(symbol, day, datetime.combine(
        day, datetime.min.time(), ET).replace(hour=9, minute=29),
        lvl, model, side, 4.5)


def test_focus_charts_first_real_bounce_not_top_screener_ticker():
    watch = ["TSLA", "NVDA", "AMD"]
    decisions = {"TSLA": None,
                 "NVDA": make_decision("NVDA", "bounce", "short", 50.266),
                 "AMD": make_decision("AMD", "false_breakout", "long", 100.)}
    assert choose_focus(watch, decisions) == "NVDA"
    assert choose_focus(watch, decisions, preferred="AMD") == "AMD"
    assert choose_focus(watch, decisions, preferred="TSLA") == "NVDA"
    assert choose_focus(watch, {}) is None
    assert choose_focus(watch, {"TSLA": decisions["AMD"]}) is None


def test_focus_prioritizes_bounce_when_multiple_accepted_setups_today():
    watch = ["TSLA", "NVDA"]
    decisions = {"TSLA": make_decision("TSLA", "false_breakout", "long", 190),
                 "NVDA": make_decision("NVDA", "bounce", "short", 50.266)}
    assert choose_focus(watch, decisions) == "NVDA"


def test_native_resistance_audit_76_m5_bar_extremes_replay_exact_gap():
    audit = BpuTouchAudit("short", 50.266, .01)
    t0 = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    for i in range(76):
        high = 49.00 + i * .01
        audit.observe(t0+timedelta(minutes=5*i), 48.1, high, 48.4)
    info = audit.as_dict()
    assert info["bars"] == 76
    assert info["native_tick"] == .01
    assert abs(info["closest_gap"] + 0.516) < 1e-8
    assert info["touches"] == 0
    assert info["undershoots"] == 76
    assert info["overshoots"] == 0
    assert info["nearest_time"].startswith("2024-01-02T15:50")
    assert info["maximum_high"] == 49.75
    line = audit.short_line("NVDA", "2024-01-02")
    assert "76" in line
    assert "maxHi=49.7500" in line
    assert "gap=-0.5160" in line
    assert len(line) <= 190


def test_native_touch_audit_does_not_confuse_wick_cross_with_exact_touch():
    audit = BpuTouchAudit("short", 50.266, .01)
    t = datetime(2024, 1, 2, 11, 0, tzinfo=ET)
    audit.observe(t, 49., 50.25, 50.)
    audit.observe(t+timedelta(minutes=5), 49., 50.27, 50.)
    audit.observe(t+timedelta(minutes=10), 49., 50.28, 50.)
    assert audit.as_dict()["touches"] == 1  # abs(50.27-50.266) < .005
    assert audit.as_dict()["undershoots"] == 1
    assert audit.as_dict()["overshoots"] == 1


def test_false_breakout_gate_is_a_one_bar_event_not_76_bar_score():
    cfg = StrategyConfig()
    lvl = Level(100., "resistance", 2, 3., valid_from=date(2024, 1, 2))
    idx = pd.date_range("2024-01-02 09:35", periods=5, freq="5min", tz=ET)
    # One valid short false breakout at the third bar: prior <= level,
    # current high > level and close back <= level.
    vals = [[99.4, 99.6, 99.1, 99.4],
            [99.4, 99.7, 99.2, 99.6],
            [99.6, 100.2, 99.5, 99.8],
            [99.8, 99.9, 99.4, 99.7],
            [99.7, 99.8, 99.3, 99.4]]
    df = pd.DataFrame(vals, index=idx, columns=["open","high","low","close"])
    states = [_check_m5(df.iloc[:n], lvl, "short", "false_breakout",
                        cfg, idx[n-1].to_pydatetime()).passed for n in range(2,6)]
    assert states == [False, True, False, False]


def test_bounce_two_bar_gate_is_not_equivalent_to_gerchik_exact_bpu1():
    cfg = StrategyConfig()
    lvl = Level(50.266, "resistance", 2, 3., valid_from=date(2024, 1, 2))
    idx = pd.date_range("2024-01-02 09:35", periods=2, freq="5min", tz=ET)
    vals = [[50.12, 50.22, 50.08, 50.18],
            [50.18, 50.40, 49.96, 50.11]]
    df = pd.DataFrame(vals, index=idx, columns=["open", "high", "low", "close"])
    approx = _check_m5(df, lvl, "short", "bounce", cfg,
                       idx[-1].to_pydatetime())
    assert approx.passed is True  # candle spans median 50.266
    audit = BpuTouchAudit("short", lvl.price, .01)
    audit.observe(idx[-1].to_pydatetime(), 49.96, 50.40, 50.11)
    assert audit.as_dict()["touches"] == 0  # high did NOT equal 50.266
