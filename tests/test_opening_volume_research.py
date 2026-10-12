"""Independent read-only ORB paper comparison. No LEAN backtest or broker."""
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from strategy.opening_volume_research import (
    OpeningVolumeBar, review_opening_relative_volume,
)

ET = ZoneInfo("America/New_York")
CURRENT = datetime(2024, 1, 24, 9, 35, tzinfo=ET)
# An explicit collection of observed session labels; not an exchange calendar.
PREVIOUS = (
    "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
    "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12",
    "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19",
    "2024-01-22", "2024-01-23",
)


def sample(when, volume=1000, symbol="AAPL", basis="SPLIT_ADJUSTED"):
    if isinstance(when, str):
        when = datetime.fromisoformat(when + "T09:35:00").replace(tzinfo=ET)
    return OpeningVolumeBar(symbol, when, volume, basis)


def evaluate(current=None, previous=None, at=CURRENT):
    return review_opening_relative_volume(
        observed_at=at, current=current or sample(CURRENT, 2000),
        previous_openings=previous if previous is not None else tuple(
            sample(d) for d in PREVIOUS),
    )


def test_same_time_of_day_fourteen_session_rvol_is_observed_not_estimated():
    v = evaluate()
    assert v.ratio == 2.
    assert v.mean_prior_shares == 1000
    assert v.current_shares == 2000
    assert v.prior_sessions == 14
    assert v.can_submit is False
    assert v.status == "RESEARCH_ONLY_NOT_GERCHIK_APPROVAL"


def test_historical_15th_opening_is_not_part_of_last_14_reference():
    extra = (sample("2024-01-02", 999_999),) + tuple(
        sample(d) for d in PREVIOUS)
    v = evaluate(previous=extra)
    assert v.ratio == 2.
    assert v.prior_sessions == 14


def test_13_days_is_unknown_and_not_artificially_filled():
    v = evaluate(previous=tuple(sample(d) for d in PREVIOUS[:-1]))
    assert v.ratio is None
    assert v.mean_prior_shares is None
    assert v.prior_sessions == 13
    assert "MISSING_14" in v.status


def test_at_929_cannot_know_future_opening_volume():
    v = evaluate(at=CURRENT.replace(hour=9, minute=29))
    assert v.ratio is None
    assert "09:35 ET" in v.status


def test_utc_observation_is_converted_to_et_using_actual_timezone():
    v = evaluate(at=CURRENT.astimezone(timezone.utc))
    assert v.ratio == 2.


def test_future_and_duplicate_prior_m5_days_are_not_admitted():
    current = sample(CURRENT, 2000)
    for bad in (sample(CURRENT), sample("2024-01-25"),
                sample(PREVIOUS[-1])):
        if bad.end_time.date() == CURRENT.date():
            history = tuple(sample(d) for d in PREVIOUS[:-1]) + (bad,)
        else:
            history = tuple(sample(d) for d in PREVIOUS) + (bad,)
        v = evaluate(current=current, previous=history)
        assert v.ratio is None
        assert any(x in v.status for x in ("future", "current", "duplicated"))


def test_wrong_symbol_or_history_adjustment_basis_fails_closed():
    base = tuple(sample(d) for d in PREVIOUS)
    for bad in (replace(base[0], symbol="TSLA"),
                replace(base[0], volume_basis="RAW")):
        v = evaluate(previous=(bad,) + base[1:])
        assert v.ratio is None
        assert "symbol" in v.status or "basis" in v.status


def test_missing_untraded_or_forward_filled_opening_has_no_ratio():
    current = sample(CURRENT, 2000)
    for bad in (replace(current, shares=0.),
                replace(current, shares=float("nan")),
                replace(current, is_fill_forward=True),
                replace(current, end_time=CURRENT.replace(minute=40)),
                replace(current, end_time=CURRENT.replace(tzinfo=None))):
        v = evaluate(current=bad)
        assert v.ratio is None
        assert v.can_submit is False


def test_all_fourteen_historical_openings_must_be_real_positive_volume():
    history = tuple(sample(d) for d in PREVIOUS)
    for bad in (replace(history[-1], shares=0),
                replace(history[-1], is_fill_forward=True)):
        v = evaluate(previous=history[:-1] + (bad,))
        assert v.ratio is None


def test_mixing_20day_total_d1_volume_into_first_five_minute_average_is_rejected():
    history = tuple(sample(d) for d in PREVIOUS)
    # The 09:35 native M5 timestamp is a strict source contract.
    wrong_bar = replace(history[0], end_time=history[0].end_time.replace(hour=16))
    v = evaluate(previous=(wrong_bar,) + history[1:])
    assert v.ratio is None
    assert "09:35 ET" in v.status
