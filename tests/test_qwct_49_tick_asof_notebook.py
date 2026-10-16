"""Guard the one-cell SRPT 4.9 native tick provenance diagnostic."""
import ast
from pathlib import Path

CELL = (Path(__file__).resolve().parents[1] /
        "research/chart_review_qc/QWCT_4_9_SRPT_NATIVE_TICK_ASOF_ONE_CELL.py")


def test_one_cell_native_history_only_and_no_execution():
    s = CELL.read_text(encoding="utf-8")
    tree = ast.parse(s, filename=str(CELL))
    assert any(isinstance(x, ast.FunctionDef) and
               x.name == "audit_native_tick_asof" for x in tree.body)
    assert "qb.history[Tick](" in s and "Resolution.TICK" in s
    assert "TickType.TRADE" in s and "TickType.QUOTE" in s
    assert "data_normalization_mode=DataNormalizationMode.RAW" in s
    assert "fill_forward=False" in s
    assert "CUTOFF + timedelta(seconds=1)" in s
    assert "if at > CUTOFF:" in s and "future_excluded += 1" in s
    assert "at = _et(x.time)" in s
    assert "raw_price=" in s and "bid=" in s and "ask=" in s
    assert "ONDATA_TIMELINESS_UNKNOWN" in s
    assert "NO_SYNTHETIC_CUTOFF" in s and "NOT_TVX_PASS" in s
    assert "NO_RELAXED_SEC_GAP" in s
    for forbidden in ("market_order(", "limit_order(", "set_holdings(",
                      "place_order(", "submit_order("):
        assert forbidden not in s.lower()


def test_asof_age_function_is_based_only_on_observed_tick_time():
    tree = ast.parse(CELL.read_text(encoding="utf-8"))
    f = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
             and x.name == "_age_seconds")
    assert isinstance(f.body[0], ast.Return)
    assert "CUTOFF - ts" in ast.unparse(f)
    assert "round" in ast.unparse(f)


def test_fail_closed_unknown_tick_data_and_invalid_quote():
    s = CELL.read_text(encoding="utf-8")
    assert "TICK_UNAVAILABLE" in s and "DATA_ENTITLEMENT_OR_HISTORY_UNVERIFIED" in s
    assert "TICK_BLOCKED TOO_MANY_TICKS" in s
    assert "if at < WINDOW_START:" in s
    assert "or bid > ask" in s and "qty <= 0" in s
    assert "HISTORICAL_TICKS_ONLY" in s
