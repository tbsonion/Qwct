"""Read-only risk-policy preflight for *provided* native LEAN evidence.

Does NOT own balances, simulate trades/fills, fetch data, approve a broker
or change any Qwct signal gate. Missing native P&L/exposure/entry history
remains UNKNOWN, never silently interpreted as zero.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from .config import StrategyConfig


def _money(name: str, value, *, strictly_positive: bool = False):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a real number, not bool")
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{name} must be finite") from None
    if not isfinite(n) or (strictly_positive and n <= 0):
        raise ValueError(f"{name} must be finite and positive" if strictly_positive
                         else f"{name} must be finite")
    return n


def _count(name: str, value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class RiskSnapshot:
    """Native point-in-time evidence, populated by an explicit caller.

    A Python-only test may construct this from labeled synthetic values.
    Live/paper risk gate MUST NOT take such a test fixture as approval.
    None fields mean 'not available', not zero.
    """
    equity: float
    available_buying_power: float | None
    current_positions: int | None
    pending_entries: int | None
    reserved_open_risk: float | None
    daily_realized_pnl: float | None
    weekly_realized_pnl: float | None
    monthly_realized_pnl: float | None
    losing_trades_today: int | None
    entries_today: int | None
    consecutive_losing_days: int | None
    pause_days_remaining: int | None
    asof: datetime
    # Baselines must be sampled from native marked-to-market portfolio equity
    # at each exchange-period start and adjusted for external cash flows.
    # Missing anchor/cashflow provenance never means today's equity.
    daily_start_equity: float | None = None
    weekly_start_equity: float | None = None
    monthly_start_equity: float | None = None
    period_cashflows_verified: bool | None = None
    winning_trades_today: int | None = None
    # Must come from native LEAN exchange-hours calendar (early close/DST).
    exchange_close: datetime | None = None

    def __post_init__(self):
        _money("equity", self.equity, strictly_positive=True)
        for name in ("daily_start_equity", "weekly_start_equity",
                     "monthly_start_equity"):
            _money(name, getattr(self, name), strictly_positive=True)
        if self.period_cashflows_verified not in (None, True, False):
            raise ValueError("period_cashflows_verified must be bool or None")
        for name in ("available_buying_power", "reserved_open_risk"):
            v = _money(name, getattr(self, name))
            if v is not None and v < 0:
                raise ValueError(f"{name} must not be negative")
        for name in ("daily_realized_pnl", "weekly_realized_pnl",
                     "monthly_realized_pnl"):
            _money(name, getattr(self, name))
        for name in ("current_positions", "pending_entries",
                     "losing_trades_today", "entries_today",
                     "consecutive_losing_days", "pause_days_remaining",
                     "winning_trades_today"):
            _count(name, getattr(self, name))
        if (not isinstance(self.asof, datetime) or self.asof.tzinfo is None
                or self.asof.utcoffset() is None):
            raise ValueError("native as-of risk snapshot requires aware datetime")
        if self.exchange_close is not None and (
                not isinstance(self.exchange_close, datetime)
                or self.exchange_close.tzinfo is None
                or self.exchange_close.utcoffset() is None):
            raise ValueError("native exchange close must be timezone-aware")


@dataclass(frozen=True)
class RiskPreflight:
    mechanical_pass: bool | None
    complete: bool
    projected_stop_risk: float
    planned_notional: float
    blockers: tuple[str, ...]
    can_submit: bool = False


def review_risk(snapshot: RiskSnapshot, *, side: str, shares: int,
                entry_price: float, stop_price: float,
                cfg: StrategyConfig) -> RiskPreflight:
    """Conservative monetary-limit study, NEVER a broker risk approval.

    Mechanical TRUE only means the supplied complete data satisfy
    configured arithmetic limits. Brokerage buying power, partial fills,
    stop activation and slippage are still unverified; can_submit=False.
    """
    if not isinstance(snapshot, RiskSnapshot):
        raise TypeError("provide an explicit native RiskSnapshot")
    if side not in ("long", "short") or isinstance(shares, bool) or (
            not isinstance(shares, int) or shares <= 0):
        raise ValueError("valid long/short side and whole shares required")
    entry = _money("entry_price", entry_price, strictly_positive=True)
    stop = _money("stop_price", stop_price, strictly_positive=True)
    if (side == "long" and stop >= entry) or (
            side == "short" and stop <= entry):
        raise ValueError("stop must lie on the loss side of proposed entry")
    notional = shares * entry
    risk = shares * abs(entry - stop)
    budget = snapshot.equity * cfg.risk_per_trade_pct / 100.0
    daily_budget = ((snapshot.daily_start_equity or snapshot.equity)
                    * cfg.max_daily_risk_pct / 100.0)
    blockers = []
    unknown = []

    if risk > budget + 1e-8:
        blockers.append("planned stop-distance exposure exceeds per-trade risk limit")
    checks = {
        "available_buying_power": snapshot.available_buying_power,
        "current_positions": snapshot.current_positions,
        "pending_entries": snapshot.pending_entries,
        "reserved_open_risk": snapshot.reserved_open_risk,
        "daily_realized_pnl": snapshot.daily_realized_pnl,
        "weekly_realized_pnl": snapshot.weekly_realized_pnl,
        "monthly_realized_pnl": snapshot.monthly_realized_pnl,
        "losing_trades_today": snapshot.losing_trades_today,
        "entries_today": snapshot.entries_today,
        "consecutive_losing_days": snapshot.consecutive_losing_days,
        "pause_days_remaining": snapshot.pause_days_remaining,
        "winning_trades_today": snapshot.winning_trades_today,
        "daily_start_equity": snapshot.daily_start_equity,
        "weekly_start_equity": snapshot.weekly_start_equity,
        "monthly_start_equity": snapshot.monthly_start_equity,
        "period_cashflows_verified": snapshot.period_cashflows_verified,
        "exchange_close": snapshot.exchange_close,
    }
    for name, value in checks.items():
        if value is None:
            unknown.append(f"unknown native {name}; cannot assume zero")
    if snapshot.period_cashflows_verified is False:
        blockers.append("period start equity not adjusted for cashflows")
    if snapshot.exchange_close is not None:
        close = snapshot.exchange_close
        # The source of this timestamp is LEAN's native exchange schedule.
        # No hardcoded 16:00 close: half-days must be handled by caller.
        if snapshot.asof.astimezone(close.tzinfo).date() != close.date():
            blockers.append("risk snapshot is not for the native exchange session")
        elif snapshot.asof >= close - timedelta(minutes=cfg.flatten_before_close_min):
            blockers.append("new position disallowed at native EOD cutoff")
    for period, base, limit in (
            ("daily", snapshot.daily_start_equity, cfg.max_daily_loss_pct),
            ("weekly", snapshot.weekly_start_equity, cfg.max_weekly_loss_pct),
            ("monthly", snapshot.monthly_start_equity, cfg.max_monthly_loss_pct)):
        if base is not None and snapshot.equity <= base * (1 - limit / 100.0):
            blockers.append(
                f"{period} marked-to-market equity drawdown limit reached")
    if snapshot.available_buying_power is not None and (
            notional > snapshot.available_buying_power + 1e-8):
        blockers.append("planned gross notional exceeds supplied buying-power proxy")
    if snapshot.current_positions is not None and (
            snapshot.current_positions >= cfg.max_positions):
        blockers.append("max simultaneous positions reached")
    if snapshot.pending_entries is not None and snapshot.pending_entries > 0:
        blockers.append("open entry orders; reservations not reconciled")
    if snapshot.reserved_open_risk is not None and (
            snapshot.reserved_open_risk + risk > daily_budget + 1e-8):
        blockers.append("combined open and planned risk exceeds daily risk budget")
    for interval, pnl, pct in (
            ("daily", snapshot.daily_realized_pnl, cfg.max_daily_loss_pct),
            ("weekly", snapshot.weekly_realized_pnl, cfg.max_weekly_loss_pct),
            ("monthly", snapshot.monthly_realized_pnl, cfg.max_monthly_loss_pct)):
        if pnl is not None and pnl <= -(snapshot.equity * pct / 100.0):
            blockers.append(f"{interval} realized loss limit reached")
    if (snapshot.losing_trades_today is not None and
            snapshot.losing_trades_today >= cfg.max_losing_trades_per_day):
        blockers.append("daily losing-trade limit reached")
    if (snapshot.losing_trades_today is not None and
            snapshot.winning_trades_today is not None and
            snapshot.losing_trades_today >= 2 and
            snapshot.winning_trades_today >= 1):
        blockers.append("2 losing and 1 winning closed trades: trading day ended")
    if snapshot.entries_today is not None and (
            snapshot.entries_today >= cfg.max_trades_per_day):
        blockers.append("daily trade-count limit reached")
    if (snapshot.consecutive_losing_days is not None and
            snapshot.consecutive_losing_days >= cfg.losing_days_break):
        blockers.append("consecutive losing-day break required")
    if (snapshot.pause_days_remaining is not None and
            snapshot.pause_days_remaining > 0):
        blockers.append("trading pause remains active")

    complete = not unknown
    mechanical_pass = False if blockers else None if unknown else True
    # This safety blocker must NOT influence the mechanical-pass tri-state.
    return RiskPreflight(
        mechanical_pass=mechanical_pass, complete=complete,
        projected_stop_risk=risk, planned_notional=notional,
        blockers=tuple(blockers + unknown + [
            "broker-native entry/stop protection and partial-fill behavior unverified; no orders"]),
        can_submit=False,
    )
