"""QWCT 2.8 BSU provenance and native completed M5 audit (NO signal promotion)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from research.cohort_cloud.bsu_touch_audit import TouchAudit, audit_report
from strategy.config import StrategyConfig
from strategy.patterns_bsu import Bar, BsuDetector


def m5(low, high, end="10:05"):
    return SimpleNamespace(low=low, high=high), datetime.strptime(
        "2024-06-24 " + end, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def audit(side="short", raw=100, cluster=99.97, tick=.01):
    return TouchAudit("CAT", "2024-06-24", "2024-03-25", side,
                      raw, cluster, tick, "REBASED")


def test_short_four_disjoint_categories_and_closest_signed_gap():
    a = audit()
    for lo, hi, expected, end in (
        (99.90, 99.98, "SHORT_OF", "09:35"),
        (99.95, 100.00, "EXACT_WICK", "09:40"),
        (99.95, 100.03, "RANGE_CROSSED", "09:45"),
        (100.05, 100.12, "GAP_BEYOND", "09:50"),
    ):
        bar, at = m5(lo, hi, end)
        assert a.observe(bar, at) == expected
    assert a.counts["BARS"] == 4
    assert [a.counts[k] for k in (
        "SHORT_OF", "EXACT_WICK", "RANGE_CROSSED", "GAP_BEYOND")] == [1, 1, 1, 1]
    assert a.first_cross_at == "09:45"
    assert a.nearest == 0 and a.nearest_signed == 0
    assert a.at == "09:40"
    assert a.counts["CLUSTER_RANGE"] >= 1
    assert a.raw_cluster_diff_ticks == pytest.approx(-3.0)
    assert a.cluster_grid


def test_long_support_classification_is_direction_correct():
    a = audit(side="long", cluster=100.03)
    for low, high, expected in (
        (100.02, 100.12, "SHORT_OF"),
        (100.00, 100.07, "EXACT_WICK"),
        (99.97, 100.04, "RANGE_CROSSED"),
        (99.88, 99.95, "GAP_BEYOND"),
    ):
        bar, at = m5(low, high)
        assert a.observe(bar, at) == expected
    assert sum(a.counts[k] for k in (
        "SHORT_OF", "EXACT_WICK", "RANGE_CROSSED", "GAP_BEYOND")) == 4


def test_half_tick_precision_matches_existing_detector_not_two_tick_nearmiss():
    a = audit(cluster=100.005)
    assert not a.cluster_grid
    for high, cat in (
        (99.98, "SHORT_OF"),        # two-tick misses remain short
        (100.004, "EXACT_WICK"),   # within half native tick
        (100.006, "RANGE_CROSSED"),
    ):
        b, at = m5(99.92, high)
        assert a.observe(b, at) == cat

    cfg = StrategyConfig()
    detector = BsuDetector(
        cfg, 100, "short", atr_value=2.0, tick_size=.01,
        bsu_ts=datetime(2024, 3, 25, tzinfo=timezone.utc))
    candidate = Bar(
        ts=datetime(2024, 6, 24, 10, 5, tzinfo=timezone.utc),
        open=99.98, high=100.03, low=99.94, close=99.96,
        volume=1000, timeframe="M5")
    state = detector.on_bar(candidate)
    assert state.phase == "watch_bpu1"  # OHLC cross does not promote BPU1
    assert not state.can_submit


def test_cluster_cross_is_distinct_from_raw_source_touch():
    a = audit(cluster=99.97)
    bar, at = m5(99.96, 99.98)
    assert a.observe(bar, at) == "SHORT_OF"
    assert a.counts["CLUSTER_RANGE"] == 1
    assert a.counts["EXACT_WICK"] == 0
    assert a.first_cluster_at == "10:05"
    assert a.first_cross_at is None


def test_aggregate_counts_only_observed_original_cases_not_trades():
    a = audit()
    b = audit(side="long", raw=150, cluster=149.985)
    assert not b.cluster_grid
    assert a.observe(*m5(99.95, 100.02)) == "RANGE_CROSSED"
    assert b.observe(*m5(150.04, 150.10)) == "SHORT_OF"
    rows = [{"audit": a}, {"audit": b}, {"audit": audit(raw=200, cluster=200.01)}]
    lines = audit_report(rows, limit=2)
    assert len(lines) == 3
    assert "proxies=3 observed=2 case_bars=2" in lines[0]
    assert "raw_exact=0" in lines[0]
    assert "crossed_cases=1" in lines[0]
    assert "NOT BPU1 / NOT TVX / NO ORDERS" in lines[0]
    assert "src=2024-03-25" in lines[1]
    assert "cross=1" in lines[1]
    assert "NO ORDERS" in lines[2]
    assert not any("CONFIRMED" in line for line in lines)


def test_invalid_data_fail_closed():
    for side in ("buy", "", None):
        with pytest.raises(ValueError):
            audit(side=side)
    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            audit(raw=value)
    a = audit()
    for low, high in ((0, 10), (105, 100), (float("nan"), 101)):
        with pytest.raises(ValueError):
            a.observe(*m5(low, high))
    assert not a.counts
