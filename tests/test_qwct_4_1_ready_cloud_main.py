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
    assert "No module named 'strategy.scenarios'" not in text
    for disallowed in ("market_order(", "limit_order(", "set_holdings(",
                       "self.buy(", "self.sell(", "place_order(",
                       "self.add_crypto(", "self.add_forex("):
        assert disallowed not in text.lower()
    assert "BPU1_EXACT=" in text and "BPU2_CLOSED=" in text
    assert "SAME_SESSION_ONLY" in text


def test_42_history_request_is_never_future_and_flushes_real_last_m5():
    script=DRIVER.read_text(encoding="utf-8")
    assert "SESSION,  # Only history known at Initialize (00:00 ET)." in script
    assert "SESSION.replace(hour=9, minute=29)" not in script
    assert 'state["consolidator"].scan(datetime(' in script
    assert "ACTUAL_1M=" in script and "REJECTED_OR_UNPUBLISHED_M5=" in script
    assert 'COMPLETE_M5=' in script
    assert 'range(390)' in script and 'range(78)' in script


def test_42_srpt_graph_marks_only_reproduced_native_m5_sources():
    cell=DRIVER.with_name("QWCT_4_2_SRPT_M5_VISUAL_AUDIT_ONE_CELL.py")
    source=cell.read_text(encoding="utf-8")
    import ast
    ast.parse(source, filename=str(cell))
    assert '"SRPT"' in source
    assert "123.51" in source and "123.87" in source
    assert '("12:35","13:40","13:45")' not in source  # price is included
    assert "12:35" in source and "13:40" in source and "13:45" in source
    assert "14:15" in source and "14:35" in source and "14:40" in source
    assert "FAIL_CLOSED_BPU2_NOT_REPRODUCED" in source
    assert "OHLC" in source and "fig.show()" in source
    assert "M5BsuSequenceScanner" in source
    assert "market_order(" not in source.lower()
    assert "set_holdings(" not in source.lower()
