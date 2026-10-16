"""QWCT 4.0: closed D1 source price provenance + manual chart audit, no orders."""
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.indicators import (
    GerchikChartLabel, D1ReactionTaxon,
    discover_bsu_price_candidates,
    audit_author_bsu_labels, audit_author_reaction_labels,
)
ET=ZoneInfo("America/New_York")
ASOF=date(2024,6,3)


def source_data():
    dates=pd.date_range("2024-04-01",periods=33,freq="B",tz=ET)
    rows=[dict(open=100.,high=102.,low=98.,close=100.,atr14=4.)
          for _ in dates]
    # Confirmed upper swing with distinct fractional RAW high.
    rows[4].update(open=101.,high=108.255,low=100.,close=102.)
    rows[8].update(open=101.,high=108.26,low=100.,close=102.)
    # A truly large bar with price sourced from RAW extremum.
    rows[14].update(open=100.,high=109.,low=96.,close=102.)
    # A REAL opening gap after previously known daily ATR.
    rows[20].update(open=107.,high=110.,low=104.,close=108.)
    # Last days consolidation window, narrow relative to ATR=4.
    for i in range(26,33):
        rows[i].update(open=100.,high=102.,low=98.,close=100.)
    return pd.DataFrame(rows,index=dates)


def find(d1=None,**kwargs):
    params=dict(session=ASOF,swing_k=2,tick_size=.01,atr_column="atr14")
    params.update(kwargs)
    return discover_bsu_price_candidates(
        source_data() if d1 is None else d1,**params)


def test_multiple_provenance_types_only_actual_raw_ohlc_values():
    d1=source_data()
    result=find(d1)
    assert len(result)>0
    assert {"CONFIRMED_SWING","CONSOLIDATION_EDGE","EXPANSION_EDGE","GAP_OPEN"} <= {
        x.origin for x in result}
    mapping={x.date():d1.iloc[i] for i,x in enumerate(d1.index)}
    for cand in result:
        assert cand.price == pytest.approx(float(mapping[cand.source_date][cand.field]))
        assert cand.known_on >= cand.source_date
        assert cand.known_on < ASOF
        assert cand.author_status == "AUTHOR_BSU_UNVERIFIED"
        assert not cand.can_trade
    # The software median of two uneven highs is NEVER synthesized.
    assert all(abs(x.price-108.2575)>1e-5 for x in result)
    high=[x for x in result if x.origin=="CONFIRMED_SWING"
          and x.source_date==d1.index[4].date() and x.role=="resistance"]
    assert high and high[0].price==108.255
    assert high[0].known_on==d1.index[6].date()
    assert high[0].native_grid=="HISTORICAL_GRID_UNKNOWN"
    assert not high[0].exact_d1_revisits


def test_native_on_grid_exact_daily_revisit_is_not_a_bpu1_approval():
    d1=source_data()
    # Genuine second D1 HIGH at a source high (not a trade entry).
    d1.loc[d1.index[22],["open","high","low","close"]]=[101.,109.,98.,101.]
    out=find(d1)
    candidate=next(x for x in out if x.origin=="EXPANSION_EDGE"
                   and x.source_date==d1.index[14].date()
                   and x.role=="resistance")
    assert d1.index[22].date() in candidate.exact_d1_revisits
    assert candidate.author_status=="AUTHOR_BSU_UNVERIFIED"
    assert not candidate.can_trade


def test_historical_confirmation_not_retroactively_moved():
    d1=source_data()
    head=find(d1.iloc[:27].copy())
    full=find(d1)
    for prev in head:
        current=next(x for x in full if (
            x.source_date,x.origin,x.role,x.field)==
            (prev.source_date,prev.origin,prev.role,prev.field))
        assert current.price==prev.price
        assert current.known_on==prev.known_on
        assert current.exact_d1_revisits[:len(prev.exact_d1_revisits)]==prev.exact_d1_revisits


