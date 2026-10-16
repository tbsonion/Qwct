"""QWCT 3.1: read-only first-day mirror source/M5 code guards.

Unit tests only inspect pure signed wick geometry and source implementation.
No mocked broker, no false LEAN-native runtime PASS claim.
"""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import pandas as pd


ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"research"/"chart_review_qc"/"MIRROR_JUNE03_RAW_D1_NATIVE_M5_ONE_CELL.py"


def fn(name):
    script=ast.parse(SRC.read_text(encoding="utf8"))
    target=next(n for n in script.body
                if isinstance(n,ast.FunctionDef) and n.name==name)
    globs={"pd":pd}
    exec(compile(ast.Module(body=[target],type_ignores=[]),str(SRC),"exec"),globs)
    return globs[name]


def test_exact_original_source_distinguished_from_cluster_median_and_span():
    check=fn("m5_geometry")
    date=pd.to_datetime(["2024-06-03 09:35","2024-06-03 09:40",
                         "2024-06-03 09:45","2024-06-03 09:50"])
    # Long setups: low, not high, matters for exact BPU1 wick geometry.
    bars=pd.DataFrame({"verified_m5":[True,True,True,True],
                       "low":[99.00,98.90,99.12,99.00],
                       "high":[100.00,99.50,99.80,100.00],
                       "close":[99.5,99.2,99.5,99.7]},
                      index=date)
    r=check(bars,99.00,99.12,"long",0.01)
    assert r["exact"]==2
    assert r["span"]==1   # 98.90 to 99.50 passed raw source without exact low
    assert r["median_exact"]==1
    assert r["checked"]==4
    assert r["first_span"]==date[1]


def test_missing_source_minutes_excluded_without_fake_bpu1():
    check=fn("m5_geometry")
    date=pd.to_datetime(["2024-06-03 09:35","2024-06-03 09:40"])
    bars=pd.DataFrame({"verified_m5":[False,True],"low":[96.00,98.9],
                       "high":[99.00,99.00]},index=date)
    r=check(bars,99.00,98.99,"short",0.01)
    assert r["checked"]==1
    assert r["exact"]==1
    assert r["span"]==0
    assert r["median_exact"]==0


def test_mirror_research_cases_frozen_before_intraday_data():
    s=SRC.read_text(encoding="utf8")
    ast.parse(s)
    assert len(s.encode("utf8"))<32_000
    for name,price in (("AMAT","214.4600"),("NFLX","633.7750"),
                       ("SRPT","125.0000"),("MSFT","415.5900")):
        assert f'ticker="{name}",cluster={price}' in s
    assert 'decision="NEGATIVE_ROLE_CONTROL"' in s
    assert "MIRROR_COHORT_FREEZE_MISMATCH" in s
    assert "FROZEN_3_0_ELIGIBILITY_MISMATCH" in s
    assert "level.first_idx not in good_idx or level.last_idx not in good_idx" in s
    assert "qb.set_start_date(2024,7,1)" in s
    assert "D1_180_ASOF_CHECK_FAILED" in s
    assert "SESSION=datetime(2024,6,3)" in s
    assert "source_at.date()" in s


def test_native_source_no_synthetic_m5_or_broker_code():
    s=SRC.read_text(encoding="utf8")
    for marker in (
        "qb.history[TradeBar](", "data_normalization_mode=DataNormalizationMode.RAW",
        "DataNormalizationMode.SCALED_RAW",
        "original=list(qb.history[TradeBar](",
        "TradeBarConsolidator(timedelta(minutes=5))",
        "consolidator.data_consolidated+=collect",
        "consolidator.update(b)",
        "consolidator.scan(minute[-1].end_time)",
        "validate_m5_tradebar(b,be.to_pydatetime())",
        "full5=all((bt+timedelta(minutes=i)) in starts for i in range(5))",
        "first_missing_ET=",
        "RAW_origin_grid=", "source_end", "last_end",
        "NO_SOURCE_AUTHORIZATION",
        "BPU1_BPU2_TVX_UNVERIFIED_NO_ORDERS",
    ):
        assert marker in s,marker
    for banned in ("resample(", "fillna(", "ffill(", "TradeBar(",
                   "market_order(", "limit_order(", "set_holdings(",
                   "stop_market_order(", "self.liquidate(",
                   "self.buy(", "self.sell(", "Resolution.SECOND",
                   "Resolution.TICK"):
        assert banned not in s,banned
    assert "TradeBarConsolidator" not in (ROOT/"strategy"/"patterns_bsu.py").read_text(encoding="utf8")
