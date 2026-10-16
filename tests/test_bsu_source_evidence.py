"""Pure checks for causal RAW D1 source-price evidence; no LEAN or trades."""
from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.levels import frozen_mirror_source_evidence

ET = ZoneInfo("America/New_York")


def _sample():
    idx = pd.date_range("2024-04-01", periods=24, freq="B", tz=ET)
    rows = [{"open": 95., "high": 99., "low": 90., "close": 96.} for _ in idx]
    rows[4].update(open=99., high=105., close=101.)
    rows[8]["high"] = 105.  # independently observed repeated historical high
    rows[12].update(open=99., high=104., close=101.)
    rows[17].update(open=106., high=107., low=105., close=106.)
    rows[18].update(open=105., high=107., low=103., close=106.)
    d1 = pd.DataFrame(rows, index=idx)
    lvl = SimpleNamespace(kind="mirror", source="swing_cluster", first_idx=4,
                          last_idx=12, price=104.5, valid_from=idx[16].date())
    trace = {"status": "PROXY_VERIFIED", "original_kind": "resistance",
             "valid_from": str(lvl.valid_from)}
    return d1, lvl, trace, idx


def _run(d1, level, trace, **kwargs):
    kwargs = {"session": date(2024, 5, 6), "tick_size": 0.01, "swing_k": 3} | kwargs
    return frozen_mirror_source_evidence(d1, level, trace, **kwargs)


def test_first_and_last_sources_are_not_approved():
    d1, level, trace, idx = _sample()
    out = _run(d1, level, trace)
    assert [(x.label, x.price) for x in out] == [
        ("FIRST_SWING", 105.), ("LAST_SWING", 104.)]
    assert all(x.status == "AUTHOR_UNVERIFIED" and not x.can_trade for x in out)
    assert idx[8].date() in out[0].original_same_wick_dates
    assert idx[17].date() in out[0].mirror_exact_wick_dates
    assert idx[18].date() in out[0].mirror_pierce_dates
    assert out[0].source_date == idx[4].date()
    assert all(x.price != level.price for x in out)  # median not selected


def test_asof_rejects_target_day_candle():
    d1, level, trace, idx = _sample()
    with pytest.raises(ValueError, match="NONCAUSAL"):
        _run(d1, level, trace, session=idx[-1].date())


