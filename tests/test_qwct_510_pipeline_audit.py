"""Metadata/three-valued-logic tests only. No generated market candles/fills.

These checks do not establish native Cloud data, author labels or TVX.
"""
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.config import StrategyConfig
from strategy.data import MarketData
from strategy.features import FeatureResult, FEATURES, _coerce, _without_exception
from strategy.levels import Level
from strategy.pipeline_audit import audit_pipeline, feature_snapshot, gate_snapshot, _chronology
from strategy.scenarios import ScenarioDecision, _score_bounce
from strategy.signals import GATE_IDS, GateResult
import strategy.features as feature_module
import strategy.pipeline_audit as audit_module

ET=ZoneInfo('America/New_York')
AT=datetime(2024,6,3,12,20,tzinfo=ET)
FREEZE=AT.replace(hour=9,minute=29)


@pytest.mark.parametrize('observed,exception,want', [
    (False,False,False),(False,True,False),(False,None,False),
    (True,False,True),(True,True,False),(True,None,None),
    (None,False,None),(None,True,False),(None,None,None),
])
def test_exception_logic_preserves_unknown(observed,exception,want):
    result=_without_exception(observed,exception)
    assert result is want
    feat=FeatureResult('g12_contaminated_zone',result)
    score,_=_score_bounce({'g12':feat},StrategyConfig())
    assert score==(1.5 if want is True else 0.0)


@pytest.mark.parametrize('value',[1,0,-1,float('nan'),float('inf'),'False','True',[],{}])
def test_truthy_non_boolean_is_never_a_positive_feature(value):
    with pytest.raises(ValueError,match='FEATURE_BOOLEAN'):
        _coerce(value)


@pytest.mark.parametrize('value,want',[(np.bool_(True),True),(np.bool_(False),False),(None,None)])
def test_native_pandas_boolean_contract(value,want):
    assert _coerce(value) is want


def features():
    return {name:FeatureResult(name,None,{'unavailable':None},'NOT_OBSERVED')
            for name,_ in FEATURES}


def gates():
    return {name:GateResult(name,True,'TEST_ONLY_GATE_METADATA') for name in GATE_IDS}


def test_all_fourteen_unknowns_are_retained_with_details():
    rows,blockers=feature_snapshot(features())
    assert len(rows)==14 and not blockers
    assert all(row['value'] is None and row['detail']['unavailable'] is None
               for row in rows.values())
    rows,blockers=feature_snapshot({})
    assert len(rows)==14 and 'FEATURE_IDENTITIES_INCOMPLETE_OR_EXTRA' in blockers
    assert all(x['value'] is None for x in rows.values())


def test_bad_feature_or_exception_cannot_hide_behind_remaining_positives():
    f=features(); f['g01']=FeatureResult('bad',float('nan'))
    f['g02']=FeatureResult('g02',None,reason='ошибка: unavailable')
    rows,blockers=feature_snapshot(f)
    assert rows['g01']['value'] is None
    assert 'g01:INVALID_BOOLEAN' in blockers and 'g02:CALCULATION_ERROR' in blockers


@pytest.mark.parametrize('name',GATE_IDS)
@pytest.mark.parametrize('value',[False,None])
def test_every_mandatory_gate_rejects_false_and_unknown(name,value):
    g=gates(); g[name]=GateResult(name,value,'TEST_ONLY')
    rows,blockers=gate_snapshot(g)
    assert rows[name]['passed'] is value
    assert name+(':UNKNOWN' if value is None else ':FALSE') in blockers


@pytest.mark.parametrize('bad',[1,np.bool_(True),'True'])
def test_gate_bool_contract_is_stricter_than_truthiness(bad):
    g=gates(); g['trend_aligned']=GateResult('trend_aligned',bad)
    rows,blockers=gate_snapshot(g)
    assert rows['trend_aligned']['passed'] is None
    assert 'trend_aligned:INVALID_GATE_RECORD' in blockers


def test_gate_missing_extra_or_internal_identity_mismatch():
    g=gates(); del g['risk_approved']; g['wrong']=GateResult('wrong',True)
    rows,blockers=gate_snapshot(g)
    assert rows['risk_approved']['passed'] is None
    assert 'GATE_IDENTITIES_INCOMPLETE_OR_EXTRA' in blockers
    g=gates(); g['m5_confirmed']=GateResult('risk_approved',True)
    assert 'm5_confirmed:INVALID_GATE_RECORD' in gate_snapshot(g)[1]


def metadata_market():
    # Time/identity records only: deliberately NO OHLC market data.
    day=pd.Timestamp('2024-05-31',tz=ET)
    d1=pd.DataFrame({'bar_end':[day+pd.Timedelta(hours=16)],'metadata_only':[True]},index=pd.DatetimeIndex([day]))
    m5=pd.DataFrame({'metadata_only':[True,True]},index=pd.DatetimeIndex([AT-timedelta(minutes=5),AT]))
    lvl=Level(123.87,'support',touches=2,strength=3,valid_from=date(2024,5,31))
    decision=ScenarioDecision('TEST_METADATA_ONLY',AT.date(),FREEZE,lvl,'bounce','long',features=features())
    return decision,MarketData('TEST_METADATA_ONLY',d1,m5,session_levels=(lvl,))


