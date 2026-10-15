"""Source/causality regression checks for the separate research-only PPHL shadow.

Mocks native indicator events; these tests do NOT reproduce LEAN PPHL.
The actual PPHL implementation must be verified in Cloud backtest logs.
"""
import ast
from collections import Counter
from datetime import date, datetime, timedelta
from math import isfinite
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.patterns_bsu import BsuDetector


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
    sym = SimpleNamespace(value="TEST")
    # Named temporary class helps emulate Qwct's actual Symbol-keyed dict.
    agent = SimpleNamespace(
        cfg=StrategyConfig(),
        time=datetime(2024, 3, 12, 9, 29, tzinfo=ET),
        _raw_d1={},
        pphl_rejects=Counter(),
        pphl_counts=Counter(),
        pphl_unique=set(),
        pphl_only_unique=set(),
    )
    agent._raw_d1[id(sym)] = raw
    return agent, sym, raw, d1


def test_pphl_shadow_uses_native_event_and_origin_not_confirmation_bar(monkeypatch):
    module = ModuleType("AlgorithmImports")
    module.PivotPointsHighLow = StubPPHL
    monkeypatch.setitem(sys.modules, "AlgorithmImports", module)
    method = _shadow_method()
    agent, symbol, raw, d1 = _fixture()
    # Substitute a hashable LEAN-Symbol stand-in.
    key = "TEST-SYMBOL"
    agent._raw_d1 = {key: raw}
    cases = method(agent, key, d1, [], .01, date(2024, 3, 12))
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
    key = "TEST-SYMBOL"
    agent._raw_d1 = {key: raw}
    old = [{
        "side": "short",
        "origin_time": raw[3].end_time.isoformat(),
        "origin": 180.14,
    }]
    cases = method(agent, key, d1, old, .01, date(2024, 3, 12))
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
