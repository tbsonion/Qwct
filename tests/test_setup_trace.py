"""Deterministic audit traces; synthetic examples are not strategy fills.

Tests first: failing tests must demonstrate that our previous program
could not replay its accepted D1 models into final M5 rejection reasons.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.levels import Level
from strategy.scenarios import ScenarioDecision
from strategy.research_trace import SetupTrace, summarize_traces


ET = ZoneInfo("America/New_York")


def accepted(symbol="TSLA", model="bounce", side="long", level=100.0):
    day = date(2024, 1, 3)
    ts = datetime(2024, 1, 3, 9, 29, tzinfo=ET)
    lvl = Level(level, "support" if side == "long" else "resistance",
                2, 3, valid_from=day, first_idx=20, last_idx=45,
                formed_at=date(2023, 12, 29))
    return ScenarioDecision(symbol, day, ts, lvl, model, side, 4.5,
                            positives=["g03", "g09"])


def test_single_accepted_d1_to_m5_trace_preserves_provenance_and_gate_failures():
    setup = accepted()
    trace = SetupTrace.from_decision(setup, d1_close=101.0,
                                      native_atr=3.0, level_count=4)
    trace.set_bsu(False, "no native swing matching exact level")
    ts = datetime(2024, 1, 3, 10, 35, tzinfo=ET)
    trace.observe_m5(ts, {"m5_confirmed": (False, "no level crossing"),
                          "risk_approved": (None, "no native risk approval"),
                          "trend_aligned": (True, "aligned")})
    trace.observe_m5(ts + timedelta(minutes=5),
                     {"m5_confirmed": (True, "crossed"),
                      "risk_approved": (None, "no native risk approval"),
                      "trend_aligned": (False, "wrong side")})
    row = trace.as_dict()
    assert row["symbol"] == "TSLA"
    assert row["session"] == "2024-01-03"
    assert row["model"] == "bounce"
    assert row["score"] == 4.5
    assert row["feature_positives"] == ["g03", "g09"]
    assert row["d1_close"] == 101.0
    assert row["d1_atr"] == 3.0
    assert row["level_count"] == 4
    assert row["level_kind"] == "support"
    assert row["level_source"] == "swing_cluster"
    assert row["level_first_idx"] == 20
    assert row["level_last_idx"] == 45
    assert row["level_valid_from"] == "2024-01-03"
    assert row["level_formed_at"] == "2023-12-29"
    assert row["bsu"] == "blocked"
    assert row["bsu_reason"] == "no native swing matching exact level"
    assert row["m5_checks"] == 2
    assert row["first_m5"].startswith("2024-01-03T10:35")
    assert row["last_m5"].startswith("2024-01-03T10:40")
    assert row["failed_gate_counts"] == {
        "m5_confirmed": 1, "risk_approved": 2, "trend_aligned": 1}
    assert row["last_gate_outcomes"]["m5_confirmed"] == "TRUE"
    assert row["last_gate_outcomes"]["risk_approved"] == "UNKNOWN"
    assert row["last_gate_outcomes"]["trend_aligned"] == "FALSE"
    line = trace.log_line()
    assert line.startswith("QWCT TRACE TSLA 2024-01-03")
    assert "M5=2" in line
    assert "risk_approved:2" in line


def test_six_setup_traces_are_separate_and_zero_candidates_explained():
    traces = []
    for i in range(6):
        setup = accepted(symbol=f"STK{i}", model="bounce" if i < 2 else "breakout")
        trace = SetupTrace.from_decision(setup, d1_close=101., native_atr=2.,
                                          level_count=3)
        trace.set_bsu(False, "no BPU" if i < 2 else "not eligible model")
        trace.observe_m5(datetime(2024, 1, 3, 11, i * 5, tzinfo=ET),
                         {"m5_confirmed": (False, "not crossed"),
                          "risk_approved": (None, "not approved")})
        traces.append(trace)
    result = summarize_traces(traces, limit=10)
    assert len(result) == 6
    assert all("STK" in x and "M5=1" in x and "candidate=NO" in x for x in result)


def test_invalidated_bpu2_reasons_and_m5_gate_explanations_are_visible():
    t = SetupTrace.from_decision(accepted(), 101., 2., 3)
    t.set_bsu(True, "native swing candidate; no TVX")
    t.bpu1_count += 1
    t.add_bpu_failure("BPU2 wick broke BPU1 extreme")
    t.add_bpu_failure("BPU2 wick broke BPU1 extreme")
    at = datetime(2024, 1, 3, 12, 5, tzinfo=ET)
    t.observe_m5(at, {
        "m5_confirmed": (False, "M5 close never crossed level"),
        "risk_approved": (None, "no real portfolio manager"),
    })
    assert t.as_dict()["bpu_failure_reasons"] == {
        "BPU2 wick broke BPU1 extreme": 2}
    text = t.log_line()
    assert "BPU-invalid=" in text
    assert "BPU2 wick" in text
    assert "close never crossed" in text
    assert "no real portfolio" in text


def test_cloud_free_trace_logs_are_split_into_short_readable_parts():
    t = SetupTrace.from_decision(accepted(), 101., 2., 3)
    t.set_bsu(False, "missing verified swing-source BSU evidence")
    t.observe_m5(datetime(2024, 1, 3, 12, 5, tzinfo=ET),
                 {"m5_confirmed": (False, "no observed crossing"),
                  "risk_approved": (None, "not native-approved")})
    lines = t.display_lines()
    assert len(lines) == 4
    assert all(len(s) <= 190 for s in lines)
    assert lines[0].startswith("QWCT D1 TSLA")
    assert lines[1].startswith("QWCT M5 TSLA")
    assert lines[2].startswith("QWCT GATES TSLA")
    assert lines[3].startswith("QWCT BSU TSLA")
    assert "no observed crossing" in lines[2]
    assert "missing verified" in lines[3]


def test_no_m5_bar_is_not_indistinguishable_from_failed_m5():
    t = SetupTrace.from_decision(accepted(), 102., 2.5, 3)
    row = t.as_dict()
    assert row["m5_checks"] == 0
    assert row["last_gate_outcomes"] == {}
    assert "M5=0" in t.log_line()


def test_trace_gate_status_never_interprets_unknown_as_true():
    t = SetupTrace.from_decision(accepted(), 99., 1.1, 2)
    t.observe_m5(datetime(2024, 1, 3, 10, 35, tzinfo=ET),
                 {"m5_confirmed": (None, "missing"),
                  "risk_approved": (None, "missing")})
    assert t.as_dict()["last_gate_outcomes"] == {
        "m5_confirmed": "UNKNOWN", "risk_approved": "UNKNOWN"}
    assert t.as_dict()["failed_gate_counts"]["m5_confirmed"] == 1
    assert not t.as_dict()["candidate"]


def test_invalid_timestamps_or_unaccepted_scenarios_cannot_be_traced():
    d = accepted()
    d.model = None
    with pytest.raises(ValueError):
        SetupTrace.from_decision(d, 100., 3., 5)
    d = accepted()
    t = SetupTrace.from_decision(d, 100., 3., 5)
    with pytest.raises(ValueError):
        t.observe_m5(datetime(2024, 1, 3, 10, 0),
                     {"m5_confirmed": (True, "unknown tz")})


def test_real_previous_and_current_m5_ohlc_are_preserved_for_replay():
    t = SetupTrace.from_decision(accepted(), 99.7, 2.0, 2)
    first = datetime(2024, 1, 3, 10, 35, tzinfo=ET)
    second = first + timedelta(minutes=5)
    bars = [
        {"date": pd.Timestamp(first), "open": 99.6, "high": 99.9,
         "low": 99.2, "close": 99.7, "volume": 1200.0},
        {"date": pd.Timestamp(second), "open": 99.7, "high": 100.3,
         "low": 99.6, "close": 100.2, "volume": 2200.0},
    ]
    t.observe_m5(second, {"m5_confirmed": (True, "confirmed cross")},
                 closed_bars=bars)
    out = t.as_dict()
    assert out["last_two_m5"][0]["close"] == 99.7
    assert out["last_two_m5"][1]["close"] == 100.2
    assert out["last_two_m5"][1]["volume"] == 2200.
    assert out["last_two_m5"][1]["time"].startswith("2024-01-03T10:40")
    assert "m5_ohlc=" in t.log_line()


def test_unavailable_or_future_m5_bar_never_fabricated_in_evidence():
    t = SetupTrace.from_decision(accepted(), 99.7, 2.0, 2)
    now = datetime(2024, 1, 3, 10, 40, tzinfo=ET)
    with pytest.raises(ValueError):
        t.observe_m5(now, {}, closed_bars=[
            {"date": pd.Timestamp(now) + pd.Timedelta(minutes=5),
             "open": 100., "high": 101., "low": 99.,
             "close": 100., "volume": 500}])
    assert t.as_dict()["m5_checks"] == 0


def test_replay_reports_are_bounded_and_no_data_is_invented():
    traces = [SetupTrace.from_decision(accepted(symbol=f"T{i}"),
              100., 2., 2) for i in range(8)]
    rows = summarize_traces(traces, limit=3)
    assert len(rows) == 4
    assert "omitted 5" in rows[-1]
    assert "M5=0" in rows[0]


def test_actual_strategy_signal_gates_feed_trace_not_fabricated_gate_values():
    # Exercises actual build_intent + evaluate_gates logic, not manually
    # invented gate outcomes. LEAN native callbacks still need Cloud test.
    from strategy.signals import build_intent
    from strategy.data import MarketData
    idx = pd.bdate_range(end="2024-01-02", periods=110, tz=ET)
    d1 = pd.DataFrame({
        "open": 99.8, "high": 101.0, "low": 98.8,
        "close": 99.9, "volume": 500000,
        "atr14": 2.0, "sma50": 99.5,
    }, index=idx)
    from strategy.breakout_retest import BreakoutRetestObserver
    m5_idx = pd.DatetimeIndex([
        datetime(2024, 1, 3, 10, 35, tzinfo=ET),
        datetime(2024, 1, 3, 10, 40, tzinfo=ET),
        datetime(2024, 1, 3, 10, 45, tzinfo=ET),
        datetime(2024, 1, 3, 10, 50, tzinfo=ET)])
    m5 = pd.DataFrame(
        [[99.6, 99.9, 99.3, 99.7],
         [99.7, 100.3, 99.6, 100.2],
         [100.2, 100.3, 99.9, 100.08],
         [100.08, 100.5, 100.01, 100.42]],
        index=m5_idx,
        columns=["open", "high", "low", "close"])
    decision = accepted(model="breakout", side="long", level=100.)
    trace = SetupTrace.from_decision(decision, d1_close=99.9,
                                     native_atr=2.0, level_count=2)
    trace.set_bsu(False, "not eligible: model is not bounce")
    obs = BreakoutRetestObserver(
        symbol="TSLA", session=decision.session, side="long",
        level_price=100., atr_value=2., max_confirm_chase_atr=0.3)
    # BEFORE confirmation, a plain closed M5 breakout must NOT satisfy
    # the full same-level retest confirmation gate.
    for i in range(2):
        row = m5.iloc[i]
        obs.on_m5(
            at=m5_idx[i].to_pydatetime(), open_price=row.open,
            high=row.high, low=row.low, close=row.close, volume=500)
    early_market = MarketData(
        "TSLA", d1, m5.iloc[:2], session_levels=(decision.level,),
        breakout_retest=obs.evidence)
    early_intent = build_intent(
        decision, early_market, m5_idx[1].to_pydatetime(),
        StrategyConfig(), equity=25000.)
    assert early_intent.gates["m5_confirmed"].passed is False
    for i in range(2, 4):
        row = m5.iloc[i]
        obs.on_m5(
            at=m5_idx[i].to_pydatetime(), open_price=row.open,
            high=row.high, low=row.low, close=row.close, volume=500)
    assert obs.phase == "CONFIRMED"
    market = MarketData(
        "TSLA", d1, m5, session_levels=(decision.level,),
        breakout_retest=obs.evidence)
    intent = build_intent(decision, market, m5_idx[-1].to_pydatetime(),
                          StrategyConfig(), equity=25000.)
    assert intent is not None
    assert intent.gates["m5_confirmed"].passed is True
    assert intent.gates["risk_approved"].passed is None
    trace.observe_m5(m5_idx[-1].to_pydatetime(), {
        name: (gate.passed, gate.reason)
        for name, gate in intent.gates.items()})
    row = trace.as_dict()
    assert row["m5_checks"] == 1
    assert row["last_gate_outcomes"]["m5_confirmed"] == "TRUE"
    assert row["last_gate_outcomes"]["risk_approved"] == "UNKNOWN"
    assert row["candidate"] is False
    assert "no native risk approval" in row["last_gate_reasons"]["risk_approved"]