def test_absent_prices_do_not_create_a_canonical_intent():
    d,m=metadata_market()
    result=audit_pipeline(d,m,AT,StrategyConfig())
    assert result['intent'] is None and result['can_trade'] is False
    assert result['status']=='BLOCKED' and 'CANONICAL_INTENT_UNAVAILABLE' in result['blockers']
    assert len(result['features'])==14 and len(result['gates'])==8


@pytest.mark.parametrize('mutation,reason',[
    ('symbol','FROZEN_DECISION_IDENTITY'),('future_freeze','FROZEN_DECISION_IDENTITY'),
    ('no_levels','SESSION_LEVEL_SNAPSHOT'),('missing_ends','D1_NATIVE_ENDTIME'),
    ('future_end','D1_NOT_CLOSED'),('duplicate','INPUT_CHRONOLOGY'),
    ('unsorted','INPUT_CHRONOLOGY'),('stale','M5_STALE'),('gap','M5_STALE'),
])
def test_bad_chronology_stops_before_canonical_builder(monkeypatch,mutation,reason):
    d,m=metadata_market()
    if mutation=='symbol': d.symbol='OTHER'
    elif mutation=='future_freeze': d.decided_at=AT+timedelta(seconds=1)
    elif mutation=='no_levels': m.session_levels=None
    elif mutation=='missing_ends': m.d1=m.d1.drop(columns='bar_end')
    elif mutation=='future_end': m.d1['bar_end']=[AT]
    elif mutation=='duplicate': m.m5=pd.concat([m.m5,m.m5.iloc[-1:]])
    elif mutation=='unsorted': m.m5=m.m5.iloc[::-1]
    elif mutation=='stale': m.m5=m.m5.iloc[:1]
    elif mutation=='gap': m.m5.index=pd.DatetimeIndex([AT-timedelta(minutes=10),AT])
    def forbidden(*args,**kwargs):
        pytest.fail('canonical builder reached with invalid evidence')
    monkeypatch.setattr(audit_module,'build_intent',forbidden)
    result=audit_pipeline(d,m,AT,StrategyConfig())
    assert any(reason in x for x in result['blockers'])
    assert result['can_trade'] is False


def test_even_all_true_test_metadata_cannot_become_trade_or_native_proof(monkeypatch):
    d,m=metadata_market()
    # Exercise audit orchestration only; not a fabricated market confirmation.
    captured=[]
    def builder(decision,market,at,cfg,**kw):
        captured.append(market)
        return SimpleNamespace(gates=gates(),model='bounce',side='long',
                               limit_price=None,stop_price=None,risk_per_share=None)
    monkeypatch.setattr(audit_module,'build_intent',builder)
    result=audit_pipeline(d,m,AT,StrategyConfig())
    assert result['status']=='BLOCKED' and result['can_trade'] is False
    assert {'AUTHOR_BSU_NOT_CERTIFIED','RECEIVE_TIME_NOT_CERTIFIED','ORDERS_DISABLED'} <= set(result['blockers'])
    assert result['availability']=='EVENT_TIME_ONLY_RECEIVE_TIME_UNVERIFIED'
    assert captured[0] is not m


def test_future_m5_metadata_is_excluded_without_reading_future_prices(monkeypatch):
    d,m=metadata_market()
    m.m5=pd.concat([m.m5,pd.DataFrame({'metadata_only':[True]},index=pd.DatetimeIndex([AT+timedelta(minutes=5)]))])
    seen=[]
    def builder(decision,market,at,cfg,**kw):
        seen.append(market.m5.index[-1]); return None
    monkeypatch.setattr(audit_module,'build_intent',builder)
    report=audit_pipeline(d,m,AT,StrategyConfig())
    assert seen==[AT] and report['m5_bars']==2


def test_evaluate_all_rejects_truthy_bad_function_outputs(monkeypatch):
    monkeypatch.setattr(feature_module,'FEATURES',[('g01',lambda *args: FeatureResult('g01',float('nan')))])
    out=feature_module.evaluate_all(None,None,AT,None,[],StrategyConfig())
    assert out['g01'].value is None and out['g01'].reason.startswith('ошибка:')


def test_bounce_window_is_checked_at_cutoff_not_later_m5_close(monkeypatch):
    d,m=metadata_market()
    at=AT.replace(hour=13,minute=30)
    m.m5.index=pd.DatetimeIndex([at-timedelta(minutes=5),at])
    monkeypatch.setattr(audit_module,'build_intent',lambda *args,**kwargs: None)
    result=audit_pipeline(d,m,at,StrategyConfig())
    assert result['entry_window']['passed'] is True  # 13:29:30, still allowed.
    late=at+timedelta(minutes=5)
    m.m5.index=pd.DatetimeIndex([late-timedelta(minutes=5),late])
    result=audit_pipeline(d,m,late,StrategyConfig())
    assert result['entry_window']['passed'] is False
    assert 'SESSION_ENTRY_WINDOW_FALSE' in result['blockers']
