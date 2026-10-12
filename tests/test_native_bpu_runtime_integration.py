"""Invoke the SAME extracted M5 callback used by LEAN with controlled bars.

These are synthetic bars, not retrieved historical NVDA. Proves that the
adapter measures every closed bar, matches the research BPU detector
state, and never invents a valid BPU1 when price misses its pivot.
"""
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pandas as pd

from strategy.config import StrategyConfig
from strategy.m5_runtime import process_m5
from strategy.patterns_bsu import BsuDetector
from strategy.research_trace import BpuTouchAudit


ET = ZoneInfo("America/New_York")


class AlgorithmHarness:
    def __init__(self):
        self._signals_open = True
        self._session_date = datetime(2024, 1, 2).date()
        self.screen_watchlist = ("NVDA",)
        self._m5_bars_seen = 0
        self._m5_input_rejections = Counter()
        self._chart_symbol = "TSLA"
        self._focus_m5_plotted = 0
        self._bpu_invalid_reasons = Counter()
        self._bsu_bpu1_count = 0
        self._bsu_proxy_bpu2_count = 0
        self.records = []
        detector = BsuDetector(
            StrategyConfig(), 50.266, "short", atr_value=1.20,
            tick_size=.01,
            bsu_ts=datetime(2023, 8, 24, 16, tzinfo=ET))
        self._symbols = {"NVDA": {
            "m5_rows": [], "bsu_link": SimpleNamespace(
                detector=detector, provenance="D1_TEST_SWING_PROXY",
                origin_time=datetime(2023, 8, 24, 16, tzinfo=ET)),
            "touch_audit": BpuTouchAudit("short", 50.266, .01),
            "decision": None, "setup_trace": None,
            "focus_level": None, "qualified_today": False}}
    def _record(self, symbol, event, **kwargs):
        self.records.append((symbol, event, kwargs))


def test_extracted_m5_callback_audits_all_76_candles_without_false_bpu():
    a = AlgorithmHarness()
    first = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    for n in range(76):
        time = first + timedelta(minutes=5*n)
        high = 49.0 + n*.01
        bar = SimpleNamespace(
            symbol="NVDA", end_time=time,
            time=time-timedelta(minutes=5), period=timedelta(minutes=5),
            open=48.9, high=high, low=48.70,
            close=48.9, volume=500)
        process_m5(a, bar, pd.Timestamp)
    audit = a._symbols["NVDA"]["touch_audit"].as_dict()
    assert audit["bars"] == 76
    assert audit["touches"] == 0
    assert audit["nearest_time"].startswith("2024-01-02T15:50")
    assert a._m5_bars_seen == 76
    assert a._bsu_bpu1_count == 0
    assert not a.records
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "watch_bpu1"


def test_real_callback_and_audit_both_find_same_exact_pivot_touch():
    a = AlgorithmHarness()
    time = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    bar = SimpleNamespace(
        symbol="NVDA", end_time=time,
        time=time-timedelta(minutes=5), period=timedelta(minutes=5),
        open=50.0, high=50.27, low=49.9,
        close=50.08, volume=500)
    process_m5(a, bar, pd.Timestamp)
    assert a._symbols["NVDA"]["touch_audit"].touches == 1
    assert a._bsu_bpu1_count == 1
    assert len(a.records) == 1
    assert a.records[0][1] == "BSU_PROXY_BPU1"


def test_zero_volume_native_m5_cannot_create_bpu1_research_evidence():
    a = AlgorithmHarness()
    at = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    bar = SimpleNamespace(
        symbol="NVDA", end_time=at,
        time=at-timedelta(minutes=5), period=timedelta(minutes=5),
        open=50., high=50.27, low=49.9,
        close=50.08, volume=0)
    process_m5(a, bar, pd.Timestamp)
    assert a._m5_bars_seen == 0
    assert a._m5_input_rejections["M5_NO_OBSERVED_TRADES"] == 1
    assert a._symbols["NVDA"]["touch_audit"].touches == 0
    assert a._bsu_bpu1_count == 0
    assert not a.records


def test_missing_traded_intermediate_m5_invalidates_immediate_bpu2():
    a = AlgorithmHarness()
    t = datetime(2024, 1, 2, 9, 35, tzinfo=ET)

    def deliver(end, volume):
        process_m5(a, SimpleNamespace(
            symbol="NVDA", end_time=end,
            time=end-timedelta(minutes=5), period=timedelta(minutes=5),
            open=50.0, high=50.27,
            low=49.9, close=50.08, volume=volume), pd.Timestamp)

    deliver(t, 500)  # True BPU1 native traded candle
    assert a._bsu_bpu1_count == 1
    deliver(t + timedelta(minutes=5), 0)  # No evidence of next trade bar
    assert a._m5_input_rejections["M5_NO_OBSERVED_TRADES"] == 1
    deliver(t + timedelta(minutes=10), 500)
    assert a._bsu_proxy_bpu2_count == 0
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "invalidated"
    assert a._bpu_invalid_reasons["BPU2 not the immediate next completed candle"] == 1


def test_duplicate_native_m5_bar_cannot_count_two_bpu1_events():
    a = AlgorithmHarness()
    now = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    candle = SimpleNamespace(
        symbol="NVDA", end_time=now,
        time=now-timedelta(minutes=5), period=timedelta(minutes=5),
        open=50., high=50.27,
        low=49.9, close=50.08, volume=500)
    process_m5(a, candle, pd.Timestamp)
    process_m5(a, candle, pd.Timestamp)
    assert a._m5_bars_seen == 1
    assert a._m5_input_rejections["M5_DUPLICATE_OR_OUT_OF_ORDER"] == 1
    assert a._symbols["NVDA"]["touch_audit"].touches == 1
    assert a._bsu_bpu1_count == 1
    assert [row[1] for row in a.records] == ["BSU_PROXY_BPU1"]


def test_late_older_m5_bar_cannot_rewrite_bsu_trajectory():
    a = AlgorithmHarness()
    now = datetime(2024, 1, 2, 9, 40, tzinfo=ET)
    newest = SimpleNamespace(
        symbol="NVDA", end_time=now,
        time=now-timedelta(minutes=5), period=timedelta(minutes=5),
        open=49., high=49.5,
        low=48.7, close=49., volume=400)
    older = SimpleNamespace(
        symbol="NVDA", end_time=now - timedelta(minutes=5),
        time=now-timedelta(minutes=10), period=timedelta(minutes=5),
        open=50., high=50.27, low=49.9, close=50.08, volume=500)
    process_m5(a, newest, pd.Timestamp)
    process_m5(a, older, pd.Timestamp)
    assert a._m5_bars_seen == 1
    assert a._m5_input_rejections["M5_DUPLICATE_OR_OUT_OF_ORDER"] == 1
    assert a._bsu_bpu1_count == 0
    assert not a.records


def test_native_m1_bar_ending_at_0935_does_not_pass_as_m5_bpu_touch():
    a = AlgorithmHarness()
    end = datetime(2024, 1, 2, 9, 35, tzinfo=ET)
    wrong_period = SimpleNamespace(
        symbol="NVDA", end_time=end, time=end-timedelta(minutes=1),
        period=timedelta(minutes=1), open=50., high=50.27,
        low=49.9, close=50.08, volume=500)
    process_m5(a, wrong_period, pd.Timestamp)
    assert a._m5_input_rejections["M5_SOURCE_PERIOD_NOT_FIVE_MINUTES"] == 1
    assert a._m5_bars_seen == 0
    assert a._symbols["NVDA"]["touch_audit"].touches == 0
    assert a._bsu_bpu1_count == 0
    assert not a.records
