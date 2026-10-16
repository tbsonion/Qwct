# QWCT 4.9 — SRPT historical native TRADE / QUOTE ticks near BPU2 -30s.
# ONE isolated QuantConnect research.ipynb code cell. NO orders.
# This checks whether a genuinely observed tick or bid/ask was available
# at/as-of 14:39:30 ET. It does NOT synthesize a missing SECOND bar,
# relax the 10-second QWCT 4.8 gate, or prove timely OnData delivery.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from math import isfinite
import pandas as pd

ET = ZoneInfo("America/New_York")
DAY = datetime(2024, 6, 3)
CUTOFF = datetime(2024, 6, 3, 14, 39, 30, tzinfo=ET)
WINDOW_START = CUTOFF - timedelta(seconds=30)
MAX_TICKS = 25000  # Fail closed rather than silently truncate history.

def _et(ts):
    p = pd.Timestamp(ts)
    return p.tz_localize(ET) if p.tzinfo is None else p.tz_convert(ET)

def _age_seconds(ts):
    return round((CUTOFF - ts).total_seconds(), 4)

def audit_native_tick_asof():
    print("QWCT 4.9 TICK START SRPT",
          "WINDOW=14:39:00..14:39:30 ET",
          "CUT_OFF=2024-06-03 14:39:30 ET",
          "HISTORICAL_NOT_ONDATA NO_ORDERS")
    qb = QuantBook()
    qb.set_time_zone("America/New_York")
    qb.set_start_date(2024, 7, 1)
    qb.set_end_date(2024, 7, 2)
    symbol = qb.add_equity(
        "SRPT", Resolution.TICK, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW).symbol
    try:
        native = list(qb.history[Tick](
            symbol,
            WINDOW_START.replace(tzinfo=None),
            (CUTOFF + timedelta(seconds=1)).replace(tzinfo=None),
            Resolution.TICK, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW))
    except (Exception) as exc:
        print("QWCT 4.9 TICK_UNAVAILABLE",
              type(exc).__name__, str(exc)[:180],
              "DATA_ENTITLEMENT_OR_HISTORY_UNVERIFIED NO_ORDERS")
        return
    if len(native) > MAX_TICKS:
        print("QWCT 4.9 TICK_BLOCKED TOO_MANY_TICKS",
              len(native), "NO_ORDERS")
        return
    trades = []
    quotes = []
    future_excluded = 0
    before_excluded = 0
    other = 0
    invalid = 0
    for x in native:
        at = _et(x.time).to_pydatetime()  # NATIVE tick timestamp, not rounded
        if at > CUTOFF:
            future_excluded += 1
            continue
        if at < WINDOW_START:
            before_excluded += 1
            continue
        if getattr(x, "symbol", None) != symbol:
            invalid += 1
            continue
        if getattr(x, "tick_type", None) == TickType.TRADE:
            price = float(x.price)
            qty = float(x.quantity)
            if (not isfinite(price) or not isfinite(qty)
                    or price <= 0 or qty <= 0):
                invalid += 1
                continue
            trades.append((at, price, qty))
        elif getattr(x, "tick_type", None) == TickType.QUOTE:
            bid = float(x.bid_price)
            ask = float(x.ask_price)
            bs = float(x.bid_size)
            ass = float(x.ask_size)
            # A tradable two-sided quote requires positive sides and sizes.
            if (not all(isfinite(v) for v in (bid,ask,bs,ass))
                    or bid <= 0 or ask <= 0 or bs <= 0 or ass <= 0
                    or bid > ask):
                invalid += 1
                continue
            quotes.append((at, bid, ask, bs, ass))
        else:
            other += 1
    trades.sort(key=lambda row: row[0])
    quotes.sort(key=lambda row: row[0])
    print("QWCT 4.9 TICK COVERAGE", "raw=", len(native),
          "valid_trades=", len(trades), "two_sided_quotes=", len(quotes),
          "future_excluded=", future_excluded,
          "before_excluded=", before_excluded,
          "invalid=", invalid, "other=", other)
    if trades:
        at, price, qty = trades[-1]
        print("QWCT 4.9 LAST_NATIVE_TRADE",
              "observed_at=", at, "age_at_cutoff_s=", _age_seconds(at),
              "raw_price=", price, "last_qty=", qty,
              "exact_cutoff_tick=", at == CUTOFF)
    else:
        print("QWCT 4.9 LAST_NATIVE_TRADE NONE")
    if quotes:
        at, bid, ask, bs, ass = quotes[-1]
        print("QWCT 4.9 LAST_TWO_SIDED_QUOTE",
              "observed_at=", at, "age_at_cutoff_s=", _age_seconds(at),
              "bid=", bid, "ask=", ask,
              "spread=", round(ask-bid, 4),
              "bid_size=", bs, "ask_size=", ass,
              "exact_cutoff_tick=", at == CUTOFF)
    else:
        print("QWCT 4.9 LAST_TWO_SIDED_QUOTE NONE")
    print("QWCT 4.9 VERDICT", 
          "HISTORICAL_TICKS_ONLY",
          "NOT_TVX_PASS",
          "NO_SYNTHETIC_CUTOFF",
          "NO_RELAXED_SEC_GAP",
          "ONDATA_TIMELINESS_UNKNOWN",
          "AUTHOR_BSU_UNVERIFIED NO_ORDERS")

audit_native_tick_asof()
