# QWCT 5.6: ONE standalone QuantBook cell; SRPT + SPY positive control.
# Historical data inventory only. No book reconstruction, CVD or orders.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from datetime import datetime, timedelta
from collections import Counter
from itertools import islice
from math import isfinite
from zoneinfo import ZoneInfo
import json
import pandas as pd

ET = ZoneInfo('America/New_York')
START = datetime(2024, 6, 3, 14, 35, tzinfo=ET)
CUTOFF = datetime(2024, 6, 3, 14, 39, 30, tzinfo=ET)
MAX_ROWS = 150000  # Per symbol; cap+1 detects incomplete enumeration.


def quote_shape(bid, ask, bid_size, ask_size):
    """Describe the raw update, not a reconstructed executable spread."""
    values = (bid, ask, bid_size, ask_size)
    if not all(isfinite(v) and v >= 0 for v in values):
        return 'INVALID'
    if bid > 0 and ask == 0:
        return 'BID_ONLY'
    if ask > 0 and bid == 0:
        return 'ASK_ONLY'
    if bid > 0 and ask > 0:
        return 'CROSSED' if bid > ask else ('LOCKED' if bid == ask else 'TWO_SIDED')
    return 'ZERO_PRICE_UPDATE'


def trade_window_summary(rows, start, cutoff):
    """Rows=(aware time, price, quantity); duplicates are NOT removed.

    No event in a second is not evidence of feed loss. This summary cannot
    certify source completeness or event-time vs receive-time latency.
    """
    if any(t.tzinfo is None or t.utcoffset() is None for t in (start, cutoff)) or cutoff <= start:
        raise ValueError('AWARE_ORDERED_WINDOW_REQUIRED')
    selected = []
    excluded = Counter()
    for at, price, qty in rows:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('AWARE_TRADE_TIME_REQUIRED')
        if not start <= at <= cutoff:
            excluded['outside_window'] += 1
        elif not all(isfinite(v) and v > 0 for v in (price, qty)):
            excluded['invalid_trade'] += 1
        else:
            selected.append((at, price, qty))
    selected.sort(key=lambda r: r[0])
    times = [r[0] for r in selected]
    seconds = {t.replace(microsecond=0) for t in times}
    anchors = [start] + times + [cutoff]
    # Four FULL minute buckets; no use of 14:39..14:40 future bar.
    volumes = [sum(q for t, p, q in selected
                   if start + timedelta(minutes=i) <= t < start + timedelta(minutes=i+1))
               for i in range(4)]
    return dict(valid_trades=len(selected), observed_volume=sum(r[2] for r in selected),
                last_trade_at=times[-1].isoformat() if times else None,
                age_at_cutoff_s=(cutoff-times[-1]).total_seconds() if times else None,
                full_minute_tick_volumes=volumes,
                seconds_with_trades=len(seconds),
                repeated_timestamps=len(times)-len(set(times)),
                max_event_silence_s=max((b-a).total_seconds() for a,b in zip(anchors,anchors[1:])),
                excluded=dict(excluded), coverage='NOT_CERTIFIED',
                availability='HISTORICAL_EVENT_TIME_ONLY_RECEIVE_TIME_UNKNOWN',
                cvd='CVD_UNAVAILABLE', classification='ORDER_FLOW_UNAVAILABLE', can_trade=False)


