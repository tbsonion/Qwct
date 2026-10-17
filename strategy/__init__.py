"""QuantConnect Free-compatible shared strategy helpers.

Identical focus and screener logic to strategy/focus.py and strategy/screener.py.
No orders, invented prices, or risk-gate changes.
"""
from math import isfinite
from datetime import datetime, timedelta
from .config import StrategyConfig


def choose_focus(watchlist, decisions, preferred=""):
    eligible = []
    for symbol in watchlist:
        name = getattr(symbol, "value", symbol)
        decision = decisions.get(symbol)
        if (decision is not None and decision.accepted
                and decision.symbol == name):
            eligible.append((symbol, name, decision))
    if not eligible:
        return None
    preferred = str(preferred).strip().upper()
    for symbol, name, _ in eligible:
        if name == preferred:
            return symbol
    for symbol, _, decision in eligible:
        if decision.model == "bounce":
            return symbol
    return eligible[0][0]


def _positive(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if isfinite(n) and n > 0 else None


def select_liquid_fundamentals(
    fundamentals, cfg: StrategyConfig, max_results: int | None = None):
    """Stage 1: LEAN Fundamental universe. Uses prior-session daily fields.

    This is a candidate **prefilter**, not the 20-day-volume/ATR Gerchik
    screen. A single low-volume day CANNOT disqualify an otherwise eligible
    stock with a valid 20-day average; enforce that in stage 2 from native
    closed D1 data. Universe capacity is still capped by dollar volume.
    """
    eligible = []
    for f in fundamentals:
        price = _positive(getattr(f, "price", None))
        volume = _positive(getattr(f, "volume", None))
        dollar_volume = _positive(getattr(f, "dollar_volume", None))
        if not getattr(f, "has_fundamental_data", False):
            continue
        if (price is None or price <= cfg.min_price
                or volume is None or dollar_volume is None):
            continue
        eligible.append(f)
    # Stable order, including equally-liquid stocks across repeated runs.
    eligible.sort(key=lambda f: (
        -float(f.dollar_volume), f.symbol.value))
    limit = cfg.screener_candidate_limit
    if max_results is not None:
        if type(max_results) is not int or max_results <= 0:
            raise ValueError("native universe SEC limit must be positive integer")
        limit = min(limit, max_results)
    return [f.symbol for f in eligible[:limit]]


def passes_gerchik_screener(price, daily_atr, volume_sma, cfg: StrategyConfig) -> bool:
    """Stage 2: the original D1 eligibility rules, native indicator values.

    The SMA input must be calculated by LEAN on 20 closed D1 share volumes,
    ATR by LEAN AverageTrueRange on closed D1 TradeBars, not here.
    """
    p = _positive(price)
    a = _positive(daily_atr)
    v = _positive(volume_sma)
    return bool(p is not None and p > cfg.min_price
                and a is not None and a >= cfg.min_atr
                and v is not None and v >= cfg.min_volume)


def native_minute_coverage(bars, session_open, session_close, time_index=None):
    """Inspect real native M1 starts and identify missing 5-minute buckets.

    The expected grid is a *clock*, not fabricated OHLC data. Missing
    observations remain missing. Return only JSON-safe primitive values.
    """
    if (not isinstance(session_open, datetime)
            or not isinstance(session_close, datetime)
            or session_open.tzinfo is None or session_close.tzinfo is None
            or session_open.utcoffset() is None
            or session_close.utcoffset() is None
            or session_close <= session_open
            or (session_close-session_open).total_seconds() % 300 != 0):
        raise ValueError("INVALID_NATIVE_SESSION_WINDOW")
    total = int((session_close-session_open).total_seconds()//60)
    if total > 390:
        raise ValueError("SESSION_EXCEEDS_REGULAR_EQUITY_DAY")
    seen = set()
    invalid = []
    for bar in bars:
        try:
            start, end = bar.time, bar.end_time
            # Use caller's existing LEAN-to-ET adapter.
            if time_index is not None:
                start, end = time_index(start), time_index(end)
            start = start if isinstance(start, datetime) else None
            end = end if isinstance(end, datetime) else None
            if start is None or end is None:
                invalid.append("NATIVE_TIMESTAMP_NOT_PYTHON_DATETIME")
                continue
            if (start.tzinfo is None or end.tzinfo is None
                    or end-start != timedelta(minutes=1)
                    or start < session_open or end > session_close
                    or (start-session_open).total_seconds() % 60 != 0
                    or getattr(bar, "is_fill_forward", False)
                    or not isfinite(float(bar.volume))
                    or float(bar.volume) <= 0):
                invalid.append("INVALID_OR_FILL_FORWARD_M1")
                continue
            if start in seen:
                invalid.append("DUPLICATE_NATIVE_M1")
                continue
            seen.add(start)
        except (TypeError, ValueError, AttributeError, OverflowError):
            invalid.append("INVALID_NATIVE_M1")
    missing = [session_open+timedelta(minutes=i)
               for i in range(total)
               if session_open+timedelta(minutes=i) not in seen]
    missing_set = set(missing)
    absent_m5 = [
        session_open+timedelta(minutes=i+5)
        for i in range(0, total, 5)
        if any(session_open+timedelta(minutes=j) in missing_set
               for j in range(i, i+5))
    ]
    return {
        "expected_m1": total, "observed_valid_m1": len(seen),
        "missing_m1": [x.strftime("%H:%M") for x in missing],
        "expected_complete_m5": total//5,
        "m5_buckets_with_missing_m1": [x.strftime("%H:%M")
                                       for x in absent_m5],
        "invalid_source_rows": len(invalid),
        "source_errors": sorted(set(invalid)),
        "status": ("PASS" if not missing and not invalid else "INCOMPLETE"),
    }

