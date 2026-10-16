"""Pure regression checks for the ONE-CELL QuantConnect 4.3 SRPT audit.

Test the actual helper extracted from the notebook (no LEAN/QuantBook needed).
Synthetic data cannot validate the native feed, author BSU or SEC TVX.
"""
import ast
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from strategy.config import StrategyConfig
from strategy.patterns_bsu import Bar, BsuDetector

CELL = (Path(__file__).resolve().parents[1] / "research" /
        "chart_review_qc" / "QWCT_4_2_SRPT_M5_VISUAL_AUDIT_ONE_CELL.py")
ET = ZoneInfo("America/New_York")
CFG = StrategyConfig()


def load_actual_audit():
    source = CELL.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CELL))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "audit_bpu2_luft")
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    namespace = {"BsuDetector": BsuDetector, "timedelta": timedelta}
    exec(compile(module, str(CELL), "exec"), namespace)
    return namespace["audit_bpu2_luft"]


def sample(*, side="long", price=123.87, bpu2_offset=0.17,
           bpu2_gap=False):
    base = datetime(2024, 6, 3, 14, 15, tzinfo=ET)
    bpu1_end = base + timedelta(minutes=20)
    bpu2_end = bpu1_end + timedelta(minutes=(10 if bpu2_gap else 5))
    if side == "long":
        source = Bar(base, price+0.18, price+0.28, price, price+0.18,
                     volume=100)
        bpu1 = Bar(bpu1_end, price+0.20, price+0.38, price, price+0.30,
                   volume=100)
        low = price+bpu2_offset
        bpu2 = Bar(bpu2_end, low+0.10, low+0.38, low, low+0.19,
                   volume=100)
    else:
        source = Bar(base, price-0.18, price, price-0.38, price-0.18,
                     volume=100)
        bpu1 = Bar(bpu1_end, price-0.15, price, price-0.45, price-0.20,
                   volume=100)
        high = price-bpu2_offset
        bpu2 = Bar(bpu2_end, high-0.10, high, high-0.38, high-0.19,
                   volume=100)
    return source, bpu1, bpu2


def audit(*args, price=123.87, side="long"):
    return load_actual_audit()(
        *args, price, side, 4.0, 0.01, CFG)


def test_synthetic_srpt_12387_17_cent_bpu2_is_within_calculated_luft():
    result = audit(*sample())
    assert result["passed"]
    assert result["stop"] == pytest.approx(122.87)
    assert result["luft"] == pytest.approx(0.20)
    assert result["signed_offset"] == pytest.approx(0.17)
    assert result["next_m5"] and not result["pierced_bpu1"]
    assert not result["beyond_luft"]
    assert result["phase"] == "bpu2_confirmed"


@pytest.mark.parametrize("offset, gap", [(0.25, False), (-0.02, False),
                                          (0.17, True)])
def test_bpu2_beyond_luft_pierced_bpu1_or_delayed_bar_is_rejected(offset, gap):
    result = audit(*sample(bpu2_offset=offset, bpu2_gap=gap))
    assert not result["passed"]


def test_short_side_symmetric_luft_check():
    assert audit(*sample(side="short", price=100.0),
                 side="short", price=100.0)["passed"]
    assert not audit(*sample(side="short", price=100.0, bpu2_offset=0.25),
                     side="short", price=100.0)["passed"]


def test_research_notebook_is_one_cell_and_cannot_hide_rejected_source():
    source = CELL.read_text(encoding="utf-8")
    ast.parse(source, filename=str(CELL))
    assert "REJECTED_SOURCE" in source
    assert "SKIPPED_SOURCE_INVALID" in source
    assert "SCANNER_VS_BPU2_LUFT_MISMATCH" in source
    assert "NO_PRE_CLOSE_SEC_TVX" in source
    assert "fig.show()" in source
    assert "FAIL_CLOSED_BPU2_NOT_REPRODUCED" not in source
    for order_api in ("market_order(", "limit_order(", "set_holdings("):
        assert order_api not in source.lower()
