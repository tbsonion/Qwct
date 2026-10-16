"""Static guard for the copy-paste-only QWCT 4.1 Cloud backtest entrypoint."""
import ast
from pathlib import Path

DRIVER = (Path(__file__).resolve().parents[1] / "research" /
          "chart_review_qc" / "QWCT_4_1_READY_BACKTEST_MAIN.py")


def test_lean_cloud_backtest_driver_is_valid_python_and_no_missing_app_modules():
    text = DRIVER.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(DRIVER))
    assert any(isinstance(n, ast.ClassDef) and
               n.name=="QwctM5SourceResearch" for n in tree.body)
    imports = {a.module for a in ast.walk(tree)
               if isinstance(a, ast.ImportFrom)}
    assert "strategy.config" in imports
    assert "strategy.levels" in imports
    assert "strategy.patterns_bsu" in imports
    # This intentionally runs in the SMALL Cloud Research project. Do not
    # pull the production main.py's other absent strategy modules.
    forbidden = ("strategy.scenarios", "strategy.bsu_bridge",
                 "strategy.breakout_retest", "strategy.sessions",
                 "strategy.research_trace", "strategy.second_runtime",
                 "strategy.corporate_action_guard", "strategy.reporting")
    assert not any(k in imports for k in forbidden)
    assert "main.py" not in text.splitlines()[0]  # source is a reusable file
    assert "No module named 'strategy.scenarios'" not in text
    for disallowed in ("market_order(", "limit_order(", "set_holdings(",
                       "self.buy(", "self.sell(", "place_order(",
                       "self.add_crypto(", "self.add_forex("):
        assert disallowed not in text.lower()
    assert "BPU1_EXACT=" in text and "BPU2_CLOSED=" in text
    assert "SAME_SESSION_ONLY" in text
