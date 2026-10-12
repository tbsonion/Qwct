"""Native LEAN TradeBar SECOND -> Gerchik TVX preclose observation.

Consumes real, completed one-second TradeBars from an existing LEAN
subscription. NOT a second-bar generator, feed, 5m consolidator, execution
model, or fill simulation. A read-only sample requires every one of the
observed traded-second bars in BPU2 BEFORE its -30s cutoff.
LEAN may omit a one-second bar when no price-setting trade occurred.
Never fill gaps with synthetic bars; bound unobserved stretches to
10 seconds and require a real traded bar ending EXACTLY at -30s.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from .native_m5_validation import _duration_seconds

SECOND = timedelta(seconds=1)
BPU2_LENGTH = timedelta(minutes=5)
PRECLOSE_GAP = timedelta(seconds=30)
MAX_SECONDS = 270
MAX_UNOBSERVED_GAP = timedelta(seconds=10)


@dataclass(frozen=True)
class NativePrecloseSample:
    observed_at: datetime
    observed_since: datetime
    bpu2_end: datetime
    observed_low: float
    observed_high: float
    last_price: float
    observed_bars: int = 0
    unobserved_seconds: int = 0
    source: str = "SEC"
    can_submit: bool = False


class NativeSecondTvxWindow:
    """One BPU1-relative, fail-closed contiguous SEC observation window."""

    def __init__(self, bpu1_end: datetime):
        if (not isinstance(bpu1_end, datetime) or bpu1_end.tzinfo is None
                or bpu1_end.utcoffset() is None
                or bpu1_end.second or bpu1_end.microsecond
                or bpu1_end.minute % 5):
            raise ValueError("native BPU1 end must be aligned, timezone-aware M5")
        self.bpu1_end = bpu1_end
        self.bpu2_end = bpu1_end + BPU2_LENGTH
        self.cutoff = self.bpu2_end - PRECLOSE_GAP
        self.last_at = bpu1_end
        self.count = 0
        self.unobserved_seconds = 0
        self.low = None
        self.high = None
        self.last_price = None
        self.blocked_reason = ""
        self.complete = False

    def accept(self, bar, *, symbol=None,
               end_at=None) -> NativePrecloseSample | None:
        """Accept one native one-second TradeBar. Never read future M5 data."""
        if self.complete or self.blocked_reason:
            return None
        try:
            # Native PythonNet DateTime values can be .NET objects.
            # LEAN adapter uses the SAME exchange-local conversion as M5
            # instead of assuming end_time is a Python datetime.
            start, native_end = bar.time, bar.end_time
            end = native_end if end_at is None else end_at
            if (not isinstance(end, datetime) or end.tzinfo is None
                    or end.utcoffset() is None):
                raise ValueError("SEC_END_UNVERIFIED")
            if symbol is not None and bar.symbol != symbol:
                raise ValueError("SEC_SYMBOL_MISMATCH")
            if _duration_seconds(bar.period) != 1 or (
                    _duration_seconds(native_end - start) != 1):
                raise ValueError("SEC_NATIVE_PERIOD_INVALID")
            if end <= self.bpu1_end or end > self.cutoff:
                raise ValueError("SEC_OUTSIDE_BPU2_PRECLOSE_WINDOW")
            gap = end - self.last_at
            if gap <= timedelta(0):
                raise ValueError("SEC_DUPLICATE_OR_LATE_SECOND")
            if gap > MAX_UNOBSERVED_GAP:
                raise ValueError("SEC_UNOBSERVED_GAP_OVER_10S")
            if getattr(bar, "is_fill_forward", False):
                raise ValueError("SEC_FILL_FORWARD")
            o, hi, lo, close, vol = (
                float(bar.open), float(bar.high), float(bar.low),
                float(bar.close), float(bar.volume))
            if (not all(isfinite(x) for x in (o, hi, lo, close, vol))
                    or min(o, hi, lo, close) <= 0
                    or hi < max(o, lo, close) or lo > min(o, hi, close)
                    or vol <= 0):
                raise ValueError("SEC_OHLCV_UNVERIFIED")
        except (TypeError, ValueError, AttributeError, OverflowError) as exc:
            self.blocked_reason = str(exc)[:140] or "SEC_UNKNOWN_DATA_ERROR"
            return None

        self.last_at = end
        self.unobserved_seconds += int(gap.total_seconds()) - 1
        self.count += 1
        self.low = lo if self.low is None else min(self.low, lo)
        self.high = hi if self.high is None else max(self.high, hi)
        self.last_price = close
        if end != self.cutoff:
            return None
        if self.count + self.unobserved_seconds != MAX_SECONDS:
            self.blocked_reason = "SEC_PRECLOSE_CHRONOLOGY_MISMATCH"
            return None
        self.complete = True
        return NativePrecloseSample(
            observed_at=end, observed_since=self.bpu1_end,
            bpu2_end=self.bpu2_end, observed_low=self.low,
            observed_high=self.high, last_price=self.last_price,
            observed_bars=self.count,
            unobserved_seconds=self.unobserved_seconds)
