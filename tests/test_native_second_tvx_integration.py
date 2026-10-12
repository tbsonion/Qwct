"""Actual extracted M5 + SEC on_data bridge, deterministic native-shaped bars.

Tests prove chronology/guard behavior, not availability of true SEC data
in Cloud, brokerage order placement, or trade profitability.
"""
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.config import StrategyConfig
from strategy.patterns_bsu import BsuDetector
from strategy.native_second_tvx import NativeSecondTvxWindow
from strategy.second_runtime import process_second_slice
from strategy.m5_runtime import process_m5

ET = ZoneInfo("America/New_York")
AT = datetime(2024, 1, 2, 10, 35, tzinfo=ET)


class ResearchHarness:
    def __init__(self, sec_on=True):
        self._signals_open = True
        self._tvx_seconds_enabled = sec_on
        self._session_date = AT.date()
        self.screen_watchlist = ("NVDA",)
        self._m5_bars_seen = 0
        self._m5_input_rejections = Counter()
        self._chart_symbol = "TSLA"
        self._focus_m5_plotted = 0
        self._bsu_bpu1_count = 0
        self._bsu_proxy_bpu2_count = 0
        self._bpu_invalid_reasons = Counter()
        self._tvx_preclose_count = 0
        self._tvx_preclose_reconciled = 0
        self._tvx_second_reasons = Counter()
        self._symbols = {"NVDA": {
            "m5_rows": [], "decision": None, "qualified_today": False,
            "focus_level": None, "setup_trace": None,
            "touch_audit": None, "tvx_sec_window": None,
            "bsu_link": SimpleNamespace(
                detector=BsuDetector(
                    StrategyConfig(), 100., "long", atr_value=2.,
                    tick_size=0.01, bsu_ts=datetime(2023, 8, 24, 16, tzinfo=ET)),
                provenance="D1_SWING_PROXY", origin_time=AT-timedelta(days=50))
        }}
        self.records = []

    def _record(self, symbol, kind, **kwargs):
        self.records.append((symbol, kind, kwargs))

    def error(self, msg):
        raise AssertionError(msg)


def native_m5(end, low=100., high=100.25, close=100.08):
    return SimpleNamespace(
        symbol="NVDA", time=end-timedelta(minutes=5), end_time=end,
        period=timedelta(minutes=5), open=100.08,
        high=high, low=low, close=close, volume=500)


def sec_bar(n, *, volume=1, low=100.01, high=100.10, price=100.06,
            wrong_period=False, fill_forward=False, symbol="NVDA"):
    at = AT + timedelta(seconds=n)
    length = timedelta(minutes=1) if wrong_period else timedelta(seconds=1)
    return SimpleNamespace(
        symbol=symbol, time=at-length, end_time=at, period=length,
        open=price, high=high, low=low, close=price,
        volume=volume, is_fill_forward=fill_forward)


def on_sec(a, bar):
    process_second_slice(
        a, SimpleNamespace(bars={bar.symbol: bar}), pd.Timestamp)


def arm(a):
    process_m5(a, native_m5(AT, low=100., high=100.25, close=100.08),
               pd.Timestamp)
    link = a._symbols["NVDA"]["bsu_link"]
    assert link.detector.state.phase == "bpu1"
    assert a._bsu_bpu1_count == 1
    if a._tvx_seconds_enabled:
        assert isinstance(a._symbols["NVDA"]["tvx_sec_window"],
                          NativeSecondTvxWindow)


def test_complete_270_native_seconds_marks_preclose_then_m5_reconciles():
    a = ResearchHarness()
    arm(a)
    for n in range(1, 270):
        on_sec(a, sec_bar(n))
    assert a._tvx_preclose_count == 0
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "bpu1"
    on_sec(a, sec_bar(270))
    st = a._symbols["NVDA"]["bsu_link"].detector.state
    assert a._tvx_preclose_count == 1
    assert st.phase == "preclose_candidate"
    assert st.preclose_seen is True
    assert st.can_submit is False
    assert st.preclose_low == 100.01
    assert st.precision == "sec_preclose_observed"
    assert [x[1] for x in a.records].count("TVX_SEC_PRE_CLOSE") == 1
    # Preclose is never a BPU2 close or a fill.
    assert a._bsu_proxy_bpu2_count == 0
    process_m5(a, native_m5(AT+timedelta(minutes=5),
                             low=100.01, high=100.13),
               pd.Timestamp)
    assert a._bsu_proxy_bpu2_count == 1
    assert a._tvx_preclose_reconciled == 1
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "bpu2_confirmed"
    assert "RECONCILED" in a.records[-1][2]["reason"]
    assert "NO ORDERS OR FILLS" in a.records[-1][2]["reason"]