def test_trace_cannot_approve_itself():
    d1, level, trace, _ = _sample()
    trace["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="MIRROR_CHRONOLOGY_NOT_VERIFIED"):
        _run(d1, level, trace)


def test_off_grid_does_not_manufacture_exact_touches():
    d1, level, trace, idx = _sample()
    d1.loc[idx[4], "high"] = 105.005
    d1.loc[idx[8], "high"] = 105.005
    out = _run(d1, level, trace)
    assert out[0].current_grid == "OFF_GRID"
    assert not out[0].mirror_exact_wick_dates
    assert out[0].status == "AUTHOR_UNVERIFIED"


def test_same_date_native_bars_fail_closed():
    d1, level, trace, idx = _sample()
    ix = list(d1.index)
    ix[7] = ix[6] + pd.Timedelta(hours=1)
    d1.index = pd.DatetimeIndex(ix)
    with pytest.raises(ValueError, match="NONCAUSAL_OR_DUPLICATE_D1_DATE"):
        _run(d1, level, trace)


def test_corrupt_ohlc_fails_closed():
    d1, level, trace, idx = _sample()
    d1.loc[idx[6], "low"] = 150.
    with pytest.raises(ValueError, match="INVALID_RAW_D1_OHLC_SHAPE"):
        _run(d1, level, trace)


def test_original_swing_and_available_from_are_verified():
    d1, level, trace, idx = _sample()
    level.last_idx = 13  # not a confirmed old-side high
    with pytest.raises(ValueError, match="SOURCE_IS_NOT_CONFIRMED_SWING"):
        _run(d1, level, trace)
    level.last_idx = 12
    level.valid_from = idx[15].date()  # last pivot confirmed on day 15
    trace["valid_from"] = str(level.valid_from)
    with pytest.raises(ValueError, match="SOURCE_CONFIRMED_AFTER_LEVEL_IS_VALID"):
        _run(d1, level, trace)



def test_one_bar_mirror_wick_reclaim_is_different_from_close_through():
    d1, level, trace, idx = _sample()
    out = _run(d1, level, trace)[0]
    # At 18: low breaches FIRST support at 105, but close recovers above.
    assert idx[18].date() in out.mirror_wick_reclaim_dates
    assert idx[18].date() not in out.mirror_close_through_dates
    assert idx[18].date() in out.mirror_range_cross_dates
    # A bar that simply stays wholly below the reference is NOT a bounce.
    assert idx[16].date() in out.mirror_close_through_dates
    assert idx[16].date() not in out.mirror_wick_reclaim_dates
    assert idx[16].date() not in out.mirror_range_cross_dates
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_original_resistance_overshoot_and_return_is_not_exact_touch():
    d1, level, trace, idx = _sample()
    # This historical wick crosses resistance, but its CLOSE is below.
    d1.loc[idx[8], "high"] = 106.
    out = _run(d1, level, trace)[0]
    assert idx[8].date() in out.original_wick_reclaim_dates
    assert idx[8].date() not in out.original_same_wick_dates
    assert out.status == "AUTHOR_UNVERIFIED"


def test_one_bar_mirror_close_through_not_mislabeled_as_reclaim():
    d1, level, trace, idx = _sample()
    d1.loc[idx[19], ["open","high","low","close"]] = [104.,107.,103.,104.]
    out = _run(d1, level, trace)[0]
    assert idx[19].date() in out.mirror_close_through_dates
    assert idx[19].date() not in out.mirror_wick_reclaim_dates
    assert idx[19].date() in out.mirror_range_cross_dates
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_mirror_two_closed_bar_reentry_requires_second_d1_close():
    d1, level, trace, idx = _sample()
    # First session CLOSES below old resistance -> new support,
    # next session CLOSES back above it; neither is BPU1 by itself.
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [106., 107., 103., 104.]
    d1.loc[idx[20], ["open", "high", "low", "close"]] = [104., 107., 103., 106.]
    out = _run(d1, level, trace)[0]
    assert idx[19].date() in out.mirror_close_through_dates
    assert idx[19].date() not in out.mirror_two_bar_reclaim_dates
    assert idx[20].date() in out.mirror_two_bar_reclaim_dates
    # The seed contains an earlier independent close reentry as well.
    assert out.mirror_two_bar_reclaim_dates[-1] == idx[20].date()
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_original_two_bar_reentry_before_new_mirror_role():
    d1, level, trace, idx = _sample()
    # The confirmed source swings still have the same original highs.
    level.valid_from = idx[20].date()
    trace["valid_from"] = str(level.valid_from)
    d1.loc[idx[17], ["open", "high", "low", "close"]] = [103., 107., 101., 106.]
    d1.loc[idx[18], ["open", "high", "low", "close"]] = [106., 107., 101., 102.]
    out = _run(d1, level, trace)[0]
    assert out.original_two_bar_reclaim_dates == (idx[18].date(),)
    assert not out.mirror_two_bar_reclaim_dates
    assert out.status == "AUTHOR_UNVERIFIED"


def test_role_transition_cannot_fake_two_bar_mirror_reentry():
    d1, level, trace, idx = _sample()
    level.valid_from = idx[19].date()
    trace["valid_from"] = str(level.valid_from)
    # Prior close below line happened BEFORE mirror effective date.
    d1.loc[idx[18], ["open", "high", "low", "close"]] = [105., 107., 103., 104.]
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [104., 107., 103., 106.]
    out = _run(d1, level, trace)[0]
    assert idx[19].date() not in out.mirror_two_bar_reclaim_dates
    assert idx[19].date() not in out.original_two_bar_reclaim_dates


def test_original_support_to_mirror_resistance_symmetric_two_bar():
    d1, level, trace, idx = _sample()
    orig = d1[["open", "high", "low", "close"]].copy()
    d1["open"] = 200 - orig["open"]
    d1["high"] = 200 - orig["low"]
    d1["low"] = 200 - orig["high"]
    d1["close"] = 200 - orig["close"]
    level.price = 95.5
    trace["original_kind"] = "support"
    # Break above new resistance and close back below.
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [94., 97., 93., 96.]
    d1.loc[idx[20], ["open", "high", "low", "close"]] = [96., 97., 93., 94.]
    out = _run(d1, level, trace)[0]
    assert out.price == 95.
    assert idx[20].date() in out.mirror_two_bar_reclaim_dates
    # The seed contains an earlier independent close reentry as well.
    assert out.mirror_two_bar_reclaim_dates[-1] == idx[20].date()
    assert out.status == "AUTHOR_UNVERIFIED" and not out.can_trade


def test_tail_geometry_uses_closed_d1_body_and_lean_atr_snapshots():
    d1, level, trace, idx = _sample()
    d1["atr14"] = 5.0
    # Mirror support at FIRST price 105. O=105, L=103, C=106.
    result = _run(d1, level, trace, atr_column="atr14")[0]
    event = next(x for x in result.wick_reactions if x.at == idx[18].date())
    assert (event.role, event.event) == ("support", "TAIL_ONLY_RECLAIM")
    assert event.body == pytest.approx(1.0)
    assert event.defended_wick == pytest.approx(2.0)
    assert event.wick_to_body == pytest.approx(2.0)
    assert event.wick_to_atr == pytest.approx(0.4)
    assert event.penetration_to_atr == pytest.approx(0.4)
    assert event.wick_to_range == pytest.approx(0.5)
    assert event.close_defended_to_atr == pytest.approx(0.2)
    assert event.atr_status == "OK"
    assert result.status == "AUTHOR_UNVERIFIED" and not result.can_trade


def test_body_cross_return_not_mislabeled_tail_only():
    d1, level, trace, idx = _sample()
    d1["atr14"] = 5.0
    # Candle body crosses the line 105: O=104, C=106, low=103.
    d1.loc[idx[19], ["open", "high", "low", "close"]] = [104., 108., 103., 106.]
    event = next(x for x in _run(
        d1, level, trace, atr_column="atr14")[0].wick_reactions
        if x.at == idx[19].date())
    assert event.event == "BODY_CROSS_RECLAIM"
    assert event.defended_wick == pytest.approx(1.0)
    assert event.wick_to_body == pytest.approx(0.5)
    assert event.wick_to_atr == pytest.approx(0.2)


def test_resistance_reclaim_measures_upper_shadow():
    from strategy.levels import _d1_wick_reaction
    candle = pd.Series(dict(open=98., high=102., low=96., close=97.))
    event = _d1_wick_reaction(
        candle, 100., 0.01, "resistance", date(2024, 5, 1), 5.0, True)
    assert (event.role, event.event) == ("resistance", "TAIL_ONLY_RECLAIM")
    assert event.upper_wick == pytest.approx(4.0)
    assert event.lower_wick == pytest.approx(1.0)
    assert event.wick_to_body == pytest.approx(4.0)
    assert event.wick_to_atr == pytest.approx(0.8)
    assert event.close_defended_to_atr == pytest.approx(0.6)


def test_doji_has_undefined_tail_divided_by_body_not_infinity():
    from strategy.levels import _d1_wick_reaction
    candle = pd.Series(dict(open=101., high=104., low=98., close=101.))
    event = _d1_wick_reaction(
        candle, 100., 0.01, "support", date(2024, 5, 1), 5., True)
    assert event.body == 0.0 and event.wick_to_body is None
    assert event.wick_to_atr == pytest.approx(0.6)
    assert event.event == "TAIL_ONLY_RECLAIM"


def test_atr_missing_never_fabricated_and_invalid_fails_closed():
    d1, level, trace, idx = _sample()
    out = _run(d1, level, trace)[0]
    event = next(e for e in out.wick_reactions if e.at == idx[18].date())
    assert event.atr_status == "NOT_REQUESTED" and event.wick_to_atr is None
    with pytest.raises(ValueError, match="NATIVE_D1_ATR_COLUMN_REQUIRED"):
        _run(d1, level, trace, atr_column="atr14")
    d1["atr14"] = 5.0
    d1.loc[idx[18], "atr14"] = float("nan")
    event = next(e for e in _run(
        d1, level, trace, atr_column="atr14")[0].wick_reactions
        if e.at == idx[18].date())
    assert event.atr_status == "NATIVE_ATR_NOT_READY"
    assert event.wick_to_atr is None
    d1.loc[idx[18], "atr14"] = 0.
    with pytest.raises(ValueError, match="INVALID_NATIVE_D1_ATR"):
        _run(d1, level, trace, atr_column="atr14")


def _qwct38_mapper():
    # Isolate the pure chart adapter from its QuantConnect notebook's top-level
    # native Research calls; no LEAN nodes, history queries, plot or orders.
    import ast
    from pathlib import Path
    path = (Path(__file__).resolve().parents[1] / "research" /
            "chart_review_qc" / "GERCHIK_3_3_D1_LEVEL_EVIDENCE_ONE_CELL.py")
    root = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in root.body
                if isinstance(n, ast.FunctionDef) and
                n.name == "chart_reaction_markers")
    scope = {"pd": pd}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(path), "exec"), scope)
    return scope["chart_reaction_markers"]


