"""Pure regression tests for native gap audit; no Cloud-data claims."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "cohort_native_acceptance_audit",
    ROOT / "research/cohort_cloud/native_acceptance_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
ET = ZoneInfo("America/New_York")


def native_day(missing=(), fill_forward=()):
    start = datetime(2024, 6, 3, 9, 30, tzinfo=ET)
    bars = []
    for i in range(390):
        t = start + timedelta(minutes=i)
        if t.strftime("%H:%M") in missing:
            continue
        bars.append(SimpleNamespace(
            time=t, end_time=t+timedelta(minutes=1),
            volume=100, is_fill_forward=t.strftime("%H:%M") in fill_forward))
    return start, start+timedelta(minutes=390), bars


def test_complete_native_day_has_78_valid_m5_buckets():
    start, end, bars = native_day()
    result = audit.native_minute_coverage(bars, start, end)
    assert result["status"] == "PASS"
    assert result["expected_m1"] == result["observed_valid_m1"] == 390
    assert result["expected_complete_m5"] == 78
    assert result["m5_buckets_with_missing_m1"] == []


def test_srpt_1308_gap_invalidates_only_1310_m5_bucket():
    start, end, bars = native_day(missing={"13:08"})
    result = audit.native_minute_coverage(bars, start, end)
    assert result["status"] == "INCOMPLETE"
    assert result["observed_valid_m1"] == 389
    assert result["missing_m1"] == ["13:08"]
    assert result["m5_buckets_with_missing_m1"] == ["13:10"]
    assert result["expected_complete_m5"] == 78


def test_fill_forward_cannot_repair_missing_minute():
    start, end, bars = native_day(fill_forward={"13:08"})
    result = audit.native_minute_coverage(bars, start, end)
    assert result["missing_m1"] == ["13:08"]
    assert result["m5_buckets_with_missing_m1"] == ["13:10"]
    assert result["invalid_source_rows"] == 1


def test_duplicate_minute_is_rejected():
    start, end, bars = native_day()
    bars.append(bars[0])
    result = audit.native_minute_coverage(bars, start, end)
    assert result["status"] == "INCOMPLETE"
    assert "DUPLICATE_NATIVE_M1" in result["source_errors"]


def test_invalid_session_rejected():
    start, end, bars = native_day()
    with pytest.raises(ValueError, match="INVALID_NATIVE_SESSION_WINDOW"):
        audit.native_minute_coverage(bars, end, start)


def test_retrospective_bpu_never_certifies_tvx_or_gates():
    result = audit.cohort_acceptance_status(
        strict_bpu1=True, strict_bpu2=True)
    assert result["bpu2"] == "OBSERVED_PROXY"
    assert result["tvx_30s"] == "UNKNOWN"
    assert result["accepted_setup"] == "UNKNOWN"
    assert result["features_14"] == "UNKNOWN"
    assert result["gates_8"] == "UNKNOWN"
    assert result["orders"] == "DISABLED"
    with pytest.raises(ValueError, match="BPU2_WITHOUT_STRICT_BPU1"):
        audit.cohort_acceptance_status(strict_bpu1=False, strict_bpu2=True)
