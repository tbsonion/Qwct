"""Red-first source integration tests for a native LEAN D1 -> M5 BPU observer.

These tests do NOT authorize TVX orders. BSU is a confirmed D1
swing-origin research PROXY, not a claimed canonical human BSU.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.bsu_bridge import create_bsu_research_observer
from strategy.config import StrategyConfig
from strategy.levels import Level
from strategy.patterns_bsu import Bar
from strategy.scenarios import ScenarioDecision

ET = ZoneInfo("America/New_York")


def evidence(kind="support", side="long", level_price=100.):
    idx = pd.date_range("2024-01-01", periods=70, freq="B", tz=ET)
    day = date(2024, 4, 15)
    df = pd.DataFrame({
        "open": 100.2, "high": 101., "low": 100.,
        "close": 100.5, "atr14": 4.,
        "bar_end": [x + pd.Timedelta(hours=16) for x in idx],
    }, index=idx)
    if kind == "resistance":
        df["high"] = 100.0
        df["low"] = 99.0
        df["open"] = 99.4
        df["close"] = 99.5
    origin = Level(price=level_price, kind=kind, touches=2,
                   strength=3, first_idx=10, last_idx=20,
                   formed_at=idx[20].date(),
                   valid_from=idx[24].date(), source="swing_cluster")
    decision = ScenarioDecision(
        "AAPL", day, datetime(2024, 4, 15, 9, 29, tzinfo=ET),
        origin, "bounce", side, score=4)
    return decision, df


def test_origin_is_native_closed_d1_swing_proxy_not_claimed_canonical_bsu():
    decision, daily = evidence()
    link, reason = create_bsu_research_observer(
        decision, daily, native_tick_size=.01, cfg=StrategyConfig())
    assert link is not None, reason
    assert link.origin_time == daily.iloc[10]["bar_end"].to_pydatetime()
    assert "PROXY" in link.provenance
    assert not link.detector.state.can_submit

    bpu1 = datetime(2024, 4, 15, 10, 5, tzinfo=ET)
    assert link.detector.on_bar(Bar(
        bpu1, 100.2, 100.4, 100., 100.2, "M5")).phase == "bpu1"
    st = link.detector.on_bar(Bar(
        bpu1 + timedelta(minutes=5), 100.3, 100.5,
        100.1, 100.3, "M5"))
    assert st.phase == "bpu2_confirmed"
    assert st.preclose_seen is False
    assert st.can_submit is False


def test_native_short_resistance_proxy_can_follow_same_rules():
    decision, daily = evidence(kind="resistance", side="short")
    link, reason = create_bsu_research_observer(
        decision, daily, native_tick_size=.01, cfg=StrategyConfig())
    assert link is not None, reason


def test_mixed_price_average_cannot_be_presented_as_precise_bsu_origin():
    decision, daily = evidence(level_price=100.03)
    link, reason = create_bsu_research_observer(
        decision, daily, native_tick_size=.01, cfg=StrategyConfig())
    assert link is None
    assert "origin" in reason.lower()


def test_no_native_bar_end_means_no_bsu_origin():
    decision, daily = evidence()
    link, reason = create_bsu_research_observer(
        decision, daily.drop(columns=["bar_end"]), .01, StrategyConfig())
    assert link is None
    assert "bar_end" in reason


def test_missing_or_naive_native_bar_end_rejected():
    decision, daily = evidence()
    daily.loc[daily.index[10], "bar_end"] = pd.NaT
    assert create_bsu_research_observer(
        decision, daily, .01, StrategyConfig())[0] is None


def test_wrong_level_kind_or_side_never_arms_bpu():
    for kind, side in [("support", "short"), ("resistance", "long"),
                       ("mirror", "long")]:
        decision, daily = evidence(kind="support", side=side)
        decision.level.kind = kind
        assert create_bsu_research_observer(
            decision, daily, .01, StrategyConfig())[0] is None


def test_breakout_and_false_breakout_are_not_bpu_bounce():
    for model in ("breakout", "false_breakout"):
        decision, daily = evidence()
        decision.model = model
        assert create_bsu_research_observer(
            decision, daily, .01, StrategyConfig())[0] is None


def test_missing_native_tick_or_atr_fails_closed():
    decision, daily = evidence()
    for t in [0., -1., None, float("nan")]:
        assert create_bsu_research_observer(
            decision, daily, t, StrategyConfig())[0] is None
    daily["atr14"] = float("nan")
    assert create_bsu_research_observer(
        decision, daily, .01, StrategyConfig())[0] is None


def test_future_formed_or_unconfirmed_level_fails_closed():
    decision, daily = evidence()
    decision.level.valid_from = date(2024, 5, 1)
    assert create_bsu_research_observer(
        decision, daily, .01, StrategyConfig())[0] is None
    decision.level.valid_from = date(2024, 3, 1)
    decision.level.formed_at = date(2024, 1, 1)
    assert create_bsu_research_observer(
        decision, daily, .01, StrategyConfig())[0] is None


def test_origin_after_morning_decision_fails_closed():
    decision, daily = evidence()
    daily.loc[daily.index[10], "bar_end"] = pd.Timestamp(
        "2024-04-15 10:30:00", tz=ET)
    assert create_bsu_research_observer(
        decision, daily, .01, StrategyConfig())[0] is None


def test_source_contract_main_connects_observer_without_imaginary_30s_data():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "from strategy.bsu_bridge import create_bsu_research_observer" in src
    assert "self.securities[symbol].symbol_properties.minimum_price_variation" in src
    assert "create_bsu_research_observer(" in src
    assert 'state["bsu_link"] = link' in src
    assert "link.detector.on_bar(ResearchBpuBar(" in src
    assert '"BSU_PROXY_BPU2_CLOSED"' in src
    assert '"bar_end": _time_index(bar.end_time)' in src
    assert "observe_preclose(" not in src
    assert "self._native_exit_enabled = False" in src
