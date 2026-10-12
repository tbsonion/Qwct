"""First phase risk-policy evidence is not broker authorization.

Use KNOWN native portfolio values for a pure fail-closed preview.
Unknown realized P&L, pending fills, reserved risk or day-break state
cannot be treated as zero.  No orders or virtual portfolio are created.
"""
from datetime import datetime, timezone
from decimal import Decimal

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
        asof=datetime(2024, 1, 2, 14, tzinfo=timezone.utc),
        daily_start_equity=25000., weekly_start_equity=25000.,
        monthly_start_equity=25000., period_cashflows_verified=True,
        winning_trades_today=0,
        exchange_close=datetime(2024, 1, 2, 21, tzinfo=timezone.utc))
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


@pytest.mark.parametrize("missing", [
    "daily_start_equity", "weekly_start_equity", "monthly_start_equity",
    "period_cashflows_verified", "exchange_close", "winning_trades_today",
])
def test_unknown_native_baseline_provenance_or_exchange_schedule_is_not_pass(missing):
    result = review_risk(
        full_snapshot(**{missing: None}), side="long", shares=10,
        entry_price=100., stop_price=95., cfg=StrategyConfig())
    assert result.mechanical_pass is None
    assert not result.complete
    assert not result.can_submit


@pytest.mark.parametrize("override,expected", [
    ({"equity": 24250.}, "daily marked-to-market"),
    ({"weekly_start_equity": 25774.}, "weekly marked-to-market"),
    ({"monthly_start_equity": 27778.}, "monthly marked-to-market"),
    ({"losing_trades_today": 2, "winning_trades_today": 1}, "2 losing"),
    ({"period_cashflows_verified": False}, "cashflows"),
    ({"asof": datetime(2024, 1, 2, 20, 55, tzinfo=timezone.utc)}, "EOD cutoff"),
    ({"asof": datetime(2024, 1, 3, 14, tzinfo=timezone.utc)}, "exchange session"),
])
def test_loss_halts_early_close_and_mixed_outcomes_fail_closed(override, expected):
    result = review_risk(full_snapshot(**override), side="long",
                         shares=10, entry_price=100., stop_price=95.,
                         cfg=StrategyConfig())
    assert result.mechanical_pass is False
    assert any(expected in blocker for blocker in result.blockers)
    assert not result.can_submit


def test_early_exchange_close_uses_native_timestamp_not_fixed_1600():
    snap = full_snapshot(
        asof=datetime(2024, 7, 3, 16, 56, tzinfo=timezone.utc),
        exchange_close=datetime(2024, 7, 3, 17, tzinfo=timezone.utc))
    result = review_risk(snap, side="long", shares=10,
                         entry_price=100., stop_price=95., cfg=StrategyConfig())
    assert result.mechanical_pass is False
    assert any("EOD" in blocker for blocker in result.blockers)


def test_preview_never_promotes_unverified_broker_stop_or_lean_risk_gate():
    review=review_risk(full_snapshot(), side="long", shares=10,
                       entry_price=100., stop_price=95., cfg=StrategyConfig())
    assert review.can_submit is False
    assert "orders" not in review.__dict__


def test_native_decimal_values_are_normalized_to_float():
    snap = full_snapshot(equity=Decimal("25000.00"),
                         available_buying_power=Decimal("24500.00"),
                         daily_start_equity=Decimal("25000.00"))
    assert type(snap.equity) is float
    result = review_risk(snap, side="long", shares=10,
                         entry_price=Decimal("100"),
                         stop_price=Decimal("95"), cfg=StrategyConfig())
    assert result.mechanical_pass is True
    assert result.can_submit is False


@pytest.mark.parametrize("bad", [1, 0, "true", 1.0])
def test_cashflow_provenance_accepts_only_an_explicit_boolean(bad):
    with pytest.raises(ValueError, match="period_cashflows_verified"):
        full_snapshot(period_cashflows_verified=bad)
