"""Pure coverage tests for QWCT 4.8b diagnostic; no LEAN/SRPT feed mock pass."""
import ast
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

CELL = (Path(__file__).resolve().parents[1] / "research" /
        "chart_review_qc/QWCT_4_8B_SEC_COVERAGE_POSITIVE_CONTROL_ONE_CELL.py")
ET = ZoneInfo("America/New_York")
START = datetime(2024, 6, 3, 14, 35, tzinfo=ET)
CUTOFF = START + timedelta(seconds=270)


def coverage():
    tree = ast.parse(CELL.read_text(encoding="utf-8"), filename=str(CELL))
    node = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                and x.name == "coverage_summary")
    ns = {"CLOCK_SECONDS": 270}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],
                  type_ignores=[])), str(CELL), "exec"), ns)
    return ns["coverage_summary"]


def rows(indices):
    return [(START + timedelta(seconds=i), 2.) for i in indices]


def test_all_observed_seconds_have_true_exact_cutoff_and_no_gaps():
    s = coverage()(rows(range(1, 271)), START, CUTOFF)
    assert s["traded_seconds"] == 270
    assert s["exact_cutoff"] and s["native_10s_gate_possible"]
    assert s["max_interval_s"] == 1 and s["intervals_over_10s"] == 0
    assert s["per_minute"] == [60, 60, 60, 60, 30]


def test_sparse_22_real_trades_cannot_pass_strict_270s_continuity():
    s = coverage()(rows(range(10, 221, 10)), START, CUTOFF)
    assert s["traded_seconds"] == 22
    assert not s["native_10s_gate_possible"]
    assert s["last_trade_age_s"] == 50
    assert s["max_interval_s"] == 50
    assert s["intervals_over_10s"] == 1


def test_missing_exact_cutoff_blocks_even_when_all_other_seconds_exist():
    s = coverage()(rows(range(1, 270)), START, CUTOFF)
    assert s["traded_seconds"] == 269
    assert not s["exact_cutoff"]
    assert not s["native_10s_gate_possible"]


def test_empty_and_duplicate_or_out_of_window_observations():
    s = coverage()([], START, CUTOFF)
    assert not s["native_10s_gate_possible"]
    assert s["traded_seconds"] == 0
    assert s["max_interval_s"] == 270
    with pytest.raises(ValueError, match="DUPLICATE"):
        coverage()(rows([1, 1]), START, CUTOFF)
    with pytest.raises(ValueError, match="OUT_OF_WINDOW"):
        coverage()(rows([271]), START, CUTOFF)


def test_scope_read_only_no_orders_no_artificial_seconds():
    source = CELL.read_text(encoding="utf-8")
    ast.parse(source)
    assert "Resolution.SECOND" in source
    assert "Resolution.MINUTE" in source
    assert '("SRPT", "SPY")' in source
    assert "fill_forward=False" in source
    assert "strict_10s_gate_possible" in source
    assert "NOT_TVX_NOT_BPU_NO_ORDERS" in source
    for key in ("market_order(", "limit_order(", "set_holdings(",
                "submit_order(", "place_order("):
        assert key not in source.lower()