def test_qwct38_markers_preserve_native_dates_prices_and_first_last():
    m = _qwct38_mapper()
    idx = pd.date_range("2024-04-01", periods=7, freq="B", tz=ET)
    d1 = pd.DataFrame(
        [{"open":100., "high":103., "low":97., "close":101.}
         for _ in idx], index=idx)
    observations = (
        SimpleNamespace(at=idx[2].date(),role="support",
                        event="TAIL_ONLY_RECLAIM",wick_to_body=2.,
                        wick_to_atr=.4),
        SimpleNamespace(at=idx[3].date(),role="support",
                        event="BODY_CROSS_RECLAIM",wick_to_body=1.5,
                        wick_to_atr=.3),
        SimpleNamespace(at=idx[4].date(),role="support",
                        event="CLOSED_WRONG_SIDE",wick_to_body=.5,
                        wick_to_atr=.1),
        SimpleNamespace(at=idx[5].date(),role="support",
                        event="TOUCH_OR_STRADDLE",wick_to_body=None,
                        wick_to_atr=None),
    )
    first = SimpleNamespace(label="FIRST_SWING",status="AUTHOR_UNVERIFIED",
                            can_trade=False,source_date=idx[0].date(),
                            confirmed_date=idx[1].date(),price=100.,
                            wick_reactions=observations,
                            original_two_bar_reclaim_dates=(),
                            mirror_two_bar_reclaim_dates=(idx[5].date(),))
    last = SimpleNamespace(label="LAST_SWING",status="AUTHOR_UNVERIFIED",
                           can_trade=False,source_date=idx[0].date(),
                           confirmed_date=idx[1].date(),price=100.5,
                           wick_reactions=(observations[0],),
                           original_two_bar_reclaim_dates=(),
                           mirror_two_bar_reclaim_dates=())
    markers = m(d1, (first, last))
    assert len(markers) == 5
    assert [p["kind"] for p in markers] == [
        "TAIL_ONLY_RECLAIM","BODY_CROSS_RECLAIM","CLOSED_WRONG_SIDE",
        "TWO_BAR_REENTRY","TAIL_ONLY_RECLAIM"]
    assert markers[0]["at"] == idx[2] and markers[0]["y"] == 97.
    assert markers[1]["y"] == 97.  # support: point to wick low
    assert markers[2]["y"] == 101.  # red: actual closed-D1 close
    assert markers[3]["y"] == 101.  # purple: second candle's close
    assert markers[0]["source"] == "FIRST_SWING"
    assert markers[-1]["source"] == "LAST_SWING"
    assert "tail/native D1 ATR=0.40" in markers[0]["tip"]
    assert "NOT AN AUTHOR-CERTIFIED" in markers[3]["tip"]
    assert all(p["at"] in d1.index for p in markers)


