"""QWCT 4.6 — type-aware Gerchik level evidence, NOT author-certified BSU.

Sources: Gerchik, Kurs aktivnogo treidera, chapter on price levels;
https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya

Do not collapse different origins into one fixed LIMIT rule. All data must
already be closed and known at as_of. These labels are independent of orders,
TVX, and the strict M5 BSU scanner. Unknown origin stays indeterminate.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

KINDS = (
    "TREND_TURN", "HISTORICAL", "MIRROR", "LIMIT_PLAYER",
    "PARANORMAL", "CONSOLIDATION", "GAP", "FLOATING",
)
FIXED_CANDIDATE = "FIXED_BSU_CANDIDATE"
UNKNOWN = "INDETERMINATE"
FLOATING = "FLOATING_ZONE"


@dataclass(frozen=True)
class LevelBar:
    end: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self):
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("BAR_END_MUST_BE_AWARE")
        if not all(isfinite(float(v)) for v in
                   (self.open, self.high, self.low, self.close)):
            raise ValueError("INVALID_OHLC")
        if not self.low <= min(self.open, self.close) <= max(
                self.open, self.close) <= self.high:
            raise ValueError("INVALID_OHLC")


@dataclass(frozen=True)
class TypedBsuEvidence:
    kind: str
    status: str
    price: float
    side: str
    source_end: datetime | None
    confirmation_end: datetime | None
    reason: str
    author_verified: bool = False

    @property
    def can_trade(self):
        return False


def classify_typed_bsu(*, kind, price, side, tick_size, bars,
                       as_of, atr=None, min_confirmations=1):
    """Causal classification of one explicit source candidate.

    bars[0] is a candidate origin, not a retrospectively chosen winner.
    For historical levels, exact-price repeat is required. For mirror,
    require a CLOSED close-through then an exact far-side wick retest.
    A break in the original direction does NOT universally invalidate
    a mirror/historical level. Unimplemented qualitative source decisions
    stay INDETERMINATE; they are never silently promoted to FIXED.
    """
    if kind not in KINDS or side not in ("long", "short"):
        raise ValueError("UNSUPPORTED_LEVEL_TYPE_OR_SIDE")
    if not isfinite(float(price)) or price <= 0:
        raise ValueError("INVALID_LEVEL_PRICE")
    if not isfinite(float(tick_size)) or tick_size <= 0:
        raise ValueError("INVALID_NATIVE_TICK")
    if abs(price/tick_size-round(price/tick_size)) > 1e-6:
        raise ValueError("OFF_NATIVE_TICK")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("AS_OF_REQUIRED")
    if not isinstance(min_confirmations, int) or min_confirmations < 1:
        raise ValueError("INVALID_CONFIRMATION_COUNT")
    if not isinstance(bars, (tuple, list)) or any(
            not isinstance(b, LevelBar) for b in bars):
        raise ValueError("CLOSED_LEVEL_BARS_REQUIRED")
    normalized = [b.end.astimezone(timezone.utc) for b in bars]
    if any(t > as_of.astimezone(timezone.utc) for t in normalized):
        raise ValueError("FUTURE_BAR_FORBIDDEN")
    if any(a >= b for a, b in zip(normalized, normalized[1:])):
        raise ValueError("BARS_OUT_OF_ORDER")
    first = bars[0].end if bars else None
    last = bars[-1].end if len(bars) > 1 else None

    def result(status, reason, confirmed=None):
        return TypedBsuEvidence(kind, status, price, side, first,
                                confirmed, reason)

    if len(bars) < 2:
        return result(UNKNOWN, "SOURCE_REQUIRES_LATER_CONFIRMATION")
    eps = tick_size*1e-6
    def exact(v):
        return abs(v-price) <= eps
    def wick(b, role):
        return b.low if role == "long" else b.high
    def beyond(b, role):
        return (b.close < price-eps if role == "long"
                else b.close > price+eps)
    def near_side(b, role):
        return (b.close > price+eps if role == "long"
                else b.close < price-eps)

    if kind == "FLOATING":
        return result(FLOATING, "NO_FIXED_PRICE_PROVEN")

    if kind == "LIMIT_PLAYER":
        # Unlike other level types, a fixed limit order cannot tolerate
        # even one adverse wick penetration after the source touch.
        if not exact(wick(bars[0], side)):
            return result(UNKNOWN, "SOURCE_NOT_EXACT_LIMIT_TOUCH")
        count = 1
        for b in bars[1:]:
            w = wick(b, side)
            if (w < price-eps if side == "long" else w > price+eps):
                return result(FLOATING, "LIMIT_PLAYER_WICK_PIERCED")
            if exact(w):
                count += 1
                if count >= max(3, min_confirmations+1):
                    return result(FIXED_CANDIDATE, "THREE_EXACT_UNPIERCED_LIMIT_HITS", b.end)
        return result(UNKNOWN, "NOT_ENOUGH_EXACT_LIMIT_HITS")

    if kind == "HISTORICAL":
        # Key-point significance is NOT inferable from equal OHLC alone.
        # Exact repetition is evidence, not an author-certified key point.
        source_extremes = (bars[0].low, bars[0].high)
        if not any(exact(x) for x in source_extremes):
            return result(UNKNOWN, "NO_EXACT_HISTORICAL_SOURCE")
        for b in bars[1:]:
            if exact(b.low) or exact(b.high):
                return result(FIXED_CANDIDATE, "EXACT_HISTORICAL_PRICE_REPEAT_PROXY", b.end)
        return result(UNKNOWN, "NO_EXACT_HISTORICAL_REPEAT")

    if kind == "MIRROR":
        # Original role is opposite the requested new role.
        old = "short" if side == "long" else "long"
        if not exact(wick(bars[0], old)):
            return result(UNKNOWN, "NO_EXACT_ORIGINAL_ROLE_SOURCE")
        crossed = False
        for b in bars[1:]:
            if not crossed:
                if (b.close > price+eps if side == "long"
                        else b.close < price-eps):
                    crossed = True
            elif exact(wick(b, side)) and near_side(b, side):
                return result(FIXED_CANDIDATE, "BREAK_AND_EXACT_OPPOSITE_ROLE_RETEST", b.end)
        return result(UNKNOWN, "MIRROR_BREAK_OR_RETEST_NOT_CONFIRMED")

    if kind == "PARANORMAL":
        if atr is None or not isfinite(float(atr)) or atr <= 0:
            return result(UNKNOWN, "SOURCE_ATR_NOT_AVAILABLE")
        if bars[0].high-bars[0].low < 2*atr:
            return result(UNKNOWN, "SOURCE_BAR_BELOW_2ATR")
        if not exact(wick(bars[0], side)):
            return result(UNKNOWN, "PARANORMAL_EXTREME_NOT_SOURCE_PRICE")
        for b in bars[1:]:
            if exact(wick(b, side)):
                return result(FIXED_CANDIDATE, "PARANORMAL_2ATR_AND_EXACT_RETEST_PROXY", b.end)
        return result(UNKNOWN, "PARANORMAL_CONFIRMATION_NOT_OBSERVED")

    if kind == "GAP":
        # The price gap requires the PREVIOUS bar, and two distinct
        # boundaries; OHLC alone does not prove an exchange session gap.
        return result(UNKNOWN, "SESSION_GAP_BOUNDARIES_NOT_VERIFIED")

    if kind == "CONSOLIDATION":
        # The book requires a consolidation on one side, not just hits.
        # Until the directional zone is independently certified, fail closed.
        return result(UNKNOWN, "CONSOLIDATION_ZONE_NOT_VERIFIED")

    if kind == "TREND_TURN":
        # A local pivot is not sufficient proof of a genuine trend reversal.
        return result(UNKNOWN, "TREND_REVERSAL_NOT_VERIFIED")

    raise AssertionError("unreachable")
