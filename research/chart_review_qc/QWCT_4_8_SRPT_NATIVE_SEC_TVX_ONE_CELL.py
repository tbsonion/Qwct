# QWCT 4.8 — SRPT June 3, 2024: real historical SECOND bars at BPU2 -30s.
# ONE self-contained QuantBook research.ipynb CODE CELL. Read-only, no orders.
# Keep the existing QWCT 4.3 M5 notebook and main.py unchanged.
#
# Exact canonical NativeSecondTvxWindow below is embedded from
# strategy/native_second_tvx.py (same source, no missing small-project modules).
# A historical QuantBook replay CANNOT prove on_data callback timeliness;
# a future separate SEC-on_data backtest is still required for that.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from math import isfinite
import pandas as pd
from strategy.config import StrategyConfig
from strategy.patterns_bsu import Bar, BsuDetector

ET = ZoneInfo("America/New_York")
DAY = datetime(2024, 6, 3)
SOURCE = datetime(2024, 6, 3, 14, 15, tzinfo=ET)
BPU1_END = datetime(2024, 6, 3, 14, 35, tzinfo=ET)
BPU2_END = datetime(2024, 6, 3, 14, 40, tzinfo=ET)
CUTOFF = BPU2_END - timedelta(seconds=30)
SOURCE_PRICE = 123.87
SIDE = "long"

def _et(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)

# Native period helper copied without semantic changes from
# strategy/native_m5_validation.py.
def _duration_seconds(value):
    """Accept native Python timedelta and pythonnet System.TimeSpan."""
    if value is None:
        return None
    total = getattr(value, "total_seconds", None)
    if total is None:
        total = getattr(value, "TotalSeconds", None)
    if total is None:
        return None
    return float(total() if callable(total) else total)


# Native one-second provenance / gap checker copied without semantic
# changes from strategy/native_second_tvx.py.
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
            # When native LEAN time is already an aware Python datetime,
            # the adapter cannot override its actual end with a different
            # timestamp and thereby manufacture the exact -30s cutoff.
            if (isinstance(native_end, datetime)
                    and native_end.tzinfo is not None
                    and native_end.utcoffset() is not None
                    and native_end != end):
                raise ValueError("SEC_ADAPTER_END_MISMATCH")
            if end.microsecond:
                raise ValueError("SEC_END_NOT_ALIGNED_TO_SECOND")
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


