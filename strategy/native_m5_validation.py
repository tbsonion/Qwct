"""Validate already-received native consolidated M5 price evidence.

No homemade data feed/indicators. Never infer an executed trade or an
actual price touch from a zero-volume/fill-forward candle. This is a
conservative research admission policy, NOT proof of native data provenance.
"""
from datetime import datetime
from math import isfinite


def validate_m5_tradebar(bar, end_at: datetime) -> tuple[bool, str]:
    """Return (usable_for_pattern_research, reason) without substituting data.

    end_at must be the timestamp supplied by LEAN's actual completed M5
    consolidator and converted to its configured exchange time zone.
    """
    if (not isinstance(end_at, datetime) or end_at.tzinfo is None
            or end_at.utcoffset() is None):
        return False, "M5_END_TIMESTAMP_UNVERIFIED"
    if (end_at.second != 0 or end_at.microsecond != 0
            or end_at.minute % 5 != 0):
        return False, "M5_PERIOD_BOUNDARY_INVALID"
    # Official LEAN TradeBar has start Time, EndTime and Period.
    # An observed native M1 bar can also end at 09:35. The clock
    # boundary alone is NOT evidence of an aggregated 5-minute bar.
    # Strict validation needs both the declared Period and actual span.
    try:
        period = getattr(bar, "period", None)
        if period is None:
            return False, "M5_SOURCE_PERIOD_MISSING"
        seconds = float(period.total_seconds())
        if not isfinite(seconds) or seconds != 300:
            return False, "M5_SOURCE_PERIOD_NOT_FIVE_MINUTES"
        source_start = getattr(bar, "time")
        source_end = getattr(bar, "end_time")
        actual_seconds = float((source_end - source_start).total_seconds())
        if not isfinite(actual_seconds) or actual_seconds != 300:
            return False, "M5_SOURCE_START_END_INCONSISTENT"
    except (AttributeError, ValueError, TypeError, OverflowError):
        return False, "M5_SOURCE_PERIOD_OR_CHRONOLOGY_UNVERIFIED"
    try:
        o, h, lo, c, volume = (float(v) for v in (
            bar.open, bar.high, bar.low, bar.close, bar.volume))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False, "M5_OHLCV_NOT_NUMERIC"
    if not all(isfinite(v) for v in (o, h, lo, c, volume)):
        return False, "M5_OHLCV_NOT_FINITE"
    if min(o, h, lo, c) <= 0 or h < max(o, c, lo) or lo > min(o, c, h):
        return False, "M5_OHLC_INVALID"
    if volume <= 0:
        # Without observed trade volume, no genuine BPU level touch or
        # breakout can be inferred. A volume-zero bar is not replaced.
        return False, "M5_NO_OBSERVED_TRADES"
    if getattr(bar, "is_fill_forward", False):
        return False, "M5_FILL_FORWARD_UNVERIFIED"
    return True, "M5_NATIVE_VALIDATED_SHAPE"
