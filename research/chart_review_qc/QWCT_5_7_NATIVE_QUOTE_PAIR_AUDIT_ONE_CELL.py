# QWCT 5.7 -- ONE standalone QuantBook cell. Native quote structure only.
# No candles generated, no book state, no trade-side estimates, no CVD/orders.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import Counter, defaultdict
from bisect import bisect_left
from itertools import islice
from math import isfinite
import json
import pandas as pd

ET = ZoneInfo('America/New_York')
START = datetime(2024, 6, 3, 14, 35, tzinfo=ET)
CUTOFF = datetime(2024, 6, 3, 14, 39, 30, tzinfo=ET)
MAX_ROWS = 150000


def describe_quote_group(rows):
    """Rows share one exact native event time; no asynchronous side carry.

    Tuple: bid,ask,bid_size,ask_size,exchange,condition,suspicious,fill_forward.
    A structural pair is NOT certification of one original NBBO message,
    last-change time of either side, receive time, or aggressor direction.
    """
    if any(r[6] or r[7] for r in rows):
        return {'status': 'FLAGGED_GROUP'}
    if any(not all(isfinite(v) and v >= 0 for v in r[:4]) for r in rows):
        return {'status': 'INVALID_VALUES'}
    if len(rows) != 2:
        return {'status': 'NOT_EXACTLY_TWO_ROWS'}
    if any(str(r[5]).lower().lstrip('0') != '1' for r in rows):
        return {'status': 'NON_REGULAR_CONDITION'}
    bids = [r for r in rows if r[0] > 0 and r[2] > 0 and r[1] == 0 and r[3] == 0]
    asks = [r for r in rows if r[1] > 0 and r[3] > 0 and r[0] == 0 and r[2] == 0]
    if len(bids) != 1 or len(asks) != 1:
        return {'status': 'NO_UNIQUE_POSITIVE_ONE_SIDED_PAIR'}
    b, a = bids[0], asks[0]
    if not b[4] or not a[4]:
        return {'status': 'EXCHANGE_UNVERIFIED'}
    status = 'CROSSED_PAIR' if b[0] > a[1] else ('LOCKED_PAIR' if b[0] == a[1] else 'PAIR_METADATA_ONLY')
    return dict(status=status, bid=b[0], ask=a[1], bid_size=b[2], ask_size=a[3],
                bid_exchange=b[4], ask_exchange=a[4])


def quote_pair_inventory(quotes, trades, start, cutoff):
    """Offline bounded inventory; the latest bad group cannot be skipped.

    Quotes=(aware time, raw tuple), trades=(aware time, price, qty).
    Any quote/trade timestamp tie abstains; no artificial event ordering.
    """
    if (start.tzinfo is None or start.utcoffset() is None or
            cutoff.tzinfo is None or cutoff.utcoffset() is None or cutoff <= start):
        raise ValueError('AWARE_ORDERED_WINDOW_REQUIRED')
    groups = defaultdict(list)
    excluded = Counter()
    for at, row in quotes:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('AWARE_QUOTE_TIME_REQUIRED')
        if start <= at <= cutoff:
            groups[at].append(row)
        else:
            excluded['quotes_outside_window'] += 1
    times = sorted(groups)
    details = {t: describe_quote_group(groups[t]) for t in times}
    statuses = Counter(d['status'] for d in details.values())
    relationships, volumes = Counter(), Counter()
    cross_venue_pairs = 0
    for d in details.values():
        if d['status'] == 'PAIR_METADATA_ONLY' and d['bid_exchange'] != d['ask_exchange']:
            cross_venue_pairs += 1
    ages = []
    valid_trades = 0
    total_volume = 0.0
    # Each valid trade is counted once, including equal timestamps.
    for at, price, qty in trades:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('AWARE_TRADE_TIME_REQUIRED')
        if not start <= at <= cutoff:
            excluded['trades_outside_window'] += 1
            continue
        if not all(isfinite(v) and v > 0 for v in (price, qty)):
            excluded['invalid_trade'] += 1
            continue
        valid_trades += 1
        total_volume += qty
        i = bisect_left(times, at)
        if i < len(times) and times[i] == at:
            reason = 'QUOTE_TRADE_TIME_TIE'
        elif i == 0:
            reason = 'NO_PRIOR_QUOTE_GROUP'
        else:
            latest = times[i-1]
            status = details[latest]['status']
            reason = status if status == 'PAIR_METADATA_ONLY' else 'LATEST_GROUP_' + status
            if status == 'PAIR_METADATA_ONLY':
                ages.append((at-latest).total_seconds())
        relationships[reason] += 1
        volumes[reason] += qty
    sample_times = list(dict.fromkeys(times[:3] + times[-3:]))
    return dict(quote_rows=sum(len(v) for v in groups.values()), quote_groups=len(times),
                group_status_counts=dict(statuses), cross_venue_structural_pairs=cross_venue_pairs,
                sample_groups=[dict(observed_at=t.isoformat(), rows=len(groups[t]), **details[t]) for t in sample_times],
                valid_trades=valid_trades, observed_trade_volume=total_volume,
                trade_relationship_counts=dict(relationships), trade_relationship_volumes=dict(volumes),
                prior_pair_report_age_s=dict(min=min(ages), max=max(ages),
                    le_0_1=sum(v <= 0.1 for v in ages), le_1=sum(v <= 1 for v in ages),
                    le_5=sum(v <= 5 for v in ages)) if ages else None,
                excluded=dict(excluded), unknown_aggressor_volume=total_volume,
                classification='ORDER_FLOW_UNAVAILABLE', cvd='CVD_UNAVAILABLE',
                coverage='NOT_CERTIFIED', available_at=None, receive_time='UNKNOWN',
                side_last_change_times='UNKNOWN', nbbo_message_mapping='UNVERIFIED', can_trade=False)


