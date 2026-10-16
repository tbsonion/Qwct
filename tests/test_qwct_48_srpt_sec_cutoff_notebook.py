"""QWCT 4.8 read-only native SEC notebook: pure regression checks.

These fixtures do NOT claim QuantConnect historical SEC availability or
real on_data delivery timing. The canonical SEC validator must not drift.
"""
import ast
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from strategy.native_m5_validation import _duration_seconds

ROOT = Path(__file__).resolve().parents[1]
CELL = ROOT / "research/chart_review_qc/QWCT_4_8_SRPT_NATIVE_SEC_TVX_ONE_CELL.py"
SOURCE = ROOT / "strategy/native_second_tvx.py"
VALIDATOR = ROOT / "strategy/native_m5_validation.py"
ET = ZoneInfo("America/New_York")
BPU1 = datetime(2024, 6, 3, 14, 35, tzinfo=ET)
CUTOFF = BPU1 + timedelta(minutes=4, seconds=30)


def _lookup(tree, name):
    return next(n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                and n.name == name)


def _runtime():
    tree = ast.parse(CELL.read_text(encoding="utf-8"))
    nodes = [_lookup(tree, "_duration_seconds"),
             _lookup(tree, "NativePrecloseSample"),
             _lookup(tree, "NativeSecondTvxWindow")]
    namespace = {
        "__name__": __name__, "datetime": datetime, "timedelta": timedelta,
        "dataclass": dataclass, "isfinite": isfinite
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(CELL), "exec"), namespace)
    return namespace["NativeSecondTvxWindow"]


def sec(end, **overrides):
    x = dict(
        time=end-timedelta(seconds=1), end_time=end,
        period=timedelta(seconds=1), symbol="SRPT",
        open=124.11, high=124.12, low=124.08,
        close=124.10, volume=4, is_fill_forward=False)
    x.update(overrides)
    return SimpleNamespace(**x)


def test_embedded_native_validator_matches_canonical_implementation():
    t = ast.parse(CELL.read_text(encoding="utf-8"))
    s = ast.parse(SOURCE.read_text(encoding="utf-8"))
    v = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    for name in ("NativePrecloseSample", "NativeSecondTvxWindow"):
        assert ast.dump(_lookup(t, name)) == ast.dump(_lookup(s, name))
    assert ast.dump(_lookup(t, "_duration_seconds")) == ast.dump(
        _lookup(v, "_duration_seconds"))


def test_exact_270_native_seconds_cutoff_yields_provisional_sample_only():
    w = _runtime()(BPU1)
    for i in range(1, 270):
        assert w.accept(sec(BPU1+timedelta(seconds=i)), symbol="SRPT") is None
    sample = w.accept(sec(CUTOFF), symbol="SRPT")
    assert sample is not None
    assert sample.observed_at == CUTOFF
    assert sample.bpu2_end == BPU1 + timedelta(minutes=5)
    assert sample.observed_bars == 270
    assert sample.unobserved_seconds == 0
    assert sample.can_submit is False


def test_no_exact_cutoff_second_cannot_claim_timed_preclose():
    w = _runtime()(BPU1)
    for i in range(1, 270):
        assert w.accept(sec(BPU1+timedelta(seconds=i)), symbol="SRPT") is None
    assert not w.complete
    assert w.accept(sec(CUTOFF+timedelta(seconds=1)), symbol="SRPT") is None
    assert w.blocked_reason == "SEC_OUTSIDE_BPU2_PRECLOSE_WINDOW"


def test_bounded_real_sparse_feed_passes_but_large_gap_blocks():
    w = _runtime()(BPU1)
    for i in range(1, 271):
        if i % 7 != 0 or i == 270:
            sample = w.accept(sec(BPU1+timedelta(seconds=i)), symbol="SRPT")
    assert sample is not None
    assert sample.unobserved_seconds > 0
    assert not sample.can_submit
    w2 = _runtime()(BPU1)
    assert w2.accept(sec(BPU1+timedelta(seconds=1)), symbol="SRPT") is None
    assert w2.accept(sec(BPU1+timedelta(seconds=12)), symbol="SRPT") is None
    assert w2.blocked_reason == "SEC_UNOBSERVED_GAP_OVER_10S"


def test_no_synthetic_m1_fill_forward_wrong_symbol_or_fake_cutoff():
    for extras in ({"period": timedelta(minutes=1)},
                   {"is_fill_forward": True},
                   {"symbol": "MSFT"},
                   {"volume": 0}):
        w = _runtime()(BPU1)
        assert w.accept(sec(BPU1+timedelta(seconds=1), **extras),
                        symbol="SRPT") is None
        assert w.blocked_reason
        assert not w.complete


def test_historical_scope_never_promotes_sec_into_an_order():
    source = CELL.read_text(encoding="utf-8")
    ast.parse(source)
    assert "Resolution.SECOND" in source
    assert "fill_forward=False" in source
    assert "NO_CLOSED_BPU2_USED" in source
    assert "ONDATA_DELIVERY_TIMELINESS_UNVERIFIED" in source
    assert "SEC_PRECLOSE_CUTOFF_NOT_OBSERVED" in source
    assert "NO_ORDERS" in source
    assert "SOURCE_PRICE = 123.87" in source
    for forbidden in ("market_order(", "limit_order(", "set_holdings(",
                      "submit_order(", "brokerage"):
        assert forbidden not in source.lower()
