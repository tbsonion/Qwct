"""Guard small Cloud one-cell QWCT 5.0 against drifting from canonical core."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "strategy/m5_reaction_taxonomy.py"
CELL = ROOT / "research/chart_review_qc/QWCT_5_0_SRPT_M5_TEN_REACTIONS_ONE_CELL.py"


def _named(tree, key):
    return next(n for n in tree.body if isinstance(n, (ast.Assign,
        ast.ClassDef)) and (getattr(n,"name",None)==key or
        isinstance(n,ast.Assign) and any(
        isinstance(t,ast.Name) and t.id==key for t in n.targets)))


def test_one_cell_embeds_same_10_reaction_source_no_extra_cloud_module():
    x = ast.parse(CORE.read_text(encoding="utf-8"))
    y = ast.parse(CELL.read_text(encoding="utf-8"))
    for name in ("KINDS","M5ReactionEvent", "M5ReactionHeuristics",
                 "M5TenReactionObserver"):
        assert ast.dump(_named(x,name)) == ast.dump(_named(y,name))


def test_native_m5_not_synthetic_no_import_new_strategy_core():
    s = CELL.read_text(encoding="utf-8")
    ast.parse(s)
    assert 'from strategy.m5_reaction_taxonomy import' not in s
    assert "Resolution.MINUTE" in s
    assert "DataNormalizationMode.RAW" in s
    assert "fill_forward=False" in s
    assert "TradeBarConsolidator(timedelta(minutes=5))" in s
    assert "any(end-timedelta(minutes=j) not in minute_ends for j in range(5))" in s
    assert "AverageTrueRange(14, MovingAverageType.WILDERS)" in s
    assert "m5_atr = AverageTrueRange(14, MovingAverageType.WILDERS)" in s
    assert "MISSING_M5=" in s and "GAP_RESETS=" in s
    assert "levels_for_session(frame, SESSION, cfg)" in s
    assert "CONTEXT_PRICE = 125.00" in s
    assert "KIND={lvl.kind}" in s
    assert "ALL_10_RULES_CHECKED" in s and "fig.show()" in s
    assert "NOT_ALL_10_MUST_APPEAR_IN_ONE_SESSION" in s
    assert "NOT_FIXED_BSU_NOT_AUTHOR_APPROVED" in s
    for forbidden in ("market_order(", "limit_order(", "set_holdings(",
                      "submit_order(", "place_order(", "live_deploy("):
        assert forbidden not in s.lower()
