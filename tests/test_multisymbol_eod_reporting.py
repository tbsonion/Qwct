"""No broker simulations: test the report format and fail-closed source contract."""
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

from strategy.reporting import (
    SIGNAL_FIELDS, ORDER_FIELDS, TRADE_FIELDS, csv_rows,
    native_order_event_row, native_closed_trade_rows, summary_json
)


def test_decisions_export_as_consistent_csv():
    rows = [{"time_et": "2026-10-09 11:00", "symbol": "MSFT",
             "type": "INTENT", "model": "bounce", "side": "long",
             "reason": "NO ORDERS SENT"}]
    result = list(csv.DictReader(io.StringIO(csv_rows(rows, SIGNAL_FIELDS))))
    assert len(result) == 1
    assert result[0]["symbol"] == "MSFT"
    assert result[0]["model"] == "bounce"
    assert result[0]["entry"] == ""


def test_real_order_event_fields_are_passed_through_unchanged():
    # This validates serialization only, NOT a fake broker or simulated fill.
    ev = SimpleNamespace(
        utc_time="2026-10-09T17:00:00Z", order_id=42, symbol="AAPL",
        status="Filled", direction="Buy", fill_quantity=10,
        fill_price=200.5, order_fee="0 USD", message="Filled")
    row = native_order_event_row(ev, tag="ENTRY")
    assert row["order_id"] == "42"
    assert row["fill_price"] == "200.5"
    assert row["tag"] == "ENTRY"
    parsed = list(csv.DictReader(io.StringIO(csv_rows([row], ORDER_FIELDS))))
    assert parsed[0] == row


def test_closed_trade_data_comes_from_trade_builder_fields():
    closed = [
        SimpleNamespace(symbol="AAPL", entry_time="09:30", exit_time="10:00",
                        direction="Long", quantity=10, entry_price=200.,
                        exit_price=203., profit_loss=30., total_fees=5., is_win=True),
        SimpleNamespace(symbol="MSFT", entry_time="10:30", exit_time="11:00",
                        direction="Short", quantity=5, entry_price=400.,
                        exit_price=402., profit_loss=-10., total_fees=1., is_win=False),
    ]
    rows = native_closed_trade_rows(closed)
    assert all(set(x) == set(TRADE_FIELDS) for x in rows)
    parsed = json.loads(summary_json(
        [{"type": "INTENT"}, {"type": "REJECT"}], [], rows, invested=False))
    assert parsed["closed_trades"] == 2
    assert parsed["net_winning_trades"] == 1
    assert parsed["closed_trade_gross_profit_loss"] == 20
    assert parsed["closed_trade_total_fees"] == 6
    assert parsed["closed_trade_net_profit_loss"] == 14
    assert rows[0]["net_profit_loss"] == "25.0"
    assert rows[1]["net_profit_loss"] == "-11.0"
    assert parsed["signals"] == 1
    assert parsed["positions_still_open"] is False


def test_source_uses_actual_leans_native_multi_symbol_events():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "self.universe_settings.resolution = Resolution.MINUTE" in src
    assert "self.universe_settings.fill_forward = False" in src
    assert "self._symbols[symbol] = state" in src
    assert "self.consolidate(" in src
    assert "self.subscription_manager.remove_consolidator(" in src
    assert "symbol not in self.screen_watchlist" in src
    assert "MarketData(" in src
    assert "self._scenario_evaluator.evaluate(" in src
    assert "self._session_policy.is_entry_allowed(" in src
    assert "self._native_exit_enabled = False" in src
    # Real-cloud diagnostics require native runtime statistics and charts,
    # not synthetic signal outcomes or an unavailable ObjectStore.
    assert 'self.plot("Qwct Research", "Screener"' in src
    assert '"Qwct Research", "D1 scenarios"' in src
    assert '"Qwct Research", "Signal intents"' in src
    assert "self.set_runtime_statistic(" in src
    assert "self._gate_failures[name] += 1" in src
    assert "self._m5_bars_seen += 1" in src
    assert "Qwct M5 bars" in src
    assert "ObjectStore DISABLED: decision CSV/JSON NOT saved." in src


def test_eod_uses_schwab_documented_cancel_then_liquidate_ordering():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    cancel = src.index("    def _cancel_before_close(self)")
    end = src.index("    def _end_session(self)")
    verify = src.index("    def _verify_flat_before_close(self)")
    events = src.index("    def on_order_event(self, event: OrderEvent)")
    assert cancel < end < verify < events
    assert "self.transactions.cancel_open_orders()" in src[cancel:end]
    assert "if self.transactions.get_open_orders():" in src[end:verify]
    assert "self.liquidate(tag=" in src[end:verify]
    assert "if not self._native_exit_enabled:" in src[cancel:end]
    assert "if not self._native_exit_enabled:" in src[end:verify]
    assert "self.portfolio.invested" in src[verify:events]
    assert not any(k in src for k in ("class OrderManager", "NativeGateway",
                                      "self.bracket_order(", "self.market_order("))


def test_native_reporting_object_store_and_trade_builder():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "def on_order_event(" in src
    assert "native_order_event_row(event, tag)" in src
    assert "self.trade_builder.closed_trades" in src
    assert "self.object_store.save(" in src
    assert "self._object_store_export_enabled = False" in src
    assert "if not self._object_store_export_enabled:" in src
    assert "ObjectStore DISABLED: decision CSV/JSON NOT saved." in src
    assert "on_end_of_algorithm" in src
    assert "self.set_trade_builder(TradeBuilder(" in src
    assert "FillGroupingMethod.FLAT_TO_FLAT" in src
    assert "self.time_rules.after_market_close(self.symbol, 1)" in src
    assert "def _checkpoint_reports(self)" in src
    assert "def on_end_of_day(self, symbol:" not in src


def test_missing_real_trade_fee_property_fails_instead_of_lying():
    # The upstream LEAN Trade class exposes total_fees, not fees.
    closed = [SimpleNamespace(
        symbol="AAPL", entry_time="9:30", exit_time="10:00",
        direction="Long", quantity=1, entry_price=100,
        exit_price=104, profit_loss=4, fees=0, is_win=True)]
    import pytest
    with pytest.raises(AttributeError):
        native_closed_trade_rows(closed)


def test_native_batched_history_warmup_and_no_synthetic_indicators():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "def _warm_symbols(self, symbols)" in src
    assert "symbols, 180, Resolution.DAILY" in src
    # Real LEAN 2.5 returns a TradeBars collection for each historical
    # time slice; treating that outer item as TradeBar caused the real
    # cloud error: 'TradeBars' object has no attribute 'symbol'.
    assert "for bars in self.history[TradeBar](" in src
    assert "for symbol, bar in bars.items():" in src
    assert "for bar in self.history[TradeBar](" not in src
    assert "self._warm_symbols(new_symbols)" in src
    assert "if self._register_symbol(self.symbol):" in src
    assert "FillGroupingMethod.FLAT_TO_FLAT" in src
    assert "self.time_rules.after_market_close(self.symbol, 1)" in src