def srpt_sec_preclose_audit():
    print("QWCT 4.8 START SRPT 2024-06-03 BPU1=14:35:00 CUTOFF=14:39:30",
          "BPU2_END=14:40:00 HISTORICAL_READ_ONLY NO_ORDERS")
    qb = QuantBook()
    qb.set_time_zone("America/New_York")
    qb.set_start_date(2024, 7, 1)
    qb.set_end_date(2024, 7, 2)
    equity = qb.add_equity(
        "SRPT", Resolution.SECOND, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW)
    symbol = equity.symbol
    tick = float(qb.securities[symbol].symbol_properties.minimum_price_variation)
    if not isfinite(tick) or tick <= 0:
        raise ValueError("NO_NATIVE_MINIMUM_PRICE_VARIATION")
    cfg = StrategyConfig()

    # Recalculate the same prior-session RAW native Wilder ATR as QWCT 4.3.
    raw_days = list(qb.history[TradeBar](
        symbol, DAY - timedelta(days=335), DAY, Resolution.DAILY,
        fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    raw_days = [x for x in raw_days if _et(x.time).date() < DAY.date()
                and not getattr(x, "is_fill_forward", False)]
    if len(raw_days) < 180:
        raise ValueError(f"D1_FAIL_CLOSED only {len(raw_days)} observed D1")
    atr = AverageTrueRange(cfg.atr_period, MovingAverageType.WILDERS)
    for day in raw_days[-180:]:
        atr.update(day)
    if not atr.is_ready or not isfinite(float(atr.current.value)):
        raise ValueError("D1_ATR_NOT_READY")

    # Independently reconstruct ALREADY CLOSED 14:35 BPU1 from its five
    # actual one-minute trades using LEAN's native TradeBarConsolidator.
    minutes = list(qb.history[TradeBar](
        symbol, DAY.replace(hour=14, minute=30),
        DAY.replace(hour=14, minute=36), Resolution.MINUTE,
        fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW))
    expected = [BPU1_END - timedelta(minutes=i) for i in range(4, -1, -1)]
    minute_by_end = {}
    for x in minutes:
        end = _et(x.end_time).to_pydatetime()
        if end not in expected:
            continue
        if (x.symbol != symbol or getattr(x, "is_fill_forward", False)
                or _duration_seconds(x.period) != 60
                or _duration_seconds(x.end_time - x.time) != 60
                or float(x.volume) <= 0 or end in minute_by_end):
            raise ValueError("BPU1_NATIVE_MINUTE_UNVERIFIED")
        minute_by_end[end] = x
    if len(minute_by_end) != 5 or any(t not in minute_by_end for t in expected):
        raise ValueError("BPU1_MISSING_NATIVE_MINUTES_FAIL_CLOSED")
    m5_bars = []
    consolidator = TradeBarConsolidator(timedelta(minutes=5))
    consolidator.data_consolidated += lambda sender, bar: m5_bars.append(bar)
    for t in expected:
        consolidator.update(minute_by_end[t])
    consolidator.scan(DAY.replace(hour=14, minute=36))
    matching = [x for x in m5_bars
                if _et(x.end_time).to_pydatetime() == BPU1_END]
    if len(matching) != 1:
        raise ValueError("BPU1_NATIVE_M5_CONSOLIDATION_FAIL_CLOSED")
    native_bpu1 = matching[0]
    if (float(native_bpu1.volume) <= 0
            or _duration_seconds(native_bpu1.period) != 300
            or _duration_seconds(native_bpu1.end_time-native_bpu1.time) != 300):
        raise ValueError("BPU1_M5_NATIVE_SHAPE_INVALID")
    bpu1 = Bar(BPU1_END, float(native_bpu1.open),
               float(native_bpu1.high), float(native_bpu1.low),
               float(native_bpu1.close), "M5", float(native_bpu1.volume))
    if abs(bpu1.low - SOURCE_PRICE) > tick * (0.5 + 1e-7):
        raise ValueError("BPU1_NOT_EXACT_12387_STOP")

    d = BsuDetector(cfg, SOURCE_PRICE, SIDE,
                    atr_value=float(atr.current.value),
                    tick_size=tick, bsu_ts=SOURCE)
    if d.on_bar(bpu1).phase != "bpu1":
        raise ValueError("BPU1_BSU_SOURCE_STATE_FAIL_CLOSED")
    print("QWCT 4.8 BPU1_NATIVE", "LOW=", bpu1.low, "STOP=",
          d.state.stop_price, "LUFT=", round(d.state.luft, 5),
          "SOURCE=EARLIER_QWCT_4.3_M5_REPLAY AUTHOR_UNVERIFIED")

    # Query only the short native SECOND interval around the cutoff.
    # The +1s is solely for History's end-exclusive start-time boundary.
    # Every bar ending later than CUTOFF is ignored BEFORE ANY evaluation.
    sec_bars = list(qb.history[TradeBar](
        symbol, BPU1_END.replace(tzinfo=None),
        (CUTOFF + timedelta(seconds=1)).replace(tzinfo=None),
        Resolution.SECOND, fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW))
    win = NativeSecondTvxWindow(BPU1_END)
    raw_received = len(sec_bars)
    sample = None
    for x in sec_bars:
        end = _et(x.end_time).to_pydatetime()
        if end <= BPU1_END or end > CUTOFF:
            continue  # no future BPU2 bar, not even its last 30 seconds
        sample = win.accept(x, symbol=symbol, end_at=end)
        if win.blocked_reason or sample is not None:
            break
    if sample is None:
        why = (win.blocked_reason or
               ("SEC_NO_NATIVE_BARS" if raw_received == 0
                else "SEC_PRECLOSE_CUTOFF_NOT_OBSERVED"))
        print("QWCT 4.8 TVX_SEC_BLOCKED", why,
              f"history_rows={raw_received}",
              f"accepted_traded_seconds={win.count}",
              f"unobserved_seconds={win.unobserved_seconds}",
              "NO_INFERRED_SEC NO_ORDERS")
        return
    if sample.observed_at != CUTOFF or sample.bpu2_end != BPU2_END:
        raise ValueError("NATIVE_SEC_PRE_CLOSE_TIMESTAMP_MISMATCH")
    print("QWCT 4.8 TVX_SEC_SAMPLE",
          "OBSERVED_AT=", sample.observed_at,
          "TRADED_1S=", sample.observed_bars,
          "UNOBSERVED_1S=", sample.unobserved_seconds,
          "RANGE=", (sample.observed_low, sample.observed_high),
          "LAST_TRADE=", sample.last_price,
          "RAW_NATIVE_HISTORICAL_NO_FILLS")
    status = d.observe_preclose(
        observed_at=sample.observed_at, bpu2_end=sample.bpu2_end,
        observed_low=sample.observed_low,
        observed_high=sample.observed_high,
        last_price=sample.last_price,
        source=sample.source, observed_since=sample.observed_since)
    if status.phase != "preclose_candidate":
        print("QWCT 4.8 TVX_SEC_INVALIDATED", status.reason,
              "HISTORICAL_ONLY NO_ORDERS")
        return
    print("QWCT 4.8 TVX_SEC_PRE_CLOSE", "PASS_PROVISIONAL",
          "EXACT_CUTOFF=", sample.observed_at,
          "ENTRY_THEORETICAL=", status.entry_price,
          "STOP=", status.stop_price, "LUFT=", status.luft,
          "NO_CLOSED_BPU2_USED",
          "ONDATA_DELIVERY_TIMELINESS_UNVERIFIED",
          "AUTHOR_BSU_UNKNOWN NO_ORDERS")

srpt_sec_preclose_audit()
