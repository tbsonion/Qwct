"""Audit structural event tuples only; no synthetic candles or signed trades."""
import ast
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
import pytest

CELL = Path(__file__).resolve().parents[1] / 'research/chart_review_qc/QWCT_5_7_NATIVE_QUOTE_PAIR_AUDIT_ONE_CELL.py'
SOURCE = CELL.read_text()
TREE = ast.parse(SOURCE)
NS = dict(isfinite=isfinite, Counter=Counter, defaultdict=defaultdict, bisect_left=bisect_left)
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n,ast.FunctionDef)
     and n.name in ('describe_quote_group','quote_pair_inventory')], type_ignores=[]), str(CELL),'exec'),NS)
START = datetime(2024,6,3,18,35,tzinfo=timezone.utc)
END = START+timedelta(seconds=30)
BID=(10,0,100,0,'ARCA','1',False,False)
ASK=(0,11,0,200,'NASDAQ','1',False,False)


def audit(quotes, trades=()):
    return NS['quote_pair_inventory'](quotes,trades,START,END)


def test_different_venues_can_form_structural_pair_but_not_certified_nbbo():
    r=audit([(START,BID),(START,ASK)],[(START+timedelta(seconds=1),10,3)])
    assert r['cross_venue_structural_pairs']==1
    assert r['trade_relationship_volumes']=={'PAIR_METADATA_ONLY':3}
    assert r['unknown_aggressor_volume']==3
    assert r['nbbo_message_mapping']=='UNVERIFIED'
    assert r['available_at'] is None and r['can_trade'] is False
    assert r['cvd']=='CVD_UNAVAILABLE'


@pytest.mark.parametrize('rows,expected',[
    ([BID], 'NOT_EXACTLY_TWO_ROWS'),
    ([BID,ASK,ASK], 'NOT_EXACTLY_TWO_ROWS'),
    ([BID,BID], 'NO_UNIQUE_POSITIVE_ONE_SIDED_PAIR'),
    ([BID,(0,11,0,0,'NASDAQ','1',False,False)],'NO_UNIQUE_POSITIVE_ONE_SIDED_PAIR'),
    ([BID,(0,11,0,200,'NASDAQ','0',False,False)],'NON_REGULAR_CONDITION'),
    ([BID,(0,11,0,200,'NASDAQ','1',True,False)],'FLAGGED_GROUP'),
    ([BID,(0,11,0,200,'NASDAQ','1',False,True)],'FLAGGED_GROUP'),
    ([BID,(0,float('nan'),0,200,'NASDAQ','1',False,False)],'INVALID_VALUES'),
    ([BID,(0,11,0,-1,'NASDAQ','1',False,False)],'INVALID_VALUES'),
    ([BID,(0,11,0,200,'','1',False,False)],'EXCHANGE_UNVERIFIED'),
    ([BID,(0,10,0,200,'NASDAQ','1',False,False)],'LOCKED_PAIR'),
    ([BID,(0,9,0,200,'NASDAQ','1',False,False)],'CROSSED_PAIR')])
def test_no_ambiguous_group_is_promoted(rows,expected):
    assert NS['describe_quote_group'](rows)['status']==expected


def test_latest_invalid_group_blocks_older_pair_and_no_async_side_join():
    q=[(START,BID),(START,ASK),(START+timedelta(seconds=1),BID)]
    r=audit(q,[(START+timedelta(seconds=2),10,3)])
    assert r['trade_relationship_counts']=={'LATEST_GROUP_NOT_EXACTLY_TWO_ROWS':1}
    assert r['prior_pair_report_age_s'] is None


def test_equal_time_quotes_abstain_and_future_rows_are_excluded():
    q=[(START+timedelta(seconds=5),BID),(START+timedelta(seconds=5),ASK),
       (END+timedelta(microseconds=1),BID)]
    r=audit(q,[(START,10,2),(START+timedelta(seconds=5),10,3),(END,11,4),
               (END+timedelta(microseconds=1),11,999)])
    assert r['trade_relationship_volumes']=={'NO_PRIOR_QUOTE_GROUP':2,'QUOTE_TRADE_TIME_TIE':3,'PAIR_METADATA_ONLY':4}
    assert r['observed_trade_volume']==r['unknown_aggressor_volume']==9
    assert r['excluded']=={'quotes_outside_window':1,'trades_outside_window':1}
    assert sum(r['trade_relationship_volumes'].values())==9


def test_tie_with_invalid_group_cannot_fall_back_to_old_pair():
    q=[(START,BID),(START,ASK),(END,BID)]
    r=audit(q,[(END,10,1)])
    assert r['trade_relationship_counts']=={'QUOTE_TRADE_TIME_TIE':1}


def test_repeat_trade_timestamps_retained_and_event_order_does_not_choose_pair():
    q=[(START,BID),(START,ASK)]
    t=[(END,10,1),(END,10,2)]
    assert audit(q,t)==audit(q[::-1],t[::-1])
    assert audit(q,t)['valid_trades']==2
    assert audit(q,t)['observed_trade_volume']==3


def test_empty_inventory_remains_unknown_and_bad_trade_volume_is_not_signed():
    assert audit([])['coverage']=='NOT_CERTIFIED'
    r=audit([],[(END,10,float('nan')),(END,10,-1)])
    assert r['valid_trades']==0 and r['excluded']=={'invalid_trade':2}


def test_naive_event_time_rejected():
    with pytest.raises(ValueError):
        audit([(START.replace(tzinfo=None),BID)])
    with pytest.raises(ValueError):
        audit([],[(END.replace(tzinfo=None),10,1)])
    with pytest.raises(ValueError):
        NS['quote_pair_inventory']([],[],START,START)


def test_runtime_scope_native_history_no_bar_generation_book_or_orders():
    assert 'qb.history[Tick]' in SOURCE and 'MAX_ROWS+1' in SOURCE
    calls={ast.unparse(n.func).lower() for n in ast.walk(TREE) if isinstance(n,ast.Call)}
    assert not any(any(s in c for s in ['market_order','limit_order','set_holdings','consolidate','quotebar','tradebar','securitycache']) for c in calls)
    assert not any(isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('strategy') for n in ast.walk(TREE))
