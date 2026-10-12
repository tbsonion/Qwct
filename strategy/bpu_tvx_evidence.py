"""Immutable provenance for a native observed Gerchik BPU2 TVX sequence.

Only a closed native M5 reconciled AFTER an actual -30s SECOND
observation may instantiate this read-only evidence. It represents a
confirmed algorithmic D1 swing proxy, NOT an original human-defined BSU
or native protective brokerage authorization.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite


@dataclass(frozen=True)
class BpuTvxEvidence:
    symbol: str
    session: date
    side: str
    d1_level_price: float
    native_origin_price: float
    bpu1_end: datetime
    preclose_at: datetime
    bpu2_end: datetime
    origin_provenance: str
    can_submit: bool = False

    def matches(self, *, symbol, session, side, level_price, observed_at):
        """Exact symbol/session/frozen level/directional and temporal match."""
        dates = (self.bpu1_end, self.preclose_at, self.bpu2_end, observed_at)
        try:
            return (
                self.can_submit is False
                and self.symbol == symbol
                and self.session == session
                and self.side == side
                and self.origin_provenance == (
                    "D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU")
                and all(isinstance(t, datetime) and t.tzinfo is not None
                        and t.utcoffset() is not None for t in dates)
                and all(isfinite(float(p)) and float(p) > 0
                        for p in (level_price, self.d1_level_price,
                                  self.native_origin_price))
                and abs(self.d1_level_price - float(level_price)) < 1e-8
                and self.bpu1_end + timedelta(minutes=5) == self.bpu2_end
                and self.preclose_at == self.bpu2_end - timedelta(seconds=30)
                and observed_at == self.bpu2_end
                and self.bpu2_end.date() == session
            )
        except (ValueError, TypeError, OverflowError):
            return False
