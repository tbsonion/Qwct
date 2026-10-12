"""The actual extracted native M5 callback drives the breakout setup stages.

Deterministic synthetic shape-only fixtures, not a LEAN or broker test.
"""
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.breakout_retest import BreakoutRetestObserver
from strategy.config import StrategyConfig
from strategy.m5_runtime import process_m5

ET = ZoneInfo("America/New_York")
START = datetime(2024, 1, 2, 10, 30, tzinfo=ET)


class Algorithm:
    def __init__(self, side="long"):
        self._signals_open = True
        self._session_date = START.date()
        self.screen_watchlist = ("NVDA",)
        self._m5_bars_seen = 0
        self._m5_input_rejections = Counter()
        self._breakout_retest_counts = Counter()
        self._chart_symbol = "TSLA"
        self._focus_m5_plotted = 0
        self.records = []
        self.cfg = StrategyConfig()
        self._symbols = {"NVDA": {
            "decision": None, "qualified_today": False,
            "bsu_link": None, "setup_trace": None, "focus_level": None,
            "m5_rows": [],
            "breakout_retest": BreakoutRetestObserver(
                symbol="NVDA", session=START.date(), side=side,
                level_price=100., atr_value=2.,
                max_confirm_chase_atr=self.cfg.max_entry_distance_atr)
        }}

    def _record(self, symbol, event, **kwargs):
        self.records.append((symbol, event, kwargs))

    def error(self, message):
        raise AssertionError(message)


def bar(minute, open_, high, low, close, volume=500, period=5):
    end = START + timedelta(minutes=minute)
    return SimpleNamespace(
        symbol="NVDA", time=end - timedelta(minutes=period),
        end_time=end, period=timedelta(minutes=period),
        open=open_, high=high, low=low, close=close,
        volume=volume, is_fill_forward=False)


def run_all(a, rows):
    for row in rows:
        process_m5(a, bar(*row), pd.Timestamp)


LONG = [
    (0, 99.8, 99.9, 99.6, 99.8),
    (5, 99.8, 100.4, 99.7, 100.2),
    (10, 100.2, 100.3, 99.9, 100.08),
    (15, 100.08, 100.5, 100.01, 100.42),
]
SHORT = [
    (0, 100.2, 100.3, 100.1, 100.2),
    (5, 100.2, 100.3, 99.6, 99.8),
    (10, 99.8, 100.1, 99.7, 99.92),
    (15, 99.92, 100.02, 99.5, 99.55),
]


def test_native_callback_proves_three_stages_for_long_without_orders():
    a = Algorithm()
    run_all(a, LONG[:2])
    assert a._symbols["NVDA"]["breakout_retest"].phase == "WAIT_RETEST"
    assert a._breakout_retest_counts["CONFIRMED"] == 0
    run_all(a, LONG[2:3])
    assert a._symbols["NVDA"]["breakout_retest"].phase == "WAIT_CONFIRMATION"
    assert a._breakout_retest_counts["CONFIRMED"] == 0
    run_all(a, LONG[3:])
    result = a._symbols["NVDA"]["breakout_retest"].evidence
    assert result.phase == "CONFIRMED"
    assert result.breakout_at < result.retest_at < result.confirmed_at
    assert result.can_submit is False
    assert a._breakout_retest_counts == Counter({
        "WAIT_RETEST": 1, "WAIT_CONFIRMATION": 1, "CONFIRMED": 1})
    assert [event for _, event, _ in a.records] == ["BREAKOUT_STAGE"] * 3
    assert all("NO ORDERS" in d["reason"] for _, _, d in a.records)


def test_native_callback_is_symmetrical_for_short_breakout():
    a = Algorithm(side="short")
    run_all(a, SHORT)
    assert a._symbols["NVDA"]["breakout_retest"].evidence.phase == "CONFIRMED"
    assert a._breakout_retest_counts["CONFIRMED"] == 1


def test_native_invalid_m5_intermediate_cannot_be_silently_skipped():
    a = Algorithm()
    run_all(a, LONG[:2])
    bad = bar(10, 100.2, 100.3, 99.9, 100.08, volume=0)
    process_m5(a, bad, pd.Timestamp)
    assert a._m5_input_rejections["M5_NO_OBSERVED_TRADES"] == 1
    process_m5(a, bar(*LONG[3]), pd.Timestamp)
    assert a._symbols["NVDA"]["breakout_retest"].evidence.phase == "INVALIDATED"
    assert a._breakout_retest_counts["CONFIRMED"] == 0
    assert a._breakout_retest_counts["INVALIDATED"] == 1


def test_native_duplicate_does_not_repeat_confirmed_event():
    a = Algorithm()
    run_all(a, LONG)
    process_m5(a, bar(*LONG[-1]), pd.Timestamp)
    assert a._breakout_retest_counts["CONFIRMED"] == 1
    assert a._m5_input_rejections["M5_DUPLICATE_OR_OUT_OF_ORDER"] == 1
    assert len(a.records) == 3


def test_native_m1_cannot_arm_breakout_state():
    a = Algorithm()
    process_m5(a, bar(*LONG[0]), pd.Timestamp)
    process_m5(a, bar(*LONG[1], period=1), pd.Timestamp)
    assert a._symbols["NVDA"]["breakout_retest"].evidence.phase == "WATCH_BREAKOUT"
    assert a._breakout_retest_counts["WAIT_RETEST"] == 0
    assert a._m5_input_rejections["M5_SOURCE_PERIOD_NOT_FIVE_MINUTES"] == 1
