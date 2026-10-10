"""Read-only BSU / BPU1 / BPU2 / TVX evidence, no trading or fake fills.

Normative pattern: https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya

The source says the originating BSU bar may be historical; BPU1 exactly
touches its level but need not follow BSU immediately; BPU2 directly follows
BPU1, does not break BPU1's extreme, and may miss the level by at most 20%
of stop distance (luft). The TVX limit order is placed about **30 seconds
BEFORE BPU2 CLOSE**. A closed M1/M5 bar cannot recreate that observation.

This independent research detector consumes ALREADY AVAILABLE OHLC bars and
optional exact-timestamp subminute preclose observations. It does NOT build
a market-data feed, fabricate intrabar data, submit orders, infer fills, or
manage portfolio/broker state. It is not wired into the live Qwct main.py.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite

from .config import StrategyConfig


_BAR_PERIODS = {
    "SEC": timedelta(seconds=1),
    "M1": timedelta(minutes=1),
    "M5": timedelta(minutes=5),
}
_PRE_CLOSE_SOURCES = ("SEC", "TICK")


def _positive(name: str, value: float) -> float:
    try:
        parsed = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{name} must be a positive finite number") from None
    if not isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return parsed


def _aware(name: str, value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or (
            value.utcoffset() is None):
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Bar:
    """One already CLOSED OHLC bar; ts is the native bar's END time.

    M5 and M1 are closed time-period bars. SEC is a completed one-second
    aggregate. Individual TICK points are not a BPU candle and must not
    be passed to on_bar; TICK may only be used for preclose observations.
    """

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    timeframe: str = "M5"
    volume: float = 0.0

    def precision_label(self) -> str:
        return {
            "SEC": "sec_closed_bar",
            "M1": "m1_closed_bar",
            "M5": "m5_closed_bar",
        }.get(self.timeframe, "unsupported")


@dataclass
class BsuState:
    phase: str = "watch_bpu1"
    # watch_bpu1 -> bpu1 -> preclose_candidate -> bpu2_confirmed
    # Or bpu1 -> bpu2_confirmed (without verified TVX preclose)
    # Any rule violation -> invalidated, until explicit reset.
    level_price: float = 0.0
    side: str = "long"
    bsu_ts: datetime | None = None
    bpu1_ts: datetime | None = None
    bpu1_extreme: float | None = None
    luft: float = 0.0
    entry_price: float | None = None
    stop_price: float | None = None
    precision: str = "unverified"
    preclose_seen: bool = False
    reason: str = ""
    history: list[datetime] = field(default_factory=list)

    @property
    def can_submit(self) -> bool:
        """Always False: no source-only evidence authorizes any order."""
        return False


class BsuDetector:
    """State of one BSU origin, price level, side and bar resolution.

    Requires BSU source time and the security's native minimum tick size.
    Does not use config.bpu_tick_tol_atr as a proxy for precise touch.
    """

    def __init__(self, cfg: StrategyConfig, level_price: float, side: str,
                 atr_value: float, stop_buffer_atr: float | None = None,
                 *, tick_size: float | None = None,
                 bsu_ts: datetime | None = None):
        if side not in ("long", "short"):
            raise ValueError("side must be long or short")
        self.cfg = cfg
        level = _positive("level_price", level_price)
        atr = _positive("atr_value", atr_value)
        if tick_size is None:
            raise ValueError("native minimum tick_size is required")
        if bsu_ts is None:
            raise ValueError("BSU source bar time is required")
        tick = _positive("tick_size", tick_size)
        _aware("bsu_ts", bsu_ts)
        stop_factor = _positive(
            "stop_buffer_atr",
            cfg.stop_buffer_atr if stop_buffer_atr is None
            else stop_buffer_atr,
        )
        pct = _positive("luft_pct_of_stop", cfg.luft_pct_of_stop)
        if pct >= 100:
            raise ValueError("luft percentage must be less than 100")
        stop_distance = stop_factor * atr
        stop = level - stop_distance if side == "long" else level + stop_distance
        if stop <= 0:
            raise ValueError("derived stop must be positive")

        self._atr_value = atr
        self._tick_size = tick
        self._bsu_ts = bsu_ts
        self._stop_factor = stop_factor
        self._period: timedelta | None = None
        self._last_bar_ts: datetime | None = None
        # Within half of one native tick counts as equality after float
        # conversions. No 0.05*ATR approximation for 'exact' touch.
        self._tick_tol = tick * 0.5 + tick * 1e-7
        self.state = BsuState(
            level_price=level,
            side=side,
            bsu_ts=bsu_ts,
            stop_price=stop,
            luft=stop_distance * pct / 100.0,
        )

    @staticmethod
    def _validate_bar(bar: Bar) -> datetime:
        if not isinstance(bar, Bar):
            raise ValueError("expected a closed Bar")
        at = _aware("bar.ts", bar.ts)
        if bar.timeframe not in _BAR_PERIODS:
            raise ValueError("BPU requires completed SEC/M1/M5 candles")
        o = _positive("open", bar.open)
        h = _positive("high", bar.high)
        l = _positive("low", bar.low)
        c = _positive("close", bar.close)
        if h < max(o, c, l) or l > min(o, c, h):
            raise ValueError("OHLC bar shape is inconsistent")
        try:
            volume = float(bar.volume)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("volume must be finite and nonnegative") from None
        if not isfinite(volume) or volume < 0:
            raise ValueError("volume must be finite and nonnegative")
        return at

    def _touch_exact(self, bar: Bar) -> bool:
        value = bar.low if self.state.side == "long" else bar.high
        return abs(value - self.state.level_price) <= self._tick_tol

    def _pierced_bpu1(self, low: float, high: float) -> bool:
        ex = self.state.bpu1_extreme
        if ex is None:
            return True  # missing required evidence -> fail closed
        return (low < ex - self._tick_tol if self.state.side == "long"
                else high > ex + self._tick_tol)

    def _beyond_luft(self, low: float, high: float) -> bool:
        lvl, luft = self.state.level_price, self.state.luft
        if self.state.side == "long":
            # A BPU2 too far ABOVE support did not confirm that level;
            # a break BELOW BPU1 is handled by _pierced_bpu1.
            return low > lvl + luft + self._tick_tol
        return high < lvl - luft - self._tick_tol

    def _valid_bpu2_range(self, low: float, high: float) -> bool:
        return not (self._pierced_bpu1(low, high)
                    or self._beyond_luft(low, high))

    def tvx_timing_note(self) -> str:
        return (
            "TVX: 30 секунд ДО закрытия БПУ2. Закрытые M5/M1 бары "
            "не подтверждают предзакрытый ТВХ; для отдельного "
            "наблюдения нужны реальные SEC/TICK-данные. Даже при "
            "наблюдении это НЕ ордер и НЕ подтверждение исполнения."
        )

    def observe_preclose(
        self, *, observed_at: datetime, bpu2_end: datetime,
        observed_low: float, observed_high: float,
        last_price: float, source: str
    ) -> BsuState:
        """Read-only preclose sample from *actual* native SEC/TICK evidence.

        A single sample exactly 30 seconds before BPU2 closes can only be
        a provisional research candidate. The eventual closed BPU2 might
        invalidate the pattern. It is NOT a fill, not an order, and is
        never called by the M5-only LEAN algorithm.
        """
        st = self.state
        if st.phase != "bpu1" or st.bpu1_ts is None or self._period is None:
            raise ValueError("BPU1 evidence required before preclose sample")
        at = _aware("observed_at", observed_at)
        end = _aware("bpu2_end", bpu2_end)
        expected_end = _aware("bpu1_ts", st.bpu1_ts) + self._period
        if source not in _PRE_CLOSE_SOURCES:
            raise ValueError("SEC/TICK preclose observations required")
        if end != expected_end or end - at != timedelta(seconds=30):
            raise ValueError("preclose must be exactly 30s before next BPU2 end")
        low = _positive("observed_low", observed_low)
        high = _positive("observed_high", observed_high)
        price = _positive("last_price", last_price)
        if not low <= price <= high:
            raise ValueError("preclose sample price outside observed range")
        if not self._valid_bpu2_range(low, high):
            return self._invalidate("BPU2 violates the level before close")
        st.phase = "preclose_candidate"
        st.preclose_seen = True
        st.entry_price = (
            st.level_price + st.luft if st.side == "long"
            else st.level_price - st.luft
        )
        st.precision = source.lower() + "_preclose_observed"
        st.reason = (
            "30s preclose sample observed; BPU2 NOT yet closed or "
            "confirmed. Not an order or fill."
        )
        return st

    def on_bar(self, bar: Bar) -> BsuState:
        """Consume an already CLOSED OHLC bar without inferring TVX fills."""
        now = self._validate_bar(bar)
        st = self.state
        if st.phase in ("invalidated", "bpu2_confirmed"):
            return st
        if self._last_bar_ts is not None and now <= self._last_bar_ts:
            return self._invalidate("duplicate or out-of-order bar")
        self._last_bar_ts = now
        st.history.append(bar.ts)

        if st.phase == "watch_bpu1":
            if now <= _aware("bsu_ts", self._bsu_ts):
                return self._invalidate("BPU1 must follow historical BSU bar")
            if self._touch_exact(bar):
                st.phase = "bpu1"
                st.bpu1_ts = bar.ts
                st.bpu1_extreme = (
                    float(bar.low) if st.side == "long" else float(bar.high))
                st.precision = bar.precision_label()
                self._period = _BAR_PERIODS[bar.timeframe]
                st.reason = "BPU1 exact native-tick-level touch observed"
            return st

        # Next CLOSED bar must have the very next interval end of same type.
        if st.phase in ("bpu1", "preclose_candidate"):
            if (bar.timeframe not in _BAR_PERIODS or
                    _BAR_PERIODS[bar.timeframe] != self._period or
                    now != _aware("bpu1_ts", st.bpu1_ts) + self._period):
                return self._invalidate(
                    "BPU2 not the immediate next completed candle")
            if self._pierced_bpu1(bar.low, bar.high):
                return self._invalidate("BPU2 wick broke BPU1 extreme")
            if self._beyond_luft(bar.low, bar.high):
                return self._invalidate(
                    "BPU2 missed the level beyond permissible luft")
            st.phase = "bpu2_confirmed"
            if st.entry_price is None:
                st.entry_price = (
                    st.level_price + st.luft if st.side == "long"
                    else st.level_price - st.luft)
            st.reason = (
                "BPU2 confirmed on completed candle; "
                + ("30s preclose sample was seen; " if st.preclose_seen
                   else "no 30s preclose sample; ")
                + "research evidence only, no TVX order/fill"
            )
            return st

        return st

    def _invalidate(self, reason: str) -> BsuState:
        self.state.phase = "invalidated"
        self.state.reason = reason
        return self.state

    def reset(self) -> BsuState:
        """Start a new observation without retaining a broken BPU1/BPU2."""
        self.__init__(
            self.cfg, self.state.level_price, self.state.side,
            atr_value=self._atr_value, stop_buffer_atr=self._stop_factor,
            tick_size=self._tick_size, bsu_ts=self._bsu_ts)
        self.state.reason = "reset: wait for a new BPU1 from known BSU"
        return self.state
