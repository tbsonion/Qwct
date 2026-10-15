"""Source/causality regression checks for the separate research-only PPHL shadow.

Mocks native indicator events; these tests do NOT reproduce LEAN PPHL.
The actual PPHL implementation must be verified in Cloud backtest logs.
"""
import ast
from collections import Counter
from datetime import date, datetime, timedelta, time
from math import isfinite
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.patterns_bsu import BsuDetector, Bar


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "research" / "bsu_cloud" / "main.py"
ET = ZoneInfo("America/New_York")


def _shadow_method():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "QwctBsuResearch")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_pphl_candidates")
    ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    env = {
        "et": lambda value: (pd.Timestamp(value).tz_localize(ET)
                             if pd.Timestamp(value).tz is None
                             else pd.Timestamp(value).tz_convert(ET)),
        "isfinite": isfinite,
        "BsuDetector": BsuDetector,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(APP), "exec"), env)
    return env["_pphl_candidates"]


class StubPPHL:
    """A single synthetic *confirmed* high event on seventh closed D1."""
    def __init__(self, high, low, limit):
        assert (high, low, limit) == (3, 3, 100)
        self.reads = 0
        self.is_ready = False
        self.current = SimpleNamespace(value=0)

    def update(self, closed_tradebar):
        assert closed_tradebar.end_time.tzinfo is not None
        self.reads += 1
        self.is_ready = self.reads >= 7
        self.current.value = 1 if self.reads == 7 else 0


def _fixture():
    first = datetime(2024, 3, 4, 16, tzinfo=ET)
    raw = [SimpleNamespace(end_time=first + timedelta(days=i))
           for i in range(7)]
    prices = [176.0, 177.0, 178.0, 180.14, 179.0, 178.0, 177.0]
    d1 = pd.DataFrame({
        "high": prices,
        "low": [p - 4 for p in prices],
        "bar_end": [bar.end_time for bar in raw],
        "atr14": [2.0] * 7,
    })
    class FakeSymbol:
        value = "TEST"

    sym = FakeSymbol()
    # Named temporary class helps emulate Qwct's actual Symbol-keyed dict.
    agent = SimpleNamespace(
        cfg=StrategyConfig(),
        time=datetime(2024, 3, 12, 9, 29, tzinfo=ET),
        _raw_d1={},
        pphl_rejects=Counter(),
        pphl_counts=Counter(),
        pphl_unique=set(),
        pphl_only_unique=set(),
        pphl_offgrid_unique=set(),
        pphl_offgrid_samples=[],
    )
    agent._raw_d1[sym] = raw
    return agent, sym, raw, d1


def test_pphl_shadow_uses_native_event_and_origin_not_confirmation_bar(monkeypatch):
    module = ModuleType("AlgorithmImports")
    module.PivotPointsHighLow = StubPPHL
    monkeypatch.setitem(sys.modules, "AlgorithmImports", module)
    method = _shadow_method()
    agent, symbol, raw, d1 = _fixture()
    cases = method(agent, symbol, d1, [], .01, date(2024, 3, 12))
    assert len(cases) == 1
    case = cases[0]
    assert case["side"] == "short"
    assert case["origin"] == pytest.approx(180.14)
    assert case["origin_time"] == raw[3].end_time.isoformat()
    assert case["confirmed_at"] == raw[6].end_time.isoformat()
    assert case["confirmed_at"] > case["origin_time"]
    assert agent.pphl_counts["only_level_days"] == 1
    assert agent.pphl_counts["overlap_level_days"] == 0
    assert case["detector"].state.level_price == pytest.approx(180.14)


def test_pphl_shadow_exact_origin_match_is_not_double_counted(monkeypatch):
    module = ModuleType("AlgorithmImports")
    module.PivotPointsHighLow = StubPPHL
    monkeypatch.setitem(sys.modules, "AlgorithmImports", module)
    method = _shadow_method()
    agent, symbol, raw, d1 = _fixture()
    old = [{
        "side": "short",
        "origin_time": raw[3].end_time.isoformat(),
        "origin": 180.14,
    }]
    cases = method(agent, symbol, d1, old, .01, date(2024, 3, 12))
    assert cases == []
    assert agent.pphl_counts["overlap_level_days"] == 1
    assert agent.pphl_counts["only_level_days"] == 0


