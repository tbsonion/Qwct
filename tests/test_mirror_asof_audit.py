"""Pure mirror chronology tests: no QuantConnect/broker interaction."""
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

from research.chart_review_qc.mirror_asof_audit import audit_mirror


DAY = date(2024, 1, 11)


def specimen(kind="support"):
    days=pd.date_range("2024-01-01",periods=10,freq="D")
    rows=[dict(open=104.0,high=108.0,low=101.0,close=105.0)
          for _ in days]
    if kind=="support":
        rows[2]=dict(open=105,high=110,low=100,close=104)
        rows[6]=dict(open=101,high=102,low=98,close=99)
        rows[7]=dict(open=99,high=100.4,low=98,close=99.3)
    else:
        rows[2]=dict(open=96,high=100,low=90,close=96)
        rows[6]=dict(open=99,high=104,low=98,close=102)
        rows[7]=dict(open=102,high=104,low=99.8,close=101)
    d1=pd.DataFrame(rows,index=days)
    level=SimpleNamespace(kind="mirror",source="swing_cluster",
        first_idx=2,last_idx=4,formed_at=date(2024,1,5),
        valid_from=date(2024,1,9),price=100.0)
    return d1,level


def test_support_to_resistance_requires_separate_d1_breach_then_retest():
    d,l=specimen("support")
    out=audit_mirror(d,l,DAY,swing_k=1,tolerance=0.5,lookback=20)
    assert out["status"]=="PROXY_VERIFIED",out
    assert (out["original_kind"],out["source"],out["swing_confirm"],
            out["breach"],out["retest"],out["valid_from"])==(
            "support","2024-01-03","2024-01-06",
            "2024-01-07","2024-01-08","2024-01-09")


def test_resistance_to_support_reversal_is_direction_sensitive():
    d,l=specimen("resistance")
    out=audit_mirror(d,l,DAY,swing_k=1,tolerance=0.5,lookback=20)
    assert out["status"]=="PROXY_VERIFIED",out
    assert out["original_kind"]=="resistance"


def test_no_retest_is_not_a_confirmed_mirror():
    d,l=specimen()
    d.loc["2024-01-08","high"]=99.7
    out=audit_mirror(d,l,DAY,1,.5,20)
    assert out["status"]=="UNKNOWN"
    assert out["reason"]=="NO_SEPARATE_CAUSAL_BREACH_AND_RETEST"


def test_no_prior_closed_swing_confirmation_or_future_levels():
    d,l=specimen()
    l.valid_from=date(2024,1,12)
    assert audit_mirror(d,l,DAY,1,.5)["status"]=="UNKNOWN"
    l.valid_from=date(2024,1,5)
    assert audit_mirror(d,l,DAY,1,.5)["reason"]=="LEVEL_CHRONOLOGY_MISMATCH"
    l.valid_from=date(2024,1,10)
    assert audit_mirror(d,l,DAY,1,.5)["reason"]=="RETEST_DATE_DISAGREES_WITH_VALID_FROM"


def test_ambiguous_original_side_never_classified_as_gerchik_level():
    d,l=specimen()
    d.loc["2024-01-03",["high","low"]]=[100.2,99.9]
    assert audit_mirror(d,l,DAY,1,.5)["reason"]=="ORIGINAL_KIND_AMBIGUOUS"


def test_session_day_d1_candle_is_lookahead_and_rejected():
    d,l=specimen()
    future=d.iloc[-1:].copy()
    future.index=[pd.Timestamp("2024-01-11")]
    d=pd.concat([d,future])
    assert audit_mirror(d,l,DAY,1,.5)["reason"]=="D1_NOT_CAUSAL_TO_SESSION"


def test_not_a_mirror_cannot_be_upgraded_by_audit():
    d,l=specimen()
    l.kind="support"
    assert audit_mirror(d,l,DAY,1,.5)["status"]=="SKIP"


def test_production_mirror_preserves_original_role():
    from strategy.config import StrategyConfig
    from strategy.levels import Level, _mark_mirror

    days = pd.date_range("2024-01-01", periods=5, freq="D")
    d1 = pd.DataFrame([
        dict(open=101, high=102, low=100, close=101),
        dict(open=101, high=102, low=100, close=101),
        dict(open=100, high=101, low=98, close=99),   # breach support
        dict(open=99, high=100.2, low=98, close=99), # retest from below
        dict(open=99, high=100, low=98, close=99),
    ], index=days)
    level = Level(
        price=100., kind="support", touches=2, strength=3.,
        valid_from=date(2024, 1, 3), first_idx=0, last_idx=1,
        formed_at=date(2024, 1, 2), source="swing_cluster")
    _mark_mirror([level], d1, StrategyConfig())
    assert level.kind == "mirror"
    assert level.original_kind == "support"
