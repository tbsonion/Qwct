"""The original Gerchik -30s instant is not the eventual BPU2 close.

These are pure, no-LEAN tests; they deliberately prove known mechanical
checks can be evaluated with only history through BPU1 plus real SEC.
They cannot establish native Schwab risk, executable fills or profit.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.levels import Level
from strategy.native_second_tvx import NativePrecloseSample
from strategy.preclose_review import review_preclose
from strategy.scenarios import ScenarioDecision

ET = ZoneInfo("America/New_York")
FINISH = datetime(2024, 1, 3, 12, 10, tzinfo=ET)
BPU1 = FINISH - timedelta(minutes=5)
CUT = FINISH - timedelta(seconds=30)


def setup():
    cfg = StrategyConfig()
    daily_index = pd.bdate_range(end="2024-01-02", periods=110, tz=ET)
    closes = [80+0.2*i for i in range(110)]
    daily = pd.DataFrame({
        "open": closes, "high": [x+1.0 for x in closes],
        "low": [x-1.0 for x in closes],
        "close": closes, "atr14": 3.,
        "sma50": pd.Series(closes).rolling(50, min_periods=1).mean().tolist(),
        "volume": 1_000_000},
        index=daily_index)
    m5 = pd.DataFrame(
        [{"open": 100.2, "high": 100.3, "low": 100.0,
          "close": 100.15, "volume": 500.}],
        index=pd.DatetimeIndex([BPU1]))
    support = Level(price=100., kind="support", strength=3., touches=2,
                    valid_from=FINISH.date())
    resistance = Level(price=120., kind="resistance", strength=3.,
                       touches=2, valid_from=FINISH.date())
    decision = ScenarioDecision(
        "NVDA", FINISH.date(), FINISH.replace(hour=9, minute=29),
        support, "bounce", "long", score=5)
    link = SimpleNamespace(
        tick_size=.01, origin_price=100., cluster_price=100.,
        provenance="D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU")
    st = SimpleNamespace(
        phase="preclose_candidate", preclose_seen=True,
        bpu1_ts=BPU1, side="long", can_submit=False,
        level_price=100., entry_price=100.10, stop_price=99.50)
    sample = NativePrecloseSample(
        observed_at=CUT, observed_since=BPU1, bpu2_end=FINISH,
        observed_low=100., observed_high=100.2, last_price=100.08,
        observed_bars=270, unobserved_seconds=0)
    return dict(decision=decision, link=link, detector_state=st,
                sample=sample, d1=daily, closed_m5=m5,
                levels=(support, resistance), cfg=cfg, equity=25_000.)


def test_preview_uses_only_already_closed_m5_and_native_sec_not_future_bpu2():
    inputs = setup()
    review = review_preclose(**inputs)
    checks = dict(review.checks)
    assert checks["native_second_cutoff"] is True
    assert checks["asof_d1_m5"] is True
    assert checks["native_tick_limit_stop"] is True
    assert checks["frozen_next_level_room_4r"] is True
    assert checks["gerchik_session"] is True
    assert checks["native_d1_trend"] is True
    assert checks["daily_atr_ready"] is True
    assert checks["target_3r"] is True
    assert checks["preliminary_risk_budget"] is True
    assert checks["last_trade_no_chase"] is True
    assert review.evidence_ready is True
    assert checks["broker_protection"] is None
    assert review.can_submit is False
    assert review.observed_at == CUT
    assert review.limit_price == 100.1
    assert review.stop_price == 99.5
    assert 0 < review.estimated_shares < 1000
    assert any("UNKNOWN" in reason for reason in review.blockers)


def test_second_lookahead_m5_bpu2_is_rejected_at_preclose():
    inputs = setup()
    inputs["closed_m5"].loc[pd.Timestamp(FINISH)] = [
        100.1, 105., 99.99, 103.0, 1000.]
    review = review_preclose(**inputs)
    assert dict(review.checks)["asof_d1_m5"] is False
    assert review.evidence_ready is False
    assert review.can_submit is False


def test_mismatching_origin_cluster_and_missing_next_level_are_blockers():
    inputs = setup()
    inputs["link"].cluster_price = 100.03
    inputs["levels"] = inputs["levels"][:1]
    review = review_preclose(**inputs)
    checks = dict(review.checks)
    assert checks["frozen_origin_level"] is False
    assert checks["frozen_next_level_room_4r"] is False
    assert review.evidence_ready is False


def test_early_morning_bounce_rejected_despite_native_bpu():
    inputs = setup()
    at = datetime(2024, 1, 3, 11, 59, 30, tzinfo=ET)
    inputs["sample"] = NativePrecloseSample(
        observed_at=at,
        observed_since=at-timedelta(minutes=4,seconds=30),
        bpu2_end=at+timedelta(seconds=30),
        observed_low=100., observed_high=100.2, last_price=100.08)
    review = review_preclose(**inputs)
    assert dict(review.checks)["gerchik_session"] is False
    assert review.evidence_ready is False


def test_unknown_broker_risk_never_becomes_true_even_all_pattern_checks_pass():
    inputs = setup()
    result = review_preclose(**inputs)
    assert result.can_submit is False
    assert dict(result.checks)["broker_protection"] is None