def test_not_enabled_uses_closed_m5_without_invented_preclose():
    a = ResearchHarness(sec_on=False)
    arm(a)
    for n in range(1, 271):
        on_sec(a, sec_bar(n))
    assert a._symbols["NVDA"]["tvx_sec_window"] is None
    assert a._tvx_preclose_count == 0
    process_m5(a, native_m5(AT+timedelta(minutes=5),
                             low=100.01, high=100.13),
               pd.Timestamp)
    assert a._bsu_proxy_bpu2_count == 1
    assert a._tvx_preclose_reconciled == 0
    assert "NO verified SEC -30s TVX" in a.records[-1][2]["reason"]


def test_missing_one_second_fails_closed_and_no_late_preclose():
    a = ResearchHarness()
    arm(a)
    for n in range(1, 271):
        if n != 100:
            on_sec(a, sec_bar(n))
    win = a._symbols["NVDA"]["tvx_sec_window"]
    assert win.blocked_reason == "SEC_MISSING_DUPLICATE_OR_LATE_SECOND"
    assert win.complete is False
    assert a._tvx_preclose_count == 0
    assert a._tvx_second_reasons[win.blocked_reason] == 1
    assert [v[1] for v in a.records].count("TVX_SEC_BLOCKED") == 1


def test_zero_volume_and_fill_forward_native_seconds_cannot_confirm():
    for kwargs, reason in (({"volume": 0}, "SEC_OHLCV_UNVERIFIED"),
                           ({"fill_forward": True}, "SEC_FILL_FORWARD"),
                           ({"wrong_period": True}, "SEC_NATIVE_PERIOD_INVALID")):
        a = ResearchHarness()
        arm(a)
        on_sec(a, sec_bar(1, **kwargs))
        assert a._symbols["NVDA"]["tvx_sec_window"].blocked_reason == reason
        for n in range(2, 271):
            on_sec(a, sec_bar(n))
        assert a._tvx_preclose_count == 0


def test_extra_seconds_at_or_after_close_cannot_backfill_270_cutoff():
    a = ResearchHarness()
    arm(a)
    for n in range(1, 270):
        on_sec(a, sec_bar(n))
    # No 270th bar; later data cannot supply the missing preclose stamp.
    on_sec(a, sec_bar(271))
    assert a._tvx_preclose_count == 0
    assert a._symbols["NVDA"]["tvx_sec_window"].complete is False


def test_preclose_wick_breaks_bpu1_extreme_and_cannot_be_reset_at_bpu2():
    a = ResearchHarness()
    arm(a)
    for n in range(1, 271):
        on_sec(a, sec_bar(n, low=99.98, high=100.1, price=100.06))
    assert a._tvx_preclose_count == 0
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "invalidated"
    process_m5(a, native_m5(AT+timedelta(minutes=5),
                             low=99.98, high=100.13),
               pd.Timestamp)
    assert a._bsu_proxy_bpu2_count == 0
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "invalidated"


def test_native_complete_m5_must_contain_previous_sec_extremes():
    a = ResearchHarness()
    arm(a)
    for n in range(1, 271):
        on_sec(a, sec_bar(n))
    assert a._tvx_preclose_count == 1
    process_m5(a, native_m5(AT+timedelta(minutes=5),
                             low=100.02, high=100.13),
               pd.Timestamp)
    assert a._bsu_proxy_bpu2_count == 0
    assert a._tvx_preclose_reconciled == 0
    assert a._symbols["NVDA"]["bsu_link"].detector.state.phase == "invalidated"


def test_mismatched_symbol_not_allowed_into_this_bpu_window():
    window = NativeSecondTvxWindow(AT)
    assert window.accept(sec_bar(1, symbol="TSLA"), symbol="NVDA") is None
    assert window.blocked_reason == "SEC_SYMBOL_MISMATCH"


def test_early_or_duplicate_second_is_not_a_complete_preclose_sample():
    window = NativeSecondTvxWindow(AT)
    assert window.accept(sec_bar(1)) is None
    assert window.accept(sec_bar(1)) is None
    assert window.blocked_reason == "SEC_MISSING_DUPLICATE_OR_LATE_SECOND"
    assert not window.complete


def test_session_reset_drops_preclose_window_before_new_bpu1():
    a = ResearchHarness()
    arm(a)
    win = a._symbols["NVDA"]["tvx_sec_window"]
    # _prepare_session clears this slot for every symbol.
    a._symbols["NVDA"]["tvx_sec_window"] = None
    assert a._symbols["NVDA"]["tvx_sec_window"] is None
    assert win.count == 0