def test_qwct38_resistance_wick_points_to_high_and_rejects_future():
    m = _qwct38_mapper()
    idx = pd.date_range("2024-04-01", periods=4, freq="B", tz=ET)
    d1 = pd.DataFrame(
        [{"open":98., "high":102., "low":96., "close":97.}
         for _ in idx], index=idx)
    obs = SimpleNamespace(at=idx[2].date(),role="resistance",
                          event="TAIL_ONLY_RECLAIM",wick_to_body=4.,
                          wick_to_atr=.8)
    e = SimpleNamespace(label="FIRST_SWING",status="AUTHOR_UNVERIFIED",
                        can_trade=False,source_date=idx[0].date(),
                        confirmed_date=idx[1].date(),price=100.,
                        wick_reactions=(obs,),
                        original_two_bar_reclaim_dates=(),
                        mirror_two_bar_reclaim_dates=())
    assert m(d1,(e,))[0]["y"] == 102.
    # No retroactively plotting a future candle that was not in AS-OF RAW D1.
    obs.at = date(2024, 5, 20)
    with pytest.raises(ValueError,match="NONCAUSAL_WICK_DATE"):
        m(d1,(e,))
    obs.at = idx[2].date()
    e.can_trade = True
    with pytest.raises(ValueError,match="ONLY_UNVERIFIED_SOURCES"):
        m(d1,(e,))


def test_qwct38_two_bar_reentry_may_not_cross_level_during_second_bar():
    m = _qwct38_mapper()
    idx = pd.date_range("2024-04-01", periods=4, freq="B", tz=ET)
    d1 = pd.DataFrame(
        [{"open":111., "high":112., "low":109., "close":110.}
         for _ in idx],index=idx)
    e=SimpleNamespace(label="LAST_SWING",status="AUTHOR_UNVERIFIED",
                      can_trade=False,source_date=idx[0].date(),
                      confirmed_date=idx[1].date(),price=100.,
                      wick_reactions=(),
                      original_two_bar_reclaim_dates=(idx[2].date(),),
                      mirror_two_bar_reclaim_dates=())
    out=m(d1,(e,))
    assert len(out)==1 and out[0]["kind"]=="TWO_BAR_REENTRY"
    assert out[0]["at"]==idx[2] and out[0]["y"]==110.
    assert "phase=ORIGINAL" in out[0]["tip"]


def test_no_orders_market_data_or_median_price_selection():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "strategy" /
           "levels.py").read_text(encoding="utf-8")
    src = src.split("class D1WickReaction:", 1)[1]
    for forbidden in ("market_order(", "limit_order(", "stop_market_order(",
                      "qb.history(", "Resolution.MINUTE", "Resolution.SECOND",
                      "Resolution.TICK", "ATR(", "np.median("):
        assert forbidden not in src, forbidden
