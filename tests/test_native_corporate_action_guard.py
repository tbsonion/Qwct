"""US-equity native SplitOccurred event must invalidate and rewarm research.

Tests exercise pure extracted handlers. Real LEAN PythonNet SplitType
and history/re-subscribing behavior still need a native Cloud smoke.
"""
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from strategy.corporate_action_guard import (
    process_native_split_events, rewarm_split_symbols,
    split_research_blocked)

ET = ZoneInfo("America/New_York")
TODAY = date(2024, 6, 10)


class MockNativeSubscriptions:
    def __init__(self):
        self.removed = []

    def remove_consolidator(self, symbol, consol):
        self.removed.append((symbol, consol))


class NativeHarness:
    def __init__(self):
        self.time = datetime(2024, 6, 10, 0, 0, tzinfo=ET)
        self._symbols = {"SPLIT": {
            "daily_consolidator": "D1_OLD",
            "m5_consolidator": "M5_OLD",
            "split_blocked_date": None,
            "split_rewarm_pending": False,
            "bsu_link": object(), "tvx_sec_window": object(),
            "bsu_tvx_evidence": object(), "preclose_review": object(),
            "breakout_retest": object(), "decision": object(),
            "qualified_today": True}}
        self.subscription_manager = MockNativeSubscriptions()
        self.events = []
        self.history_warm_count = 0

    def _record(self, sym, kind, **kwargs):
        self.events.append((sym, kind, kwargs))

    def _register_symbol(self, symbol):
        assert symbol not in self._symbols
        self._symbols[symbol] = {
            "daily_consolidator": "D1_NEW",
            "m5_consolidator": "M5_NEW",
            "bsu_link": None, "tvx_sec_window": None,
            "decision": None, "split_rewarm_pending": False}
        return True

    def _warm_symbols(self, symbols):
        assert symbols == ["SPLIT"]
        self.history_warm_count += 1


def native_slice(kind):
    return SimpleNamespace(splits={"SPLIT": SimpleNamespace(type=kind)})


def test_warning_not_real_split_does_not_invalidate_bpu():
    a = NativeHarness()
    process_native_split_events(a, native_slice("warning"), "occurred")
    assert a._symbols["SPLIT"]["bsu_link"] is not None
    assert not split_research_blocked(a._symbols["SPLIT"], TODAY)
    assert not a.events


def test_real_split_invalidates_previous_native_m5_sec_and_preclose_risk():
    a = NativeHarness()
    process_native_split_events(a, native_slice("occurred"), "occurred")
    old = a._symbols["SPLIT"]
    assert split_research_blocked(old, TODAY)
    assert old["split_rewarm_pending"]
    for key in ("bsu_link", "tvx_sec_window", "bsu_tvx_evidence",
                "preclose_review", "breakout_retest", "decision"):
        assert old[key] is None
    assert not old["qualified_today"]
    assert a.events[0][1] == "SPLIT_RESEARCH_BLOCKED"
    process_native_split_events(a, native_slice("occurred"), "occurred")
    assert len(a.events) == 1


def test_split_rewarm_uses_native_lean_consolidator_removal_and_typed_history():
    a = NativeHarness()
    process_native_split_events(a, native_slice("occurred"), "occurred")
    a.time = a.time.replace(hour=9, minute=29)
    rewarm_split_symbols(a)
    assert a.subscription_manager.removed == [
        ("SPLIT", "D1_OLD"), ("SPLIT", "M5_OLD")]
    assert a.history_warm_count == 1
    assert a._symbols["SPLIT"]["daily_consolidator"] == "D1_NEW"
    assert a._symbols["SPLIT"]["split_blocked_date"] == TODAY
    assert not a._symbols["SPLIT"]["split_rewarm_pending"]
    assert split_research_blocked(a._symbols["SPLIT"], TODAY)
    assert not split_research_blocked(
        a._symbols["SPLIT"], date(2024, 6, 11))
    assert a.events[-1][1] == "SPLIT_REWARMED_BLOCKED"


def test_native_source_wires_split_handler_before_sec_and_blocks_m5():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    main = (root/"main.py").read_text()
    m5 = (root/"strategy/m5_runtime.py").read_text()
    sec = (root/"strategy/second_runtime.py").read_text()
    assert "process_native_split_events(self, data, SplitType.SPLIT_OCCURRED)" in main
    assert main.index("process_native_split_events(self, data") < main.index(
        "process_second_slice(self, data")
    assert "rewarm_split_symbols(self)" in main
    assert "split_research_blocked(state, self._session_date)" in main
    assert "split_research_blocked(state, self._session_date)" in m5
    assert "split_research_blocked(state, self._session_date)" in sec
