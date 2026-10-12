"""Native-M5, read-only breakout -> retest -> confirmation research.

Original Qwct implementation inspired by the *idea* of explicit setup
states in published BreakoutRetestSetup examples, NOT copied code.
Daily Gerchik level/side and actual completed M5 bars are inputs. The
lookback/tolerances are research parameters, not authenticated course
rules. No subscriptions, orders, fills, targets, calendars or OMS.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite


M5 = timedelta(minutes=5)
TERMINAL = ("CONFIRMED", "EXPIRED", "INVALIDATED")


@dataclass(frozen=True)
class BreakoutRetestEvidence:
    symbol: str
    session: date
    side: str
    level_price: float
    phase: str
    breakout_at: datetime | None
    retest_at: datetime | None
    confirmed_at: datetime | None
    reason: str
    can_submit: bool = False

    def matches(self, *, symbol, session, side, level_price, observed_at):
        # Evidence is meaningful ONLY on the M5 candle that actually
        # completed the third distinct stage, not on subsequent candles.
        return (
            self.can_submit is False and self.phase == "CONFIRMED"
            and self.symbol == symbol and self.session == session
            and self.side == side and isfinite(float(level_price))
            and abs(self.level_price - float(level_price)) < 1e-8
            and self.breakout_at is not None
            and self.retest_at is not None
            and self.confirmed_at is not None
            and self.breakout_at < self.retest_at < self.confirmed_at
            and self.confirmed_at == observed_at
            and observed_at.date() == session
        )


class BreakoutRetestObserver:
    """One observed native M5 stream for one premarket D1 breakout.

    Requires: first a close CROSSING the level, a SEPARATE later M5
    retest/hold near the same level, and a subsequent candle closing
    through the retest extreme. No retrospective rescans or multi-
    candidate optimizer; a failed candidate is terminal for this session.
    """

    RETEST_BARS = 8
    RETEST_TOL_ATR = 0.20
    INVALIDATION_ATR = 0.50

    def __init__(self, *, symbol: str, session: date, side: str,
                 level_price: float, atr_value: float,
                 max_confirm_chase_atr: float):
        if not symbol or not isinstance(session, date) or side not in ("long", "short"):
            raise ValueError("confirmed symbol/session/side required")
        for name, value in (
            ("level", level_price), ("native D1 ATR", atr_value),
            ("no-chase ATR", max_confirm_chase_atr)
        ):
            if (isinstance(value, bool) or
                    not isfinite(float(value)) or float(value) <= 0):
                raise ValueError(f"{name} must be positive and finite")
        self.symbol = symbol
        self.session = session
        self.side = side
        self.level = float(level_price)
        self.atr = float(atr_value)
        self.chase = float(max_confirm_chase_atr)
        self.phase = "WATCH_BREAKOUT"
        self.reason = "awaiting native M5 close crossing preselected D1 level"
        self.breakout_at = None
        self.retest_at = None
        self.confirmed_at = None
        self._last_time = None
        self._last_close = None
        self._after_breakout = 0
        self._retest_extreme = None

    @property
    def evidence(self) -> BreakoutRetestEvidence:
        return BreakoutRetestEvidence(
            self.symbol, self.session, self.side, self.level, self.phase,
            self.breakout_at, self.retest_at, self.confirmed_at,
            self.reason)

    def _stop(self, phase, reason):
        self.phase, self.reason = phase, reason
        return self.evidence

    def on_m5(self, *, at: datetime, open_price: float, high: float,
              low: float, close: float, volume: float) -> BreakoutRetestEvidence:
        """One previously native-validated CLOSED M5 bar, in event order.

        Callback must have passed validate_m5_tradebar first; check prices
        and temporal continuity here independently to prevent a test
        fixture / another caller from bypassing the strategy contract.
        """
        if self.phase in TERMINAL:
            return self.evidence
        if (not isinstance(at, datetime) or at.tzinfo is None or
                at.utcoffset() is None or at.date() != self.session or
                at.second or at.microsecond or at.minute % 5):
            return self._stop("INVALIDATED", "M5_SESSION_OR_CLOCK_INVALID")
        vals = (open_price, high, low, close, volume)
        try:
            o, h, l, c, v = tuple(float(x) for x in vals)
        except (TypeError, ValueError, OverflowError):
            return self._stop("INVALIDATED", "M5_NUMERIC_INVALID")
        if (not all(isfinite(x) for x in (o, h, l, c, v))
                or min(o, h, l, c) <= 0 or v <= 0
                or h < max(o, c, l) or l > min(o, c, h)):
            return self._stop("INVALIDATED", "M5_OHLCV_INVALID")
        if self._last_time is not None and (
                at <= self._last_time or at - self._last_time != M5):
            return self._stop("INVALIDATED", "M5_GAP_DUPLICATE_OR_LATE")
        previous = self._last_close
        self._last_time, self._last_close = at, c
        bullish = self.side == "long"
        level = self.level

        if self.phase == "WATCH_BREAKOUT":
            if previous is not None and (
                (bullish and previous <= level < c) or
                (not bullish and previous >= level > c)):
                self.breakout_at = at
                self._after_breakout = 0
                return self._stop("WAIT_RETEST", "M5_BREAKOUT_CLOSED_WAIT_RETEST")
            return self.evidence

        if self.phase == "WAIT_RETEST":
            self._after_breakout += 1
            # Expiry is strictly time-bounded; no hidden infinite wait.
            if self._after_breakout > self.RETEST_BARS:
                return self._stop("EXPIRED", "RETEST_NOT_SEEN_WITHIN_EIGHT_M5")
            if (bullish and c < level - self.INVALIDATION_ATR * self.atr
                    or not bullish and c > level + self.INVALIDATION_ATR * self.atr):
                return self._stop("INVALIDATED", "CLOSED_BEYOND_LOSS_SIDE")
            close_holds = c >= level if bullish else c <= level
            near = (l <= level + self.RETEST_TOL_ATR * self.atr if bullish
                    else h >= level - self.RETEST_TOL_ATR * self.atr)
            if near and close_holds:
                self.retest_at = at
                self._retest_extreme = h if bullish else l
                return self._stop("WAIT_CONFIRMATION", "M5_RETEST_HELD_WAIT_NEXT_BAR")
            return self.evidence

        if self.phase == "WAIT_CONFIRMATION":
            # No same-candle and no future-looking confirmation:
            # exactly the immediate NEXT completed native M5 must close
            # beyond the retest candle's directional extreme.
            if (bullish and c < level - self.INVALIDATION_ATR * self.atr
                    or not bullish and c > level + self.INVALIDATION_ATR * self.atr):
                return self._stop("INVALIDATED", "CONFIRM_LOST_LEVEL")
            confirmed = (
                (bullish and c > self._retest_extreme and c > o)
                or (not bullish and c < self._retest_extreme and c < o))
            if not confirmed:
                return self._stop("INVALIDATED", "NEXT_M5_DID_NOT_CONFIRM")
            if abs(c - level) > self.chase * self.atr:
                return self._stop("INVALIDATED", "CONFIRM_OVEREXTENDED_NO_CHASE")
            self.confirmed_at = at
            return self._stop(
                "CONFIRMED", "BREAKOUT_RETEST_CONFIRMATION_M5_RESEARCH_ONLY")
        return self._stop("INVALIDATED", "UNKNOWN_RESEARCH_PHASE")
