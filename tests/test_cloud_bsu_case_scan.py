"""Native Cloud BPU case-search regressions: no synthetic signals or orders."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from strategy.research_trace import BpuTouchAudit
from tools.package_quantconnect_free import build_sources

ROOT = Path(__file__).resolve().parents[1]


def test_exact_native_m5_touch_is_not_a_crossing_or_nearby_miss():
    audit = BpuTouchAudit("short", 502.66, .01)
    now = datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York"))
    audit.observe(now, low=488., high=493., close=490.)
    assert audit.touches == 0 and abs(audit.closest_gap + 9.66) < 1e-8
    audit.observe(now + timedelta(minutes=5), low=500., high=502.67, close=502.)
    assert audit.touches == 0 and audit.overshoots == 1
    audit.observe(now + timedelta(minutes=10), low=501., high=502.66, close=502.)
    assert audit.touches == 1 and audit.closest_gap == 0
    assert audit.bars == 3


def test_asof_cloud_scan_is_enabled_by_default_with_new_historical_window():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'self.get_parameter("scan_start") or "2024-02-06"' in main
    assert 'self.get_parameter("scan_end") or "2024-03-15"' in main
    assert '(end - start).days > 45' in main
    assert "self._case_scan = True" in main
    assert "QWCT SCAN ACTIVE" in main
    assert "self._bsu_scan_best = []" in main
    assert "self._native_exit_enabled = False" in main
    assert not any(token in main for token in
                   ("self.market_order(", "self.limit_order(", "self.bracket_order("))


def test_bpu_scan_ranks_only_observed_closed_m5_native_touch_audit():
    cloud = build_sources(ROOT)
    assert len(cloud) == 24
    m5 = cloud["strategy/m5_runtime.py"]
    report = cloud["strategy/reporting.py"]
    assert 'if getattr(self, "_case_scan", False):' in m5
    assert m5.index('audit.observe(') < m5.index('case = (abs(audit.closest_gap)')
    assert 'self._bsu_scan_best = self._bsu_scan_best[:5]' in m5
    assert 'if not self._object_store_export_enabled:' in report
    assert "QWCT SCAN NEAREST" in report
    assert "QWCT SCAN EVENT" in report
    assert "BSU_PROXY_BPU2_CLOSED" in report
    assert 'self._bsu_bpu1_count' in report
    assert 'self._bsu_proxy_bpu2_count' in report
    assert 'NO ORDERS' in report


def test_existing_cloud_package_keeps_native_history_and_import_path():
    cloud = build_sources(ROOT)
    assert len(cloud["main.py"]) < 28_000
    assert "from strategy import choose_focus" in cloud["main.py"]
    assert "from strategy.reporting import write_reports" in cloud["main.py"]
    assert "resolve_raw_bsu_evidence(" in cloud["main.py"]
    assert "raw_evidence=raw_evidence, require_raw=True" in cloud["main.py"]