def test_invalid_inputs_fail_closed_and_missing_native_atr_is_not_fabricated():
    d1=source_data()
    with pytest.raises(ValueError,match="BSU40_NONCAUSAL_D1"):
        find(d1,session=d1.index[-1].date())
    with pytest.raises(ValueError,match="BSU40_INVALID_WINDOWS"):
        find(d1,swing_k=0)
    with pytest.raises(ValueError,match="BSU40_MISSING_NATIVE_D1"):
        find(d1.drop(columns="atr14"))
    d1.loc[d1.index[3],"atr14"]=0.
    with pytest.raises(ValueError,match="BSU40_INVALID_NATIVE_ATR"):
        find(d1)
    d1.loc[d1.index[3],"atr14"]=float("nan")
    assert find(d1)  # valid confirmed swings do not invent ATR


def label(cand,**changes):
    kwargs=dict(ticker="AMAT",timeframe="D1",frozen_session=ASOF,
                level_price=cand.price,source_date=cand.source_date,
                evidence_url="https://example.org/author-chart",
                note="Illustrative MANUAL labelled fixture, not real author verification")
    kwargs.update(changes)
    return GerchikChartLabel(**kwargs)


def test_no_chart_ground_truth_is_explicit_unknown():
    out=find()
    b=audit_author_bsu_labels(out,(),ticker="AMAT",session=ASOF,tick_size=.01)
    r=audit_author_reaction_labels((),(),ticker="AMAT",session=ASOF)
    assert b.status==r.status=="NO_AUTHOR_GROUND_TRUTH"
    assert b.matches==r.matches==0 and b.precision.startswith("UNKNOWN")
    assert not b.can_trade and not r.can_trade


def test_manual_source_match_needs_exact_price_and_source_date():
    out=find()
    cand=next(x for x in out if x.native_grid=="ON_CURRENT_GRID")
    audit=audit_author_bsu_labels(
        out,(label(cand),),ticker="AMAT",session=ASOF,tick_size=.01)
    assert audit.matches==1
    assert audit.status=="LABELLED_CANDIDATE_COVERAGE_ONLY"
    assert not audit.can_trade
    off=audit_author_bsu_labels(
        out,(label(cand,level_price=cand.price+0.07),),
        ticker="AMAT",session=ASOF,tick_size=.01)
    assert off.matches==0
    assert off.missed==1
    incomplete=audit_author_bsu_labels(
        out,(label(cand,source_date=None),),ticker="AMAT",
        session=ASOF,tick_size=.01)
    assert incomplete.status=="INCOMPLETE_AUTHOR_SOURCE"
    with pytest.raises(ValueError,match="BSU40_UNSUPPORTED_AUTHOR_MARKUP"):
        audit_author_bsu_labels(
            out,(label(cand,ticker="NFLX"),),ticker="AMAT",
            session=ASOF,tick_size=.01)


def test_positive_reaction_labels_never_claim_accuracy():
    tag=D1ReactionTaxon(
        kind="BOUNCE",observed_on=date(2024,4,17),
        anchor_on=date(2024,4,16),reference_price=100.,
        source_label="FIRST_SWING",phase="MIRROR")
    source=next(x for x in find() if x.native_grid=="ON_CURRENT_GRID")
    matched=label(source,reaction_kind="BOUNCE",
                  reaction_date=tag.observed_on)
    missed=label(source,reaction_kind="CHOP",
                 reaction_date=tag.observed_on)
    result=audit_author_reaction_labels(
        (tag,),(matched,missed),ticker="AMAT",session=ASOF)
    assert result.matches==1 and result.missed==1
    assert result.status=="POSITIVE_LABEL_COVERAGE_NOT_ACCURACY"
    assert "UNKNOWN" in result.precision
    with pytest.raises(ValueError,match="BSU40_REACTION_LABEL_INCOMPATIBLE"):
        audit_author_reaction_labels(
            (tag,),(label(source,reaction_kind="BOUNCE",
                          reaction_date=ASOF),),ticker="AMAT",session=ASOF)
