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


def test_replay_reports_are_bounded_and_no_data_is_invented():
    traces = [SetupTrace.from_decision(accepted(symbol=f"T{i}"),
              100., 2., 2) for i in range(8)]
    rows = summarize_traces(traces, limit=3)
    assert len(rows) == 4
    assert "omitted 5" in rows[-1]
    assert "M5=0" in rows[0]