def audit_order_flow_data():
    qb = QuantBook()
    qb.set_time_zone('America/New_York')
    qb.set_start_date(2024, 7, 1)
    qb.set_end_date(2024, 7, 2)
    print('QWCT 5.6 HISTORICAL_DATA_AUDIT NO_ORDERS NOT_TVX_PASS')
    for ticker in ('SRPT', 'SPY'):
        try:
            symbol = qb.add_equity(ticker, Resolution.TICK, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            stream = qb.history[Tick](symbol, START.replace(tzinfo=None),
                (CUTOFF + timedelta(seconds=1)).replace(tzinfo=None),
                Resolution.TICK, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW)
            raw = list(islice(iter(stream), MAX_ROWS + 1))
            if len(raw) > MAX_ROWS:
                print('QWCT 5.6', ticker, 'ROW_CAP_EXCEEDED ORDER_FLOW_UNAVAILABLE NO_ORDERS')
                continue
            counts, shapes, exchanges, conditions = Counter(), Counter(), Counter(), Counter()
            trades, quote_times = [], []
            for tick in raw:
                stamp = pd.Timestamp(tick.time)
                at = (stamp.tz_localize(ET) if stamp.tzinfo is None else stamp.tz_convert(ET)).to_pydatetime()
                if at < START or at > CUTOFF:
                    counts['outside_window'] += 1
                    continue
                if tick.symbol != symbol:
                    counts['wrong_symbol'] += 1
                    continue
                kind = str(tick.tick_type)
                counts[kind] += 1
                exchanges[(kind, str(tick.exchange))] += 1
                conditions[(kind, str(tick.sale_condition))] += 1
                if getattr(tick, 'is_fill_forward', False):
                    counts['fill_forward_rejected'] += 1
                    continue
                if bool(tick.suspicious):
                    counts['suspicious_rejected'] += 1
                    continue
                if tick.tick_type == TickType.TRADE:
                    trades.append((at, float(tick.price), float(tick.quantity)))
                elif tick.tick_type == TickType.QUOTE:
                    shape = quote_shape(float(tick.bid_price), float(tick.ask_price),
                                        float(tick.bid_size), float(tick.ask_size))
                    shapes[shape] += 1
                    if float(tick.bid_size) == 0 or float(tick.ask_size) == 0:
                        counts['quote_zero_size_side'] += 1
                    if shape != 'INVALID':
                        quote_times.append(at)
            stats = trade_window_summary(trades, START, CUTOFF)
            stats.update(source='QC_NATIVE_HISTORY_TICK_ALGOSEEK_US_EQUITY_RAW',
                         symbol=str(symbol), start=START.isoformat(), cutoff=CUTOFF.isoformat(),
                         raw_rows=len(raw), counts=dict(counts), quote_shapes=dict(shapes),
                         last_quote_at=max(quote_times).isoformat() if quote_times else None,
                         trade_quote_timestamp_ties=len(set(t for t,p,q in trades) & set(quote_times)),
                         exchange_counts={str(k):v for k,v in exchanges.items()},
                         condition_counts={str(k):v for k,v in conditions.items()})
            # Compare filtered trades with native bar volume diagnostically.
            # QC bar-building filters differ; equality is NOT completeness proof.
            try:
                bars = list(qb.history[TradeBar](symbol, START.replace(tzinfo=None),
                    (START+timedelta(minutes=4)).replace(tzinfo=None), Resolution.MINUTE,
                    fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW))
                observed = {}
                for b in bars:
                    stamp = pd.Timestamp(b.end_time)
                    end = (stamp.tz_localize(ET) if stamp.tzinfo is None else stamp.tz_convert(ET)).to_pydatetime()
                    if (b.symbol == symbol and not b.is_fill_forward and
                            START < end <= START+timedelta(minutes=4) and
                            b.period == timedelta(minutes=1)):
                        key = end.isoformat()
                        if key in observed:
                            raise ValueError('DUPLICATE_MINUTE_END')
                        observed[key] = float(b.volume)
                expected = [(START+timedelta(minutes=i+1)).isoformat() for i in range(4)]
                stats['native_full_minute_volumes'] = [observed.get(k) for k in expected]
                stats['tick_minus_native_minute'] = [None if observed.get(k) is None else
                    stats['full_minute_tick_volumes'][i]-observed[k] for i,k in enumerate(expected)]
            except Exception as exc:
                stats['minute_comparison_error'] = type(exc).__name__ + ': ' + str(exc)[:160]
            print('QWCT 5.6', ticker, json.dumps(stats, sort_keys=True, allow_nan=False))
        except Exception as exc:
            print('QWCT 5.6', ticker, 'HISTORY_OR_ENTITLEMENT_UNVERIFIED',
                  type(exc).__name__, str(exc)[:180], 'ORDER_FLOW_UNAVAILABLE NO_ORDERS')
    print('QWCT 5.6 END NO_CVD NO_BOOK_RECONSTRUCTION NO_RELAXED_SEC_GATE NO_ORDERS')


audit_order_flow_data()
