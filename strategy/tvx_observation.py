"""Proof-driven, read-only SEC BPU2 30-second TVX research adapter.

Requires the caller to deliver ORIGINAL completed native 1-second US-equity
TradeBars with fill_forward disabled and positive traded volume. It is
NOT wired to Qwct Cloud's minute-resolution stock universe. No SEC/TICK
prices are interpolated, backfilled or synthesized from M5 candles.
"""
from datetime import datetime, timedelta
from math import isfinite

from .patterns_bsu import Bar, BsuDetector

_ONE = timedelta(seconds=1)
_FIVE = timedelta(minutes=5)
_PRE = timedelta(seconds=30)


class NativeSecondTvxWindow:
    """One BPU1 -> BPU2 preclose research window, never trade authority.

    Each second must have its original native 1s TradeBar. For liquid
    symbols, missing trade seconds are common; this strict prototype
    rejects a gap rather than guessing a candle. It intentionally does
    not falsely infer completeness from a sparse or fill-forward feed.
    """

    def __init__(self, detector: BsuDetector):
        if not isinstance(detector, BsuDetector):
            raise TypeError("native BsuDetector required")
        st = detector.state
        if st.phase != "bpu1" or st.bpu1_ts is None or detector._period != _FIVE:
            raise ValueError("native closed M5 BPU1 required before SEC study")
        if st.bpu1_ts.tzinfo is None or st.bpu1_ts.utcoffset() is None:
            raise ValueError("BPU1 must be timezone-aware")
        self.detector = detector
        self.start = st.bpu1_ts
        self.bpu2_end = self.start + _FIVE
        self.target = self.bpu2_end - _PRE
        self.count = 0
        self.high = None
        self.low = None
        self.last_price = None
        self.done = False

    def on_second(self, bar: Bar):
        if self.done:
            raise ValueError("preclose window already consumed")
        if self.detector.state.phase != "bpu1":
            raise ValueError("BPU1 no longer active; SEC observation invalid")
        if not isinstance(bar, Bar) or bar.timeframe != "SEC":
            raise ValueError("original completed native SEC TradeBar required")
        timestamp = bar.ts
        if (not isinstance(timestamp, datetime) or timestamp.tzinfo is None
                or timestamp.utcoffset() is None):
            raise ValueError("native SEC end timestamp must be aware")
        expected = self.start + _ONE * (self.count + 1)
        if timestamp != expected:
            raise ValueError("missing, duplicate or out-of-order SEC gap")
        if timestamp > self.target:
            raise ValueError("cannot infer preclose from post-target observation")
        try:
            o, h, lo, cl, vol = (float(v) for v in (
                bar.open, bar.high, bar.low, bar.close, bar.volume))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("native SEC OHLCV invalid") from None
        if (not all(isfinite(v) for v in (o, h, lo, cl, vol))
                or min(o, h, lo, cl) <= 0
                or h < max(o, cl, lo) or lo > min(o, cl, h)):
            raise ValueError("invalid native SEC OHLC shape")
        if vol <= 0:
            raise ValueError("SEC native non-fill-forward positive trade volume required")
        self.count += 1
        self.high = max(self.high, h) if self.high is not None else h
        self.low = min(self.low, lo) if self.low is not None else lo
        self.last_price = cl
        if timestamp == self.target:
            if self.count != 270:
                raise ValueError("insufficient native SEC observations")
            self.done = True
            return self.detector.observe_preclose(
                observed_at=timestamp, bpu2_end=self.bpu2_end,
                observed_low=self.low, observed_high=self.high,
                last_price=cl, source="SEC", observed_since=self.start)
        return self.detector.state
