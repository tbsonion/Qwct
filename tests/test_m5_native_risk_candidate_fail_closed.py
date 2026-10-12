"""Real extracted M5 callback, fake native adapter results. No LEAN engine or fills."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

import strategy.m5_runtime as runtime
from strategy.config import StrategyConfig
from strategy.risk_research import RiskPreflight
from strategy.signals import TradeIntent, GateResult, GATE_IDS


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class NativeSymbol:
    value: str


NVDA = NativeSymbol("NVDA")


def harness():
    a = SimpleNamespace()
    a._signals_open = True
    a._session_date = datetime(2024, 1, 2).date()
    a.screen_watchlist = (NVDA,)
    a._symbols = {
        NVDA: {
            "daily_rows": [], "m5_rows": [], "bsu_link": None, "setup_trace": None,
            "decision": SimpleNamespace(accepted=True, score=6.0),
            "qualified_today": False, "session_levels": (),
        }}
    a._m5_bars_seen = 0
    a._m5_input_rejections = Counter()
    a._m5_checks = 0
    a._intent_missing_atr = 0
    a._chart_symbol = "AAPL"
    a._focus_m5_plotted = 0
    a._m5_true_by_model = Counter()
    a._m5_true_other_blockers = Counter()
    a._gate_failures = Counter()
    a.cfg = StrategyConfig()
    a.portfolio = SimpleNamespace(total_portfolio_value=25000.)
    a._session_policy = SimpleNamespace(
        is_entry_allowed=lambda model, ts: (True, "test window"))
    a.records = []
    a._record = lambda symbol, event, *args: a.records.append((symbol, event, args))
    a._frame = lambda rows: pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()
    a.error = lambda msg: a.records.append(("ERROR", str(msg)))
    return a


def candidate_intent():
    at = datetime(2024, 1, 2, 10, 40, tzinfo=ET)
    value = TradeIntent(
        symbol="NVDA", session=at.date(), signal_at=at,
        side="long", model="breakout", level_price=100,
        limit_price=100, stop_price=95, risk_per_share=5,
        shares=10, tp_r=3, room_r=4)
    value.gates = {name: GateResult(name, True, "test")
                   for name in GATE_IDS}
    value.gates["risk_approved"] = GateResult("risk_approved", None, "unknown")
    return value


def deliver(a):
    at = datetime(2024, 1, 2, 10, 40, tzinfo=ET)
    b = SimpleNamespace(
        symbol=NVDA, end_time=at,
        open=100., high=101., low=99., close=100., volume=100.)
    runtime.process_m5(a, b, pd.Timestamp)


def test_native_risk_adapter_failure_cannot_emit_research_candidate(monkeypatch):
    a = harness()
    value = candidate_intent()
    monkeypatch.setattr(runtime, "build_intent", lambda *_args, **_kwargs: value)
    def api_failure(*_args, **_kwargs):
        raise RuntimeError("LEAN native evidence unavailable")
    monkeypatch.setattr(runtime, "review_native_lean_risk", api_failure)
    deliver(a)
    assert not any(row[1] == "RESEARCH_CANDIDATE" for row in a.records)
    assert value.gates["risk_approved"].passed is None
    assert "failed closed" in value.gates["risk_approved"].reason
    assert a._m5_checks == 1
    assert a._symbols[NVDA]["qualified_today"] is False


def test_partial_native_risk_evidence_allows_only_labeled_preliminary_candidate(monkeypatch):
    a = harness()
    value = candidate_intent()
    monkeypatch.setattr(runtime, "build_intent", lambda *_args, **_kwargs: value)
    monkeypatch.setattr(runtime, "review_native_lean_risk", lambda *_args, **_kwargs:
                        RiskPreflight(None, False, 50., 1000.,
                                      ("unknown native daily_start_equity",), False))
    deliver(a)
    assert [event for _, event, *_rest in a.records] == ["RESEARCH_CANDIDATE"]
    assert value.gates["risk_approved"].passed is None
    assert a._symbols[NVDA]["qualified_today"] is True


def test_known_native_rejection_blocks_candidate(monkeypatch):
    a = harness()
    value = candidate_intent()
    monkeypatch.setattr(runtime, "build_intent", lambda *_args, **_kwargs: value)
    monkeypatch.setattr(runtime, "review_native_lean_risk", lambda *_args, **_kwargs:
                        RiskPreflight(False, False, 50., 1000.,
                                      ("max simultaneous positions reached",), False))
    deliver(a)
    assert not any(row[1] == "RESEARCH_CANDIDATE" for row in a.records)
    assert value.gates["risk_approved"].passed is False
