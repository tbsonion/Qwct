"""First phase risk-policy evidence is not broker authorization.

Use KNOWN native portfolio values for a pure fail-closed preview.
Unknown realized P&L, pending fills, reserved risk or day-break state
cannot be treated as zero.  No orders or virtual portfolio are created.
"""
from datetime import datetime, timezone

import pytest

from strategy.config import StrategyConfig
from strategy.risk_research import RiskSnapshot, review_risk


def full_snapshot(**kw):
    data = dict(
        equity=25000., available_buying_power=24500.,
        current_positions=0, pending_entries=0,
        reserved_open_risk=0., daily_realized_pnl=0.,
        weekly_realized_pnl=0., monthly_realized_pnl=0.,
        losing_trades_today=0, entries_today=0,
        consecutive_losing_days=0, pause_days_remaining=0,
        asof=datetime(2024, 1, 2, 14, tzinfo=timezone.utc))
    data.update(kw)
    return RiskSnapshot(**data)


def test_explicit_complete_native_evidence_passes_only_mechanical_policy():
    x=review_risk(full_snapshot(), side="long", shares=10,
                  entry_price=100., stop_price=95., cfg=StrategyConfig())
    assert x.mechanical_pass is True
    assert x.complete is True
    assert x.projected_stop_risk == 50.
    assert x.can_submit is False
    assert "broker" in " ".join(x.blockers).lower()


def test_missing_realized_pnl_never_assumed_zero():
    x=review_risk(full_snapshot(weekly_realized_pnl=None),
                  side="long", shares=10, entry_price=100.,
                  stop_price=95., cfg=StrategyConfig())
    assert x.mechanical_pass is None
    assert x.complete is False
    assert x.can_submit is False
    assert any("weekly" in v for v in x.blockers)


@pytest.mark.parametrize("kwargs", [
    {"daily_realized_pnl": -750.},
    {"weekly_realized_pnl": -750.},
    {"monthly_realized_pnl": -2500.},
    {"losing_trades_today": 3},
    {"entries_today": 5},
    {"current_positions": 3},
    {"pause_days_remaining": 2},
    {"pending_entries": 1},
    {"consecutive_losing_days": 3},
    {"reserved_open_risk": 740.},
    {"available_buying_power": 20.},
])
def test_fail_closed_for_hard_risk_limits(kwargs):
    x=review_risk(full_snapshot(**kwargs), side="long", shares=10,
                  entry_price=100., stop_price=95., cfg=StrategyConfig())
    assert x.mechanical_pass is False
    assert x.can_submit is False
    assert len(x.blockers)>1


def test_single_trade_stop_risk_over_50_rejected():
    x=review_risk(full_snapshot(), side="short", shares=11,
                  entry_price=100., stop_price=105., cfg=StrategyConfig())
    assert x.projected_stop_risk == 55.
    assert x.mechanical_pass is False


def test_stop_direction_and_negative_or_nonfinite_values_rejected():
    with pytest.raises(ValueError):
        review_risk(full_snapshot(), side="long", shares=2,
                    entry_price=100., stop_price=101., cfg=StrategyConfig())
    with pytest.raises(ValueError):
        full_snapshot(equity=float("nan"))


def test_preview_never_promotes_unverified_broker_stop_or_lean_risk_gate():
    review=review_risk(full_snapshot(), side="long", shares=10,
                       entry_price=100., stop_price=95., cfg=StrategyConfig())
    assert review.can_submit is False
    assert "orders" not in review.__dict__