def test_native_pphl_is_shadow_only_with_no_trading_or_scoring_changes():
    source = APP.read_text(encoding="utf-8")
    assert "PivotPointsHighLow(k, k, 100)" in source
    assert "native.update(daily)" in source
    assert "pivot_index = i - k" in source
    assert 'self._on_pphl_m5(bar, current)' in source
    assert 'self.active[sym] = states' in source
    assert 'self.pphl_shadow[sym] = self._pphl_candidates(' in source
    assert 'PPHL_FAIL:' in source
    assert "BSU PPHL COMPARE" in source
    assert "pphl_only_BPU2_strict=" in source
    assert "NO SEC TVX / NO ORDERS" in source
    for call in ("self.market_order(", "self.limit_order(",
                 "self.set_holdings(", "self.buy(", "self.sell("):
        assert call not in source


def _shadow_m5_method():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "QwctBsuResearch")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_on_pphl_m5")
    env = {"ResearchBar": Bar, "pd": pd, "time": time}
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(APP), "exec"), env)
    return env["_on_pphl_m5"]


def test_pphl_shadow_preserves_native_m5_proof_for_real_window_event():
    """Simulates native completed M5 pairs, not market data or fills."""
    k = "AAPL"
    origin = datetime(2024, 3, 19, 16, tzinfo=ET)
    detector = BsuDetector(
        StrategyConfig(), 179.53, "short",
        atr_value=2.0, tick_size=.01, bsu_ts=origin)
    case = {
        "symbol": k, "session": "2024-03-21", "side": "short",
        "origin": 179.53, "tick": .01,
        "origin_time": origin.isoformat(),
        "confirmed_at": datetime(2024, 3, 20, 16, tzinfo=ET).isoformat(),
        "detector": detector, "bpu1_strict": False, "bpu1_observed": None,
    }
    agent = SimpleNamespace(
        pphl_shadow={k: [case]}, pphl_counts=Counter(),
        pphl_rejects=Counter(), pphl_samples_logged=5,
        pphl_in_window_proofs=[], pphl_window_unique=set(),
        cfg=StrategyConfig(), log=lambda unused: None,
    )
    on_m5 = _shadow_m5_method()

    def candle(hour, minute, op, hi, lo, cl):
        end = datetime(2024, 3, 21, hour, minute, tzinfo=ET)
        c = SimpleNamespace(
            symbol=k, open=op, high=hi, low=lo, close=cl, volume=1000.)
        on_m5(agent, c, pd.Timestamp(end))

    candle(13, 10, 179.49, 179.53, 179.45, 179.47)
    assert agent.pphl_counts["only_bpu1_strict"] == 1
    assert len(agent.pphl_in_window_proofs) == 0
    candle(13, 15, 179.47, 179.50, 179.42, 179.45)
    assert agent.pphl_counts["only_bpu2_detector"] == 1
    assert agent.pphl_counts["only_bpu2_strict"] == 1
    assert agent.pphl_counts["only_bpu2_strict_in_window"] == 1
    assert len(agent.pphl_window_unique) == 1
    assert len(agent.pphl_in_window_proofs) == 1
    proof = agent.pphl_in_window_proofs[0]
    assert proof[0] == k
    assert proof[3] == 179.53
    assert proof[7][2] == 179.53
    assert proof[8][1] == 179.50
    assert proof[5] > proof[4]
    assert agent.pphl_rejects == {}


def test_offgrid_pivot_is_skipped_and_deduplicated(monkeypatch):
    module = ModuleType("AlgorithmImports")
    module.PivotPointsHighLow = StubPPHL
    monkeypatch.setitem(sys.modules, "AlgorithmImports", module)
    method = _shadow_method()
    agent, symbol, raw, d1 = _fixture()
    d1.loc[3, "high"] = 180.145
    cases = method(agent, symbol, d1, [], .01, date(2024, 3, 12))
    assert cases == []
    assert agent.pphl_rejects["off-grid native PPHL origin"] == 1
    assert len(agent.pphl_offgrid_unique) == 1
    assert len(agent.pphl_offgrid_samples) == 1
    method(agent, symbol, d1, [], .01, date(2024, 3, 12))
    assert agent.pphl_rejects["off-grid native PPHL origin"] == 2
    assert len(agent.pphl_offgrid_unique) == 1
    assert len(agent.pphl_offgrid_samples) == 1


def test_pphl_win_proofs_are_logged_separately_from_capped_event_logs():
    src = APP.read_text(encoding="utf-8")
    for term in (
        "BSU PPHL WINDOW PROOF", "BSU PPHL WINDOW OHLC",
        "BSU PPHL EVIDENCE", "BSU PPHL OFFGRID",
        "unique_level_day_episodes=", "unique_offgrid_origins=",
        'self.pphl_in_window_proofs.append((',
        'self.pphl_window_unique.add(episode_key)',
    ):
        assert term in src
