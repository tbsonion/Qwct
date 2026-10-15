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
        "NO_SAME_DAY_FUNDAMENTAL_CALLBACK",
        "Saturday never auto-carried",
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
    assert "after_market_close(anchor, 1)" not in s  # last day would be skipped


def test_missing_and_split_days_never_fabricate_m5():
    s = APP.read_text(encoding="utf-8")
    for required in (
        "self.by_day.get(day)",
        "NO_SAME_DAY_CALLBACK",
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


def test_native_m1_m5_replay_tail_diagnostic_never_invents_last_bar():
    code = APP.read_text(encoding="utf-8")
    assert "def _replay(self, symbol, minute_bars, day, close):" in code
    assert "self._replay(symbol, minute[symbol], day, end)" in code
    for phrase in (
        'last_m1_end = et(minute_bars[-1].end_time)',
        'last_m5_end = et(emitted[-1].end_time) if emitted else None',
        'self.summary["m1_tail_at_close"]',
        'self.summary["m1_tail_before_close"]',
        'self.summary["m5_tail_at_close"]',
        'self.summary["m5_tail_before_close"]',
        "QWCT COHORT TAIL",
        "TIMING AUDIT ONLY / NO SYNTHETIC BAR",
    ):
        assert phrase in code
    assert "consolidator.scan(" not in code  # never flush an unclosed M5
    assert "TradeBar(" not in code  # don't create artificial boundary bars
    assert len(code.encode("utf-8")) < 32_000
