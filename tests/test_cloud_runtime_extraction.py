"""Pure smoke tests for Cloud editor module split (not a LEAN backtest)."""
from collections import Counter
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.m5_runtime import process_m5
from strategy.runtime_reporting import write_reports


class QuietResearchAlgorithm:
    def __init__(self):
        self._signals_open = True
        self._session_date = datetime(2024, 1, 3).date()
        self.screen_watchlist = ("TSLA",)
        self._symbols = {"TSLA": {"m5_rows": [], "decision": None,
                                  "bsu_link": None, "focus_level": None,
                                  "qualified_today": False}}
        self._m5_bars_seen = 0
        self._chart_symbol = "NVDA"
        self._focus_m5_plotted = 0


def test_real_m5_bar_handler_extract_uses_completed_ohlc_no_orders():
    algorithm = QuietResearchAlgorithm()
    time = datetime(2024, 1, 3, 10, 35, tzinfo=ZoneInfo("America/New_York"))
    bar = SimpleNamespace(symbol="TSLA", end_time=time,
                          open=100.0, high=101.2, low=99.5,
                          close=100.5, volume=1200)
    process_m5(algorithm, bar, pd.Timestamp)
    assert algorithm._m5_bars_seen == 1
    assert algorithm._symbols["TSLA"]["m5_rows"][0]["close"] == 100.5
    assert algorithm._symbols["TSLA"]["m5_rows"][0]["date"] == pd.Timestamp(time)
    assert algorithm._focus_m5_plotted == 0


def test_actual_runtime_reporting_function_emits_empty_research_statistics():
    class Alg:
        def __init__(self):
            self._signal_rows = []
            self._order_event_rows = []
            self._d1_models = Counter()
            self._bsu_block_reasons = Counter()
            self._bpu_invalid_reasons = Counter()
            self._gate_failures = Counter()
            self._m5_true_by_model = Counter()
            self._m5_true_other_blockers = Counter()
            self._chart_symbol = None
            self._focus_m5_plotted = 0
            self._bsu_bpu1_count = 0
            self._bsu_proxy_armed_count = 0
            self._bsu_proxy_bpu2_count = 0
            self._m5_bars_seen = 0
            self._m5_checks = 0
            self._intent_missing_atr = 0
            self._setup_traces = []
            self._setup_traces_omitted = 0
            self._object_store_export_enabled = False
            self.stats = {}
            self.logs = []
        def set_runtime_statistic(self, k, v):
            self.stats[k] = v
        def log(self, s):
            self.logs.append(s)

    algorithm = Alg()
    write_reports(algorithm)
    assert algorithm.stats["Qwct D1 setups"] == 0
    assert algorithm.stats["Qwct M5 checks"] == 0
    assert algorithm.stats["Qwct traced D1 setups"] == 0
    assert any("ObjectStore DISABLED" in s for s in algorithm.logs)
