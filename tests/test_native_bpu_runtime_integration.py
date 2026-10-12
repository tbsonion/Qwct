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
        open=50.0, high=50.27, low=49.9,
        close=50.08, volume=500)
    process_m5(a, bar, pd.Timestamp)
    assert a._symbols["NVDA"]["touch_audit"].touches == 1
    assert a._bsu_bpu1_count == 1
    assert len(a.records) == 1
    assert a.records[0][1] == "BSU_PROXY_BPU1"
