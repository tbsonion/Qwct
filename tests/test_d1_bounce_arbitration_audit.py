"""Score arbitration audit is read-only: decisions/thresholds are unchanged."""
from datetime import timedelta

import pandas as pd

import strategy.scenarios as sm
from strategy.config import StrategyConfig
from strategy.features import FeatureResult
from strategy.levels import Level


def _case(monkeypatch, *, bounce_parts=2, kind="resistance", original_kind=None):
    dates = pd.bdate_range("2024-01-01", periods=85, tz="America/New_York")
    d1 = pd.DataFrame({
        "open": 100., "high": 101., "low": 99., "close": 100.,
        "volume": 1_000_000, "atr14": 3.}, index=dates)
    day = dates[-1].date() + timedelta(days=1)
    now = (dates[-1] + pd.Timedelta(days=1, hours=9, minutes=29)).to_pydatetime()
    level = Level(price=100., kind=kind, touches=3, strength=4.,
                  source="swing_cluster", formed_at=dates[24].date(),
                  valid_from=dates[30].date(), first_idx=12, last_idx=24,
                  original_kind=original_kind)
    def features(*_a, **_kw):
        return {
            "g09": FeatureResult("g09", False, detail={
                "long_pullback_free": bounce_parts >= 1,
                "big_bars_approach": bounce_parts >= 2}),
            "g11": FeatureResult("g11", True),
            "g14": FeatureResult("g14", True),
            "g04": FeatureResult("g04", True),
        }
    monkeypatch.setattr(sm, "evaluate_all", features)
    evaluator = sm.ScenarioEvaluator(StrategyConfig())
    return evaluator, evaluator.evaluate("AAPL", day, now, d1, None, [level])


def test_shadow_bounce_above_threshold_but_false_breakout_outscores(monkeypatch):
    ev, decision = _case(monkeypatch, bounce_parts=2)
    assert decision.accepted and decision.model == "false_breakout"
    assert decision.score == 5.
    assert ev.scan_model_audit["nearby_evaluated"] == 1
    assert ev.scan_model_audit["bsu_level_present"] == 1
    assert ev.scan_model_audit["bounce_scored_eligible"] == 1
    assert ev.scan_model_audit["bounce_outscored"] == 1
    assert ev.scan_model_audit["selected_bounce"] == 0
    assert ev.scan_model_audit["bounce_tie_lost"] == 0


def test_shadow_bounce_below_threshold_is_not_promoted(monkeypatch):
    ev, decision = _case(monkeypatch, bounce_parts=1)
    assert decision.model == "false_breakout"
    assert ev.scan_model_audit["bounce_below_threshold"] == 1
    assert ev.scan_model_audit["bounce_scored_eligible"] == 0
    assert ev.scan_model_audit["selected_bounce"] == 0


def test_mirror_bounce_score_does_not_claim_native_bsu_eligible(monkeypatch):
    ev, decision = _case(monkeypatch, bounce_parts=2, kind="mirror")
    assert decision.model == "false_breakout"
    assert ev.scan_model_audit["bsu_level_present"] == 0
    assert ev.scan_model_audit["no_bsu_eligible_level"] == 1
    assert ev.scan_model_audit["bounce_scored_eligible"] == 0


def test_proven_mirror_bounce_is_counted_bsu_eligible(monkeypatch):
    ev, decision = _case(
        monkeypatch, bounce_parts=2, kind="mirror", original_kind="support")
    assert decision.model == "false_breakout"
    assert ev.scan_model_audit["bsu_level_present"] == 1
    assert ev.scan_model_audit["bounce_scored_eligible"] == 1
