"""Contract tests using event tuples, not market candles or claimed fills."""
import ast
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
import pytest

CELL = Path(__file__).resolve().parents[1] / 'research/chart_review_qc/QWCT_5_6_ORDER_FLOW_DATA_AUDIT_ONE_CELL.py'
SOURCE = CELL.read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
NS = dict(Counter=Counter, timedelta=timedelta, isfinite=isfinite)
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n, ast.FunctionDef)
     and n.name in ('quote_shape', 'trade_window_summary')], type_ignores=[]), str(CELL), 'exec'), NS)
START = datetime(2024, 6, 3, 18, 35, tzinfo=timezone.utc)
CUTOFF = START + timedelta(minutes=4, seconds=30)


@pytest.mark.parametrize('values,expected', [
    ((10,0,100,0),'BID_ONLY'), ((0,11,0,100),'ASK_ONLY'),
    ((10,0,0,0),'BID_ONLY'), ((10,11,100,100),'TWO_SIDED'),
    ((11,11,100,100),'LOCKED'), ((12,11,100,100),'CROSSED'),
    ((0,0,0,0),'ZERO_PRICE_UPDATE'), ((float('nan'),11,1,1),'INVALID'),
    ((10,11,-1,1),'INVALID'), ((10,float('inf'),1,1),'INVALID')])
def test_raw_one_sided_updates_are_not_invalid_quotes(values, expected):
    assert NS['quote_shape'](*values) == expected


def test_cutoff_future_invalid_and_duplicate_event_semantics():
    rows = [(START,10,2), (START,10,3), (START+timedelta(minutes=1),11,7),
            (CUTOFF,12,4), (CUTOFF+timedelta(microseconds=1),99,1000),
            (START,10,float('nan')), (START-timedelta(microseconds=1),10,999)]
    result = NS['trade_window_summary'](rows, START, CUTOFF)
    assert result['observed_volume'] == 16
    assert result['full_minute_tick_volumes'] == [5,7,0,0]
    assert result['repeated_timestamps'] == 1  # Legitimate trades not deduped.
    assert result['excluded'] == {'outside_window':2, 'invalid_trade':1}
    assert result['age_at_cutoff_s'] == 0
    assert result['classification'] == 'ORDER_FLOW_UNAVAILABLE'
    assert result['cvd'] == 'CVD_UNAVAILABLE' and result['can_trade'] is False


def test_empty_or_sparse_events_do_not_certify_data_loss_or_completeness():
    result = NS['trade_window_summary']([], START, CUTOFF)
    assert result['coverage'] == 'NOT_CERTIFIED'
    assert result['max_event_silence_s'] == 270
    assert result['last_trade_at'] is None and result['age_at_cutoff_s'] is None
    sparse = NS['trade_window_summary']([(START,10,1)], START, CUTOFF)
    assert sparse['coverage'] == 'NOT_CERTIFIED'
    assert sparse['max_event_silence_s'] == 270


def test_order_independent_inventory_and_timezone_equivalence():
    rows = [(START+timedelta(seconds=5),10,1), (START,10,2)]
    a = NS['trade_window_summary'](rows, START, CUTOFF)
    b = NS['trade_window_summary'](rows[::-1], START, CUTOFF)
    assert a == b
    assert a['age_at_cutoff_s'] == 265


@pytest.mark.parametrize('start,cutoff,rows', [
    (START.replace(tzinfo=None), CUTOFF, []),
    (CUTOFF,START,[]), (START,CUTOFF,[(START.replace(tzinfo=None),10,1)])])
def test_unknown_time_basis_is_rejected(start,cutoff,rows):
    with pytest.raises(ValueError):
        NS['trade_window_summary'](rows,start,cutoff)


def test_standalone_history_no_strategy_imports_or_execution_calls():
    names = {n.func.attr.lower() for n in ast.walk(TREE)
             if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not names & {'market_order','limit_order','set_holdings','liquidate','stop_market_order','submit_order'}
    assert 'qb.history[Tick]' in SOURCE and 'qb.history[TradeBar]' in SOURCE
    assert 'MAX_ROWS + 1' in SOURCE and 'ROW_CAP_EXCEEDED' in SOURCE
    assert 'NO_RELAXED_SEC_GATE' in SOURCE
    assert not any(isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('strategy') for n in ast.walk(TREE))