def run_native_quote_pair_audit():
    qb = QuantBook()
    qb.set_time_zone('America/New_York')
    qb.set_start_date(2024, 7, 1)
    qb.set_end_date(2024, 7, 2)
    print('QWCT 5.7 NATIVE_QUOTE_PAIR_AUDIT NO_ORDERS NOT_TVX_PASS')
    for ticker in ('SRPT', 'SPY'):
        try:
            symbol = qb.add_equity(ticker, Resolution.TICK, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            stream = qb.history[Tick](symbol, START.replace(tzinfo=None),
                (CUTOFF+timedelta(seconds=1)).replace(tzinfo=None), Resolution.TICK,
                fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW)
            raw = list(islice(iter(stream), MAX_ROWS+1))
            if len(raw) > MAX_ROWS:
                print('QWCT 5.7', ticker, 'ROW_CAP_EXCEEDED ORDER_FLOW_UNAVAILABLE NO_ORDERS')
                continue
            quotes, trades = [], []
            counts = Counter()
            for tick in raw:
                if tick.symbol != symbol:
                    counts['wrong_symbol'] += 1
                    continue
                stamp = pd.Timestamp(tick.time)
                at = (stamp.tz_localize(ET) if stamp.tzinfo is None else stamp.tz_convert(ET)).to_pydatetime()
                if tick.tick_type == TickType.QUOTE:
                    quotes.append((at, (float(tick.bid_price),float(tick.ask_price),
                        float(tick.bid_size),float(tick.ask_size),str(tick.exchange),
                        str(tick.sale_condition),bool(tick.suspicious),bool(tick.is_fill_forward))))
                elif tick.tick_type == TickType.TRADE:
                    if bool(tick.suspicious) or bool(tick.is_fill_forward):
                        counts['flagged_trade_rejected'] += 1
                    else:
                        trades.append((at,float(tick.price),float(tick.quantity)))
                else:
                    counts['other_tick_type'] += 1
            result = quote_pair_inventory(quotes,trades,START,CUTOFF)
            result.update(source='QC_NATIVE_RAW_TICK_HISTORY', symbol=str(symbol),
                start=START.isoformat(), cutoff=CUTOFF.isoformat(), raw_rows=len(raw),
                adapter_counts=dict(counts), deployed_lean_version='NOT_RECORDED')
            print('QWCT 5.7', ticker, json.dumps(result, sort_keys=True, allow_nan=False))
        except Exception as exc:
            print('QWCT 5.7', ticker, 'HISTORY_OR_SCHEMA_UNVERIFIED',
                type(exc).__name__, str(exc)[:180], 'ORDER_FLOW_UNAVAILABLE NO_ORDERS')
    print('QWCT 5.7 END NO_SIDE_ESTIMATES NO_BOOK_RECONSTRUCTION NO_ORDERS')


run_native_quote_pair_audit()
