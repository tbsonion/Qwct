"""Read-only, completed-bar view for the original Gerchik strategy rules.

Bars are supplied by LEAN History/Consolidate. This module does NOT fetch
prices, simulate fills, calculate exchange hours, or schedule events.
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .levels import Level

ET = ZoneInfo("America/New_York")


def _et(ts: datetime) -> pd.Timestamp:
    # A wrong timezone can shift the D1 cutoff by an entire day around
    # midnight or DST. Fail closed instead of interpreting naive data
    # as if its native source were known to be US/Eastern.
    value = pd.Timestamp(ts)
    if value.tzinfo is None:
        raise ValueError("as-of timestamp must include a real timezone")
    return value.tz_convert(ET)


@dataclass
class MarketData:
    symbol: str
    d1: pd.DataFrame
    m5: pd.DataFrame | None = None
    # None -> legacy pure-test fallback to as-of recomputation. An explicit
    # tuple (including empty) is the premarket snapshot and MUST be reused
    # unchanged throughout the trading day to avoid data revision/drift.
    session_levels: tuple["Level", ...] | None = None

    def d1_asof(self, ts: datetime) -> pd.DataFrame:
        current_day = _et(ts).normalize()
        return self.d1.loc[self.d1.index < current_day]

    def m5_asof(self, ts: datetime) -> pd.DataFrame:
        if self.m5 is None:
            return pd.DataFrame()
        return self.m5.loc[self.m5.index <= _et(ts)]
