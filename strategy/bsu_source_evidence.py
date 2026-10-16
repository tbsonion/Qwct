"""As-of RAW D1 evidence for historical BSU source-price candidates.

Research-only. No author BSU approval, re-anchoring, M5, orders or fills.
Uses the existing confirmed swing detector and existing 3.3 mirror trace.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite

import pandas as pd

from .levels import _confirmed_swings


@dataclass(frozen=True)
class BsuSourceEvidence:
    label: str
    source_date: date
    confirmed_date: date
    price: float
    current_grid: str
    original_same_wick_dates: tuple
    mirror_exact_wick_dates: tuple
    mirror_pierce_dates: tuple
    status: str = "AUTHOR_UNVERIFIED"

    @property
    def can_trade(self):
        return False


def _close_enough(a, b, tick):
    # Same floating-point guard as BsuDetector; NOT an adjustable ATR tolerance.
    return abs(a - b) <= tick * (0.5 + 1e-7)


def _on_current_grid(price, tick):
    # Current grid is diagnostic, not authoritative for historic rebased prices.
    return abs(price / tick - round(price / tick)) <= 1e-5


def frozen_mirror_source_evidence(d1_asof, level, trace, *, session, tick_size, swing_k):
    """Inspect confirmed FIRST/LAST RAW swing prices, no future M5.

    Inputs must be existing native closed RAW D1 bars, a native-created Level,
    and a 3.3 trace with PROXY_VERIFIED. Exact D1 wicks are observations,
    never a Gerchik-approved fixed BSU, BPU1 or executable signal.
    """
    if not isinstance(session, date) or isinstance(session, pd.Timestamp):
        raise ValueError("SESSION_DATE_REQUIRED")
    if not isinstance(swing_k, int) or isinstance(swing_k, bool) or swing_k < 1:
        raise ValueError("INVALID_SWING_K")
    try:
        tick = float(tick_size)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_NATIVE_TICK") from exc
    if not isfinite(tick) or tick <= 0:
        raise ValueError("INVALID_NATIVE_TICK")
    if not isinstance(d1_asof, pd.DataFrame) or not isinstance(d1_asof.index, pd.DatetimeIndex):
        raise ValueError("INVALID_RAW_D1_FRAME")
    if (d1_asof.index.tz is None or d1_asof.empty or
            not d1_asof.index.is_unique or not d1_asof.index.is_monotonic_increasing):
        raise ValueError("INVALID_NATIVE_D1_INDEX")
    dates = [stamp.date() for stamp in d1_asof.index]
    if any(d >= session for d in dates) or any(x >= y for x, y in zip(dates, dates[1:])):
        raise ValueError("NONCAUSAL_OR_DUPLICATE_D1_DATE")
    for field in ("open", "high", "low", "close"):
        if field not in d1_asof:
            raise ValueError("MISSING_RAW_D1_OHLC")
        if not pd.to_numeric(d1_asof[field], errors="coerce").map(isfinite).all():
            raise ValueError("INVALID_RAW_D1_OHLC")
    bars = d1_asof[["open", "high", "low", "close"]].astype(float)
    if ((bars.min(axis=1) <= 0).any()
            or (bars.high < bars[["open", "close", "low"]].max(axis=1)).any()
            or (bars.low > bars[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("INVALID_RAW_D1_OHLC_SHAPE")
    if (not isinstance(trace, dict) or trace.get("status") != "PROXY_VERIFIED"
            or trace.get("original_kind") not in ("resistance", "support")):
        raise ValueError("MIRROR_CHRONOLOGY_NOT_VERIFIED")
    if getattr(level, "kind", None) != "mirror" or getattr(level, "source", None) != "swing_cluster":
        raise ValueError("NOT_EXISTING_SWING_MIRROR")
    if (not isinstance(level.valid_from, date) or level.valid_from > session or
            str(level.valid_from) != trace.get("valid_from")):
        raise ValueError("MIRROR_NOT_FROZEN_AS_OF_SESSION")
    first, last = level.first_idx, level.last_idx
    if (not all(isinstance(n, int) and not isinstance(n, bool) for n in (first, last))
            or not swing_k <= first < last or last + swing_k >= len(bars)):
        raise ValueError("SWING_SOURCE_NOT_CONFIRMED")
    if not isfinite(float(level.price)) or float(level.price) <= 0:
        raise ValueError("BAD_SOFTWARE_LEVEL_PRICE")

    original = trace["original_kind"]
    original_field, mirror_field = (("high", "low") if original == "resistance"
                                    else ("low", "high"))
    confirmed = _confirmed_swings(d1_asof, swing_k)[0 if original == "resistance" else 1]
    valid_swings = {i: (float(price), confirmed_on) for i, price, confirmed_on in confirmed}
    evidence = []
    for label, idx in (("FIRST_SWING", first), ("LAST_SWING", last)):
        if idx not in valid_swings:
            raise ValueError("SOURCE_IS_NOT_CONFIRMED_SWING")
        p = float(bars.iloc[idx][original_field])
        verified_price, confirmed_on = valid_swings[idx]
        if abs(p - verified_price) > max(abs(p), 1.0) * 1e-12:
            raise ValueError("SOURCE_PRICE_MISMATCH")
        if confirmed_on >= session or confirmed_on >= level.valid_from:
            raise ValueError("SOURCE_CONFIRMED_AFTER_LEVEL_IS_VALID")
        # A historical pivot must be confirmed BEFORE it can be reinforced.
        # We do not count its own bar as a second touch.
        from_idx = idx + swing_k + 1
        same, mirror_exact, mirror_pierced = [], [], []
        on_grid = _on_current_grid(p, tick)
        for j in range(from_idx, len(bars)):
            v = float(bars.iloc[j][original_field])
            if on_grid and _close_enough(v, p, tick):
                same.append(dates[j])
            if dates[j] < level.valid_from:
                continue
            new_wick = float(bars.iloc[j][mirror_field])
            if on_grid and _close_enough(new_wick, p, tick):
                mirror_exact.append(dates[j])
            if (new_wick < p - tick * (0.5 + 1e-7) if original == "resistance"
                    else new_wick > p + tick * (0.5 + 1e-7)):
                mirror_pierced.append(dates[j])
        evidence.append(BsuSourceEvidence(
            label=label, source_date=dates[idx], confirmed_date=confirmed_on,
            price=p, current_grid="ON_GRID" if on_grid else "OFF_GRID",
            original_same_wick_dates=tuple(same),
            mirror_exact_wick_dates=tuple(mirror_exact),
            mirror_pierce_dates=tuple(mirror_pierced)))
    return tuple(evidence)
