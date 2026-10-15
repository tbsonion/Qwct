"""Pure CI guards for QWCT 2.5 separate native M5 research; no LEAN mock fills."""
import ast
from datetime import date, datetime, timedelta
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
from strategy.config import StrategyConfig
from strategy.levels import Level

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "research" / "m5_cloud" / "main.py"
ET = ZoneInfo("America/New_York")


def only(name, deps):
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == name)
    namespace = dict(deps)
    exec(compile(ast.fix_missing_locations(
        ast.Module(body=[fn], type_ignores=[])), str(APP), "exec"), namespace)
    return namespace[name]


def local_timestamp(v):
    ts = pd.Timestamp(v)
    return ts.tz_localize(ET) if ts.tzinfo is None else ts.tz_convert(ET)


def fake_day_bars():
    days = pd.bdate_range("2024-02-01", periods=70, tz=ET)
    pivot_idx, confirm_idx = 25, 42
    d1 = pd.DataFrame(index=days)
    d1["high"], d1["low"], d1["close"] = 105., 95., 100.
    d1["bar_end"] = days + pd.Timedelta(hours=16)
    d1.loc[days[pivot_idx], "high"] = 182.87
    d1.loc[days[confirm_idx], "high"] = 183.0
    level = Level(
        price=183.56, kind="resistance", touches=2, strength=2.,
        first_idx=pivot_idx, last_idx=confirm_idx,
        formed_at=days[confirm_idx].date(),
        valid_from=days[confirm_idx+3].date()+timedelta(days=1),
        source="swing_cluster")
    target = ("2024-05-15", "TSLA", "short",
              str(days[pivot_idx].date()), 182.87, 183.56)
    session = date(2024, 5, 15)
    native = [
        SimpleNamespace(time=d, end_time=d + pd.Timedelta(hours=16),
                        high=float(d1.iloc[i]["high"]),
                        low=float(d1.iloc[i]["low"]),
                        close=float(d1.iloc[i]["close"]))
        for i, d in enumerate(days)
    ]
    return d1, level, target, session, native


def test_recover_exact_original_swing_and_never_round_source():
    d1, lvl, target, session, _ = fake_day_bars()
    def fake_swings(frame, k):
        return ([(lvl.first_idx, 182.87, date(2024, 3, 1)),
                 (lvl.last_idx, 183., d1.index[lvl.last_idx+3].date())], [])
    choose = only("choose_original_origin", {
        "isfinite": isfinite, "timedelta": timedelta,
        "_confirmed_swings": fake_swings,
    })
    got, reason = choose(d1, [lvl], target, session, StrategyConfig(), .01)
    assert got is lvl and reason.startswith("OBSERVED_D1_SWING_PROXY")
    bad = list(target)
    bad[4] = 182.88
    assert choose(d1, [lvl], tuple(bad), session,
                  StrategyConfig(), .01)[0] is None
    d1.loc[d1.index[lvl.first_idx], "high"] = 182.875
    changed = list(target)
    changed[4] = 182.875
    assert choose(d1, [lvl], tuple(changed), session,
                  StrategyConfig(), .01)[1] == "SUBTICK_PIVOT_MANUAL_REVIEW"
    assert choose(d1, [lvl], target,
                  d1.index[-1].date(), StrategyConfig(), .01)[0] is None


def test_raw_scaled_provenance_gate_match_shift_future_and_duplicate():
    d1, lvl, target, session, raw = fake_day_bars()
    compare = only("compare_closed_bases", {
        "isfinite": isfinite, "et": local_timestamp
    })
    scaled = [SimpleNamespace(**vars(x)) for x in raw]
    assert compare(raw, scaled, lvl, session, .01) == (
        True, "RAW_SCALED_ORIGIN_LATEST_MATCH")
    scaled[lvl.first_idx].high -= 1.
    assert compare(raw, scaled, lvl, session, .01)[1] == (
        "SCALED_SOURCE_REBASED")
    scaled[lvl.first_idx].high += 1.
    scaled[-1].close += .5
    assert compare(raw, scaled, lvl, session, .01)[1] == (
        "SCALED_LATEST_DIFF")
    scaled[-1].close -= .5
    assert compare(raw, scaled[:-1], lvl, session, .01)[1] == (
        "SCALED_ORIGIN_OR_LATEST_MISSING")
    assert compare(raw, scaled+[scaled[-1]], lvl, session, .01)[1] == (
        "SCALED_FUTURE_OR_DUPLICATE")
    scaled[-1].end_time = pd.Timestamp("2024-05-15", tz=ET)
    assert compare(raw, scaled, lvl, session, .01)[0] is False


def test_six_targets_exact_native_m5_no_orders_and_reuse_existing_detector():
    code = APP.read_text(encoding="utf-8")
    parsed = ast.parse(code)
    case_expr = next(
        n.value for n in parsed.body if isinstance(n, ast.Assign)
        and any(isinstance(k, ast.Name) and k.id == "CASES"
                for k in n.targets))
    rows = ast.literal_eval(case_expr)
    assert len(rows) == 6
    assert {r[1] for r in rows} == {
        "TSLA", "TXN", "AAPL", "AMAT", "META", "NFLX"}
    assert len({(r[0], r[1]) for r in rows}) == 6
    assert {r[0] for r in rows} == {
        "2024-04-10", "2024-04-11", "2024-04-16",
        "2024-04-18", "2024-04-19"}
    for required in (
        "BsuDetector(", "validate_m5_tradebar(",
        "self.consolidate(symbol, timedelta(minutes=5), self._on_m5)",
        "Resolution.MINUTE", "DataNormalizationMode.RAW",
        "DataNormalizationMode.SCALED_RAW",
        "origin_end < last_end < et(self.time)",
        "manual_bsu=UNVERIFIED", "TVX_UNVERIFIED",
        "QWCT M5 SUMMARY", "QWCT M5 CASE",
        "SPLIT_QUARANTINED", "SCALED_SOURCE_REBASED",
    ):
        assert required in code
    for forbidden in (
        "self.market_order(", "self.limit_order(", "self.stop_market_order(",
        "self.set_holdings(", "self.buy(", "self.sell(", "Resolution.SECOND",
        "Resolution.TICK", "observe_preclose(",
    ):
        assert forbidden not in code
    assert len(code.encode("utf-8")) < 32_000


def test_native_closed_m5_detects_only_proxy_not_preclose_tvx():
    from strategy.patterns_bsu import BsuDetector, Bar
    cfg = StrategyConfig()
    src = datetime(2024, 3, 11, 16, 0, tzinfo=ET)
    det = BsuDetector(cfg, 182.87, "short",
                      atr_value=3., tick_size=.01, bsu_ts=src)
    t = datetime(2024, 4, 10, 12, 5, tzinfo=ET)
    first = det.on_bar(Bar(
        ts=t, open=182.5, high=182.87, low=182.4,
        close=182.6, volume=1000., timeframe="M5"))
    assert first.phase == "bpu1"
    second = det.on_bar(Bar(
        ts=t+timedelta(minutes=5), open=182.6,
        high=182.86, low=182.3, close=182.45,
        volume=1500., timeframe="M5"))
    assert second.phase == "bpu2_confirmed"
    assert second.preclose_seen is False
    assert second.can_submit is False
