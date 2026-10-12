"""Native LEAN TradeBar SECOND -> Gerchik TVX preclose observation.

Consumes real, completed one-second TradeBars from an existing LEAN
subscription. NOT a second-bar generator, feed, 5m consolidator, execution
model, or fill simulation. A read-only sample requires every one of the
270 completed second bars in BPU2 BEFORE its -30s cutoff. Missing trade
seconds (fill_forward=False) intentionally fail closed rather than
pretend a synthetic uninterrupted source.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from .native_m5_validation import _duration_seconds

SECOND = timedelta(seconds=1)
BPU2_LENGTH = timedelta(minutes=5)
PRECLOSE_GAP = timedelta(seconds=30)
OBSERVED_SECONDS = 270


@dataclass(frozen=True)
class NativePrecloseSample:
    observed_at: datetime
    observed_since: datetime
    bpu2_end: datetime
    observed_low: float
    observed_high: float
    last_price: float
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
        self.low = None
        self.high = None
        self.last_price = None
        self.blocked_reason = ""
        self.complete = False

    def accept(self, bar, *, symbol=None) -> NativePrecloseSample | None:
        """Accept one native one-second TradeBar. Never read future M5 data."""
        if self.complete or self.blocked_reason:
            return None
        try:
            start, end = bar.time, bar.end_time
            if (not isinstance(end, datetime) or end.tzinfo is None
                    or end.utcoffset() is None):
                raise ValueError("SEC_END_UNVERIFIED")
            if symbol is not None and bar.symbol != symbol:
                raise ValueError("SEC_SYMBOL_MISMATCH")
            if _duration_seconds(bar.period) != 1 or (
                    _duration_seconds(end - start) != 1):
                raise ValueError("SEC_NATIVE_PERIOD_INVALID")
            if end <= self.bpu1_end or end > self.cutoff:
                raise ValueError("SEC_OUTSIDE_BPU2_PRECLOSE_WINDOW")
            if end != self.last_at + SECOND:
                raise ValueError("SEC_MISSING_DUPLICATE_OR_LATE_SECOND")
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
        self.count += 1
        self.low = lo if self.low is None else min(self.low, lo)
        self.high = hi if self.high is None else max(self.high, hi)
        self.last_price = close
        if end != self.cutoff:
            return None
        if self.count != OBSERVED_SECONDS:
            self.blocked_reason = "SEC_PRECLOSE_INCOMPLETE"
            return None
        self.complete = True
        return NativePrecloseSample(
            observed_at=end, observed_since=self.bpu1_end,
            bpu2_end=self.bpu2_end, observed_low=self.low,
            observed_high=self.high, last_price=self.last_price)
