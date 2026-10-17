"""Gerchik BSU/BPU1/BPU2 provisional -30s TVX, STRICTLY as-of review.

This is NOT the retrospective confirmed-BPU2 M5 gate and not an order.
Uses only frozen prior-day D1, closed M5 through BPU1, and the actual
already completed SECOND bar ending 30s before BPU2 close. It never
assumes that the remaining 30 seconds have happened or that Schwab
will accept/activate a stop. Unresolved native risk is explicitly UNKNOWN.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from .indicators import global_trend, trend_direction
from .levels import next_level
from .sessions import SessionPolicy

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PrecloseReview:
    observed_at: datetime
    bpu2_end: datetime
    side: str
    limit_price: float
    stop_price: float
    last_trade_price: float
    estimated_shares: int
    planned_risk_usd: float
    checks: tuple[tuple[str, bool | None], ...]
    blockers: tuple[str, ...]
    # Never let a signal-only research review authorize a broker order.
    can_submit: bool = False

    @property
    def evidence_ready(self) -> bool:
        """All REQUIRED observable checks passed; broker remains UNKNOWN.

        An empty or incomplete tuple must never be a successful preclose
        evidence review (all([]) is True in Python).
        """
        required = {
            "native_second_cutoff", "frozen_origin_level",
            "bpu1_bpu2_preclose", "asof_d1_m5", "native_d1_trend",
            "daily_atr_ready", "native_tick_limit_stop",
            "last_trade_no_chase", "frozen_next_level_room_4r",
            "target_3r", "gerchik_session", "preliminary_risk_budget",
        }
        checks = dict(self.checks)
        return (len(checks) == len(self.checks)
                and set(checks) == required | {"broker_protection"}
                and checks["broker_protection"] is None
                and all(checks[name] is True for name in required))


def review_preclose(*, decision, link, detector_state, sample, d1,
                    closed_m5, levels, cfg, equity, session_policy=None):
    """One immutable, read-only as-of review. No native LEAN or market calls.

    A missing/future D1 or M5 datum is an explicit failure, never an
    inferred value. frozen levels must come from session D1 snapshot.
    """
    if session_policy is None:
        session_policy = SessionPolicy(cfg)
    checks = {}
    blockers = []
    def check(name, ok, why):
        checks[name] = bool(ok) if ok is not None else None
        if ok is not True:
            blockers.append(why)

    at = sample.observed_at
    stamp_ok = (
        isinstance(at, datetime) and at.tzinfo is not None
        and at.utcoffset() is not None
        and sample.bpu2_end-at == timedelta(seconds=30)
        and sample.observed_since + timedelta(minutes=5) == sample.bpu2_end
        and at.astimezone(ET).date() == decision.session
        and sample.can_submit is False)
    check("native_second_cutoff", stamp_ok,
          "no exactly timed native SECOND sample at -30 seconds")

    side = decision.side
    level = decision.level
    tick = float(link.tick_size)
    pivot = float(link.origin_price)
    frozen = (decision.accepted and decision.model == "bounce"
              and side in ("long", "short")
              and link.provenance ==
                "D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU"
              and level is not None and level in (levels or ())
              and level.valid_from is not None
              and level.valid_from <= decision.session
              and float(level.price) == float(link.cluster_price)
              and isfinite(tick) and tick > 0
              and abs(float(level.price)-pivot) <= tick*0.5 + 1e-8)
    check("frozen_origin_level", frozen,
          "D1 level or exact swing-origin BSU does not match frozen session")

    st = detector_state
    seq = (st.phase == "preclose_candidate" and st.preclose_seen
           and st.bpu1_ts == sample.observed_since
           and st.side == side and st.can_submit is False
           and abs(st.level_price-pivot) <= tick*0.5 + 1e-8)
    check("bpu1_bpu2_preclose", seq,
          "BPU1 or real SEC partial BPU2 is unverified")

    def aligned(data):
        return (isinstance(data, pd.DataFrame)
                and isinstance(data.index, pd.DatetimeIndex)
                and data.index.tz is not None
                and data.index.is_monotonic_increasing
                and data.index.is_unique)
    d1_ok = (
        aligned(d1) and len(d1) >= cfg.trend_sma+1
        and all(ts.tz_convert(ET).date() < decision.session
                for ts in d1.index)
        and "atr"+str(cfg.atr_period) in d1.columns)
    m5_ok = (
        aligned(closed_m5) and len(closed_m5) >= 1
        and closed_m5.index[-1] == pd.Timestamp(sample.observed_since)
        and all(ts <= pd.Timestamp(sample.observed_since)
                for ts in closed_m5.index)
        and pd.Timestamp(decision.decided_at) < pd.Timestamp(at))
    check("asof_d1_m5", d1_ok and m5_ok,
          "missing, future, or stale D1/closed M5 information")

    trend_ok = False
    atr = float("nan")
    if d1_ok:
        try:
            a = float(d1["atr"+str(cfg.atr_period)].iloc[-1])
            atr = a if isfinite(a) and a > 0 else float("nan")
            direction = 1 if side == "long" else -1
            trend_ok = (not cfg.allow_countertrend and
                        global_trend(d1, len(d1)-1, cfg) == direction
                        and trend_direction(d1, len(d1)-1, cfg) == direction)
        except (ValueError, KeyError, TypeError, OverflowError, IndexError):
            trend_ok = False
    check("native_d1_trend", trend_ok, "D1 trend not verified as of session")
    check("daily_atr_ready", isfinite(atr) and atr > 0,
          "native D1 ATR not available")

    entry, stop, price = (
        float(st.entry_price) if st.entry_price is not None else float("nan"),
        float(st.stop_price) if st.stop_price is not None else float("nan"),
        float(sample.last_price))
    numeric = all(isfinite(v) and v > 0 for v in (entry, stop, price))
    risk_ps = (entry-stop if side == "long" else stop-entry)
    tick_grid = (numeric and
                 all(abs(round(v/tick)*tick-v) <= tick*1e-5
                     for v in (entry, stop)))
    entry_ok = (tick_grid and risk_ps > 0
                and ((stop < pivot < entry) if side == "long"
                     else (entry < pivot < stop))
                and abs(abs(entry-pivot)-0.2*abs(pivot-stop))
                    <= tick*0.5 + 1e-8)
    check("native_tick_limit_stop", entry_ok,
          "native-tick TVX limit, stop or 20% luft invalid")

    near = (isfinite(atr) and isfinite(price)
            and abs(price-pivot) <= cfg.max_entry_distance_atr*atr)
    check("last_trade_no_chase", near,
          "last SEC trade exceeds no-chase threshold at -30s")

    room_ok = False
    if entry_ok and levels is not None and risk_ps > 0:
        direction = 1 if side == "long" else -1
        target_level = next_level(
            tuple(l for l in levels if l.valid_from is not None
                  and l.valid_from <= decision.session),
            entry, direction)
        room_ok = bool(target_level is not None and
                       abs(target_level.price-entry)/risk_ps
                       >= cfg.min_room_r)
    check("frozen_next_level_room_4r", room_ok,
          "no premarket frozen next level at least 4R away")

    tp = (entry+cfg.tp_r*risk_ps if side == "long"
          else entry-cfg.tp_r*risk_ps)
    check("target_3r", entry_ok and isfinite(tp) and tp > 0
          and cfg.tp_r >= cfg.min_rr,
          "theoretical 3R target not on profit side or positive")

    allowed, _ = session_policy.is_entry_allowed("bounce", at)
    check("gerchik_session", allowed, "preclose not inside bounce time window")

    try:
        equity = float(equity)
        shares = int((equity * cfg.risk_per_trade_pct / 100)//risk_ps) if (
            isfinite(equity) and equity > 0 and risk_ps > 0) else 0
    except (ValueError, OverflowError, TypeError, ZeroDivisionError):
        shares = 0
    estimated_risk = shares*risk_ps if shares > 0 else 0.
    check("preliminary_risk_budget", (shares > 0 and
          isfinite(equity) and shares*entry <= equity
          and estimated_risk <= equity*cfg.risk_per_trade_pct/100),
          "preliminary size exceeds cash or single-trade risk budget")
    # We have NOT verified total portfolio exposure, losses, native
    # brokerage buying power, full fills or protective child orders.
    check("broker_protection", None,
          "UNKNOWN: native portfolio risk ledger, fills and Schwab protection")
    return PrecloseReview(
        observed_at=at, bpu2_end=sample.bpu2_end,
        side=side, limit_price=entry, stop_price=stop,
        last_trade_price=price, estimated_shares=shares,
        planned_risk_usd=estimated_risk,
        checks=tuple(checks.items()), blockers=tuple(blockers))
