"""QWCT 2.6 guards: same canonical D1 Shadow, PIT callback, native M1->M5 replay."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "research" / "cohort_cloud" / "main.py"
BASE = ROOT / "research" / "universe_cloud" / "main.py"


def function_ast(filename, name):
    mod = ast.parse(filename.read_text(encoding="utf-8"))
    return next(n for n in mod.body if isinstance(n, ast.FunctionDef)
                and n.name == name)


def test_original_shadow_d1_rules_unmodified():
    for name in (
        "d1_shadow_shortlist", "classify_snapshot",
        "origin_d1_audit", "compare_raw_scaled",
    ):
        assert ast.dump(function_ast(APP, name)) == ast.dump(
            function_ast(BASE, name)), name


def test_free_cloud_budget_no_orders_and_bounded_independent_month():
    s = APP.read_text(encoding="utf-8")
    ast.parse(s)
    assert len(s.encode("utf-8")) < 32_000
    assert 'self.get_parameter("scan_start") or "2024-06-01"' in s
    assert 'self.get_parameter("scan_end") or "2024-06-30"' in s
    assert "(end-start).days > 35" in s
    assert "Resolution.SECOND" not in s and "Resolution.TICK" not in s
    for command in (
        "self.market_order(", "self.limit_order(", "self.stop_market_order(",
        "self.set_holdings(", "self.buy(", "self.sell(", "self.liquidate(",
    ):
        assert command not in s


def test_morning_frozen_fundamental_and_shadow_and_after_close_only():
    s = APP.read_text(encoding="utf-8")
    for required in (
        "self.universe_settings.resolution = Resolution.DAILY",
        "self.add_universe(self._select)",
        "self.time_rules.before_market_open(anchor, 1)",
        "self.time_rules.after_market_close(anchor, 0)",
        "self.callback_at[day] > et(self.time)",
        "self.callback_events.append(event)",
        "freeze_fundamental_event(",
        "NO_SAME_DAY_FUNDAMENTAL_CALLBACK",
        "next_session_fundamentals(",
        "native_next_open/09:29 OK",
        "self._daily_history(\n                members, day, DataNormalizationMode.RAW)",
        "classify_snapshot(d1, self.cfg, day)",
        "shadow = d1_shadow_shortlist(passed, self.cfg.screener_watchlist_limit)",
        "origin_d1_audit(d1, level, day, self.cfg, tick)",
        "compare_raw_scaled(",
        'proof["status"] not in ("MATCH", "REBASED")',
        "f\"QWCT COHORT DAY",
    ):
        assert required in s, required
    # The only M1 history request and native M5 replay occur AFTER the
    # market close. No ticker gets a new real-time M1 subscription.
    assert "self.add_equity(\n            \"SPY\", Resolution.MINUTE" in s
    assert s.count("Resolution.MINUTE") == 2  # SPY + after-close M1 History
    assert "TradeBarConsolidator(timedelta(minutes=5))" in s
    assert "consolidator.update(bar)" in s
    assert "validate_m5_tradebar(bar, at.to_pydatetime())" in s
    assert "self._observe(case, bar, at)" in s
    assert "end = et(self.time).to_pydatetime()" in s  # early-close-aware
    assert "after_market_close(anchor, 1)" not in s  # last day skipped
    assert "self.timing_mode" in s


def test_missing_and_split_days_never_fabricate_m5():
    s = APP.read_text(encoding="utf-8")
    for required in (
        "self.by_day.get(day)",
        "NO_VERIFIED_SELECTION",
        "self.quarantined.add((sym, et(self.time).date()))",
        "SPLIT_OCCURRED_QUARANTINE",
        "if (sym, day) not in self.quarantined",
        "BAD_OR_UNORDERED_M1_",
        "EMPTY_M1_",
        "M5_OUTSIDE_REGULAR_SESSION",
        "bpu2_confirmed",
        "first_strict",
        "strict_bpu2_window",
        "TVX_UNVERIFIED NO ORDERS",
        "QWCT COHORT SUMMARY",
        "QWCT COHORT COVERAGE",
        "QWCT COHORT NEAREST",
    ):
        assert required in s, required


def test_2_6_not_modified_original_three_strategies():
    s = APP.read_text(encoding="utf-8")
    assert "from strategy.patterns_bsu import Bar as ClosedBar, BsuDetector" in s
    assert "from strategy.native_m5_validation import validate_m5_tradebar" in s
    # BsuDetector is read-only: no synthetic fill/trade intent/profit.
    assert "detector.on_bar(ClosedBar(" in s
    assert "research" not in s[:90].lower() or "QWCT" in s


def test_native_close_scan_keeps_completed_origin_candles():
    code = APP.read_text(encoding="utf-8")
    assert "def _replay(self, symbol, minute_bars, day, close):" in code
    assert "self._replay(symbol, minute[symbol], day, end)" in code
    assert "consolidator.scan(minute_bars[-1].end_time)" in code
    for phrase in (
        'tail_ok = len(minute_bars) >= 5',
        'for i, b in enumerate(minute_bars[-5:])',
        'not getattr(b, "is_fill_forward", False)',
        'and isfinite(float(b.volume)) and float(b.volume) > 0',
        'self.rejects["M1_CLOSE_FIVE_NOT_COMPLETE"]',
        'self.rejects["M5_CLOSE_UNVERIFIED_SOURCE"]',
        'self.rejects["M5_CLOSE_NOT_EMITTED"]',
        'self.summary["close_scanned"]',
    ):
        assert phrase in code
    assert "TradeBar(" not in code
    assert "best_signed" in code and "best_at" in code
    assert "signed=" in code and "closest_ticks=" in code
    assert len(code.encode("utf-8")) < 32_000


def test_2_7_next_session_has_strict_ab_mode_and_native_calendar_only():
    s = APP.read_text(encoding="utf-8")
    assert 'self.get_parameter("timing_mode") or "next_session"' in s
    assert 'self.timing_mode not in ("strict", "next_session")' in s
    assert "self.securities[self.anchor].exchange.hours" in s
    assert 'label = "SAME_DAY"' in s
    assert 'label = "NEXT_SESSION"' in s
    assert 'self.summary["strict_days"] += 1' in s
    assert 'self.summary["next_session_days"] += 1' in s
    assert 'f"strict_days={self.summary[' in s
    assert 'f"next_days={self.summary[' in s
    assert "self.callback_events.append(event)" in s
    assert "VERIFIED_NEXT_EXCHANGE_SESSION" not in s  # separate pure helper
    assert "datetime(2024, 6, 3" not in s  # no hard-coded market days


def test_2_7_weekend_holiday_mapping_fail_closed():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from types import SimpleNamespace
    import pandas as pd
    from research.cohort_cloud.timing_gate import next_session_fundamentals

    et = ZoneInfo("America/New_York")
    def dt(day, hour=0, minute=0):
        return datetime.fromisoformat(day).replace(
            hour=hour, minute=minute, tzinfo=et)

    class ExchangeCalendar:
        def __init__(self, nontrading, next_opens):
            self.nontrading, self.next_opens = nontrading, next_opens
        def is_date_open(self, value, extended_market_hours=False):
            assert not extended_market_hours
            return value.date().isoformat() not in self.nontrading
        def get_next_market_open(self, value, extended_market_hours=False):
            assert not extended_market_hours
            return self.next_opens[value.date().isoformat()]

    # Native market hours are mocked at boundaries; NO calendar used by
    # the executable strategy other than LEAN's Exchange.Hours.
    hours = ExchangeCalendar(
        {"2024-06-08", "2024-06-09", "2024-06-19"},
        {"2024-06-08": datetime(2024, 6, 10, 9, 30),
         "2024-06-19": datetime(2024, 6, 20, 9, 30)})
    event = lambda when, ends, complete=True: dict(
        at=when, symbols=("A", "B"), source_min=ends,
        source_max=ends, complete=complete)
    friday_close = dt("2024-06-08")
    saturday = event(friday_close, friday_close)
    convert = lambda value: pd.Timestamp(value).tz_localize(et) if (
        value.tzinfo is None) else pd.Timestamp(value).tz_convert(et)
    due, reason = next_session_fundamentals(
        [saturday], dt("2024-06-10", 9, 29), hours, convert)
    assert due is saturday and reason == "VERIFIED_NEXT_EXCHANGE_SESSION"
    holiday = event(dt("2024-06-19"), dt("2024-06-19"))
    due, _ = next_session_fundamentals(
        [saturday, holiday], dt("2024-06-20", 9, 29), hours, convert)
    assert due is holiday
    assert next_session_fundamentals(
        [saturday], dt("2024-06-11", 9, 29), hours, convert)[0] is None
    assert next_session_fundamentals(
        [event(friday_close, friday_close, False)],
        dt("2024-06-10", 9, 29), hours, convert)[0] is None
    assert next_session_fundamentals(
        [event(friday_close, friday_close+timedelta(hours=1))],
        dt("2024-06-10", 9, 29), hours, convert)[0] is None
    assert next_session_fundamentals(
        [saturday, saturday], dt("2024-06-10", 9, 29), hours, convert)[1] == (
            "AMBIGUOUS_NEXT_SESSION_CALLBACKS")
    assert next_session_fundamentals(
        [saturday], dt("2024-06-10", 9, 31), hours, convert)[0] is None


def test_2_7_capture_real_selected_fundamental_endtimes_and_generator():
    from types import SimpleNamespace
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from research.cohort_cloud.timing_gate import freeze_fundamental_event
    et = ZoneInfo("America/New_York")
    at = datetime(2024, 6, 8, 0, 0, tzinfo=et)
    selected = ("A", "C")
    items = [SimpleNamespace(symbol=name, end_time=at)
             for name in ("A", "B", "C")]
    out = freeze_fundamental_event(
        (x for x in items), None, at,
        lambda values, cfg: selected,
        lambda dt: dt)
    assert out["complete"] and out["symbols"] == selected
    assert out["source_min"] == at == out["source_max"]
    items[2].end_time = None
    bad = freeze_fundamental_event(
        items, None, at, lambda values, cfg: selected,
        lambda dt: (_ for _ in ()).throw(TypeError()) if dt is None else dt)
    assert not bad["complete"]
