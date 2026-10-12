"""Pure Gerchik screener rules; LEAN owns universe data and indicators.

This module never downloads quotes, computes ATR/SMA, or submits orders.
"""
from math import isfinite

from .config import StrategyConfig


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
