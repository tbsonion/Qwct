"""Mock-shaped LEAN method contract tests; NOT QuantConnect runtime tests."""
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from strategy.config import StrategyConfig
from strategy.lean_risk_observer import review_native_lean_risk

ET = ZoneInfo("America/New_York")


def native_fixture(monkeypatch, *, buying_power=24500, positions=0, orders=()):
    api = ModuleType("AlgorithmImports")
    api.OrderDirection = SimpleNamespace(BUY="Buy", SELL="Sell")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    symbol = "NVDA"
    lookups = []
    class Portfolio:
        total_portfolio_value = Decimal("25000")
        def values(self):
            return [SimpleNamespace(quantity=1) for _ in range(positions)]
        def get_buying_power(self, s, direction):
            lookups.append((s, direction))
            return Decimal(str(buying_power))
    close = datetime(2024, 1, 2, 16, tzinfo=ET)
    hours = SimpleNamespace(
        get_next_market_close=lambda now, extended_market_hours: (
            close.replace(tzinfo=None)))
    algo = SimpleNamespace(
        cfg=StrategyConfig(), portfolio=Portfolio(),
        transactions=SimpleNamespace(get_open_orders=lambda: list(orders)),
        securities={symbol: SimpleNamespace(
            exchange=SimpleNamespace(hours=hours))},
        time=datetime(2024, 1, 2, 9, 35),
    )
    def index(value):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ET)
        return SimpleNamespace(to_pydatetime=lambda: value)
    return algo, symbol, lookups, index


def intent(**kwargs):
    state = dict(side="long", shares=10, limit_price=100., stop_price=95.)
    state.update(kwargs)
    return SimpleNamespace(**state)


def test_actual_native_portfolio_fields_do_not_invent_period_trade_history(monkeypatch):
    algo, symbol, lookups, index = native_fixture(monkeypatch)
    r = review_native_lean_risk(
        algo, symbol, intent(), datetime(2024, 1, 2, 14, 35, tzinfo=timezone.utc), index)
    assert lookups == [(symbol, "Buy")]
    assert r.projected_stop_risk == 50.
    assert r.mechanical_pass is None
    assert r.complete is False
    assert r.can_submit is False
    assert any("daily_start_equity" in b for b in r.blockers)


def test_native_buying_power_and_open_positions_are_mechanical_rejections(monkeypatch):
    algo, symbol, _, index = native_fixture(
        monkeypatch, buying_power=100, positions=3)
    r = review_native_lean_risk(
        algo, symbol, intent(), datetime(2024, 1, 2, 14, 35, tzinfo=timezone.utc), index)
    assert r.mechanical_pass is False
    assert any("buying-power" in b for b in r.blockers)
    assert any("max simultaneous" in b for b in r.blockers)
    assert r.can_submit is False


def test_any_open_order_is_not_mislabeled_as_new_pending_entry(monkeypatch):
    algo, symbol, _, index = native_fixture(monkeypatch, orders=("EXIT_ORDER",))
    r = review_native_lean_risk(
        algo, symbol, intent(), datetime(2024, 1, 2, 14, 35, tzinfo=timezone.utc), index)
    assert r.mechanical_pass is None
    assert any("pending_entries" in b for b in r.blockers)


def test_no_broker_orders_added_to_m5_native_risk_gate():
    root = Path(__file__).resolve().parents[1]
    code = (root / "strategy" / "m5_runtime.py").read_text()
    assert "review_native_lean_risk" in code
    assert 'False if failed else None' in code
    assert "self.limit_order(" not in code
    assert "self.market_order(" not in code


def test_native_portfolio_asof_cannot_reuse_later_data_for_earlier_m5(monkeypatch):
    algo, symbol, _, index = native_fixture(monkeypatch)
    with pytest.raises(ValueError, match="not aligned to completed M5"):
        review_native_lean_risk(
            algo, symbol, intent(),
            datetime(2024, 1, 2, 14, 0, tzinfo=timezone.utc),
            index)
