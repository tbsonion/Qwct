"""Legacy two-bar bounce cannot masquerade as full preclose Gerchik TVX."""
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.bpu_tvx_evidence import BpuTvxEvidence
from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.levels import Level
from strategy.scenarios import ScenarioDecision
from strategy.signals import _check_m5, build_intent

ET = ZoneInfo("America/New_York")
FINISH = datetime(2024, 1, 3, 10, 45, tzinfo=ET)
BPU1 = FINISH - timedelta(minutes=5)


def context(evidence=None):
    daily_idx = pd.bdate_range(end="2024-01-02", periods=110, tz=ET)
    d1 = pd.DataFrame({
        "open": 99.8, "high": 102., "low": 98.5,
        "close": 100., "volume": 1_000_000.,
        "atr14": 2., "sma50": 99.},
        index=daily_idx)
    m5 = pd.DataFrame([
        [100.10, 100.25, 100.0, 100.10],
        [100.10, 100.21, 100.0, 100.11]],
        index=pd.DatetimeIndex([BPU1, FINISH]),
        columns=["open", "high", "low", "close"])
    level = Level(price=100., kind="support", touches=2, strength=3.,
                  valid_from=FINISH.date())
    decision = ScenarioDecision("NVDA", FINISH.date(), FINISH, level,
                                "bounce", "long")
    return decision, MarketData(
        "NVDA", d1, m5, session_levels=(level,), bpu_tvx=evidence)


def good_evidence():
    return BpuTvxEvidence(
        symbol="NVDA", session=FINISH.date(), side="long",
        d1_level_price=100., native_origin_price=100.,
        entry_price=100.10, stop_price=99.50,
        preclose_last_price=100.06,
        bpu1_end=BPU1,
        preclose_at=FINISH-timedelta(seconds=30),
        bpu2_end=FINISH,
        origin_provenance="D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU")


def test_prior_two_bar_bounce_is_only_legacy_proxy_not_m5_gate_approval():
    decision, market = context()
    assert _check_m5(market.m5, decision.level, "long", "bounce",
                     StrategyConfig(), FINISH).passed is True
    intent = build_intent(decision, market, FINISH, StrategyConfig())
    assert intent.gates["m5_confirmed"].passed is False
    assert "missing native BPU/TVX" in intent.gates["m5_confirmed"].reason
    assert not intent.all_gates_passed


def test_verified_native_preclose_plus_later_m5_allows_only_readonly_bounce_gate():
    decision, market = context(good_evidence())
    intent = build_intent(decision, market, FINISH, StrategyConfig())
    assert intent.gates["m5_confirmed"].passed is True
    assert intent.limit_price == 100.10
    assert intent.stop_price == 99.50
    assert round(intent.risk_per_share, 3) == 0.6
    assert intent.gates["risk_approved"].passed is None
    assert intent.all_gates_passed is False
    assert market.bpu_tvx.can_submit is False


def test_mismatching_evidence_never_approves_wrong_symbol_session_side_or_level():
    good = good_evidence()
    for altered in (
        replace(good, symbol="TSLA"),
        replace(good, session=FINISH.date()-timedelta(days=1)),
        replace(good, side="short"),
        replace(good, d1_level_price=101.),
        replace(good, preclose_at=FINISH-timedelta(seconds=31)),
        replace(good, bpu1_end=BPU1-timedelta(minutes=5)),
        replace(good, bpu2_end=FINISH+timedelta(minutes=5)),
        replace(good, origin_provenance="unknown"),
        replace(good, native_origin_price=float("nan")),
        replace(good, entry_price=100.),
        replace(good, stop_price=100.),
        replace(good, preclose_last_price=float("nan")),
    ):
        decision, market = context(altered)
        assert build_intent(
            decision, market, FINISH, StrategyConfig()
        ).gates["m5_confirmed"].passed is False


def test_stale_reconciled_bpu2_is_not_replayable_in_later_m5():
    good = good_evidence()
    assert not good.matches(
        symbol="NVDA", session=FINISH.date(), side="long",
        level_price=100., observed_at=FINISH+timedelta(minutes=5))


def test_post_bpu2_close_cannot_retroactively_replace_price_at_minus30s():
    decision, market = context(good_evidence())
    # A price surge in final 30s was not known when the TVX
    # provisional signal was observed. No-chase uses the REAL
    # SEC last trade price at -30s, not the later M5 close.
    market.m5.loc[FINISH, ["open", "high", "low", "close"]] = [
        100.10, 102.3, 100.0, 101.8]
    intent = build_intent(decision, market, FINISH, StrategyConfig())
    assert intent.gates["m5_confirmed"].passed is True
    assert intent.limit_price == 100.10
    assert intent.gates["risk_approved"].passed is None
    assert intent.all_gates_passed is False
