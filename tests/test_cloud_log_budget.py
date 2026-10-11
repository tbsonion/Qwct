"""Cloud Free diagnostics must survive QuantConnect's 10 KB log quota."""
from collections import Counter
from types import SimpleNamespace

from strategy.runtime_reporting import write_reports


class FakeTrace:
    def __init__(self, i):
        self.m5_checks = 2
        self.symbol = f"T{i}"
    def display_lines(self):
        return [
            f"QWCT D1 {self.symbol} accepted",
            f"QWCT M5 {self.symbol} check",
            f"QWCT GATES {self.symbol} risk_approved:UNKNOWN",
            f"QWCT BSU {self.symbol} blocked:origin inconsistent",
        ]


class FakeAlgorithm:
    def __init__(self, n):
        self._signal_rows = [{"type": "SCENARIO"} for _ in range(n)]
        self._d1_models = Counter({"bounce": n})
        self._bsu_block_reasons = Counter({"origin mismatch": n})
        self._bpu_invalid_reasons = Counter()
        self._gate_failures = Counter({"risk_approved": n})
        self._m5_true_by_model = Counter()
        self._m5_true_other_blockers = Counter()
        self._bsu_bpu1_count = 0
        self._bsu_proxy_armed_count = 0
        self._bsu_proxy_bpu2_count = 0
        self._chart_symbol = SimpleNamespace(value="TSLA")
        self._focus_m5_plotted = 100
        self._m5_bars_seen = 200
        self._m5_checks = n * 2
        self._intent_missing_atr = 0
        self._setup_traces = [FakeTrace(i) for i in range(n)]
        self._setup_traces_omitted = 0
        self._object_store_export_enabled = False
        self.stats = {}
        self.lines = []
    def set_runtime_statistic(self, name, value):
        self.stats[name] = value
    def log(self, value):
        self.lines.append(value)


def test_end_summary_is_first_and_six_morning_setups_are_all_visible():
    a = FakeAlgorithm(6)
    write_reports(a)
    assert a.lines[0].startswith("Qwct research summary:")
    assert sum(line.startswith("QWCT BSU ") for line in a.lines) == 6
    assert a.stats["Qwct top BSU blocker"] == "origin mismatch (6)"


def test_very_long_runs_keep_trace_logging_bounded_below_10kb():
    a = FakeAlgorithm(40)
    write_reports(a)
    assert sum(line.startswith("QWCT BSU ") for line in a.lines) <= 8
    assert any("viewer limit" in line for line in a.lines)
    assert len("\n".join(a.lines)) < 7000


def test_daily_screener_logs_are_not_repeated_full_universe_lists():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert 'self._screen_logged = False' in source
    assert 'if not self._screen_logged:' in source
    assert 'self._screen_logged = True' in source
    assert 'self.debug(f"SCREEN {self.time.date()}: "' not in source


def test_rejected_bounce_logs_exact_cause_early_with_a_small_cap():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert 'self._bsu_blocks_logged = 0' in source
    assert 'if self._bsu_blocks_logged < 6:' in source
    assert '"QWCT BSU BLOCKED' in source
