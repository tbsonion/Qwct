"""Read-only new Cloud project: source integration and canonical module reuse.

These are source checks, NOT proof that native LEAN Cloud emitted BPU signals.
"""
import ast
from pathlib import Path

from strategy.config import StrategyConfig
from strategy.levels import Level, native_cluster_tolerance
from strategy.patterns_bsu import Bar, BsuDetector

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "research" / "bsu_cloud" / "main.py"


def test_new_research_main_parses_and_never_places_orders():
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(isinstance(x, ast.ClassDef)
               and x.name == "QwctBsuResearch" for x in tree.body)
    assert "ALL ORDERS DISABLED" in source
    forbidden = ("self.market_order(", "self.limit_order(",
                 "self.set_holdings(", "self.liquidate(",
                 "self.bracket_order(", "self.buy(", "self.sell(")
    assert not any(term in source for term in forbidden)
    assert "OrderManager" not in source
    assert "FillGroupingMethod" not in source


def test_research_reuses_native_history_m5_and_canonical_bsu_modules():
    source = APP.read_text(encoding="utf-8")
    assert "from strategy.levels import levels_for_session" in source
    assert "from strategy.patterns_bsu import Bar as ResearchBar, BsuDetector" in source
    assert "from strategy.native_m5_validation import validate_m5_tradebar" in source
    assert "data_normalization_mode=DataNormalizationMode.RAW" in source
    assert "self.history[TradeBar]" in source
    assert "AverageTrueRange(" in source
    assert "self.consolidate(sym, timedelta(minutes=5), self._on_m5)" in source
    assert "self.schedule.on(" in source
    assert "scan_start" in source and "scan_end" in source
    assert "(end - start).days > 45" in source
    assert "BSU RESEARCH SUMMARY" in source
    assert "BSU RESEARCH NEAREST" in source
    assert "BSU RESEARCH BPU1" in source
    assert "BSU RESEARCH BPU2" in source
    assert "scored_ge_threshold" not in source
    assert "min_model_score" not in source
    assert "self.cfg.bpu_tick_tol_atr" not in source


def test_research_package_dependencies_exist_and_do_not_pull_live_code():
    packages = (
        "strategy/__init__.py", "strategy/config.py",
        "strategy/indicators.py", "strategy/levels.py",
        "strategy/patterns_bsu.py", "strategy/native_m5_validation.py",
    )
    for name in packages:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        assert tree is not None
    assert callable(native_cluster_tolerance)
    assert isinstance(StrategyConfig(), StrategyConfig)
    assert isinstance(Level(100., "resistance"), Level)
    assert callable(BsuDetector)
    assert callable(Bar)
