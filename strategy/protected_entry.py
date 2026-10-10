"""Read-only Schwab/LEAN native bracket feasibility review.

This module does NOT submit orders, emulate broker fills, maintain an OMS,
or approve live/paper trading. LEAN OTO/Bracket child exits activate only
after the parent FULLY fills; Schwab does not support OUO. The review must
remain fail-closed until actual LEAN and Schwab behavior is verified.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class ProtectedEntryReview:
    # A single whole-share LEAN bracket is a DOCUMENTED research candidate,
    # not a verified broker guarantee.
    native_candidate: bool
    can_submit: bool
    risk_usd: float
    target_price: float
    blockers: tuple[str, ...]


def _positive_decimal(name: str, value) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite, positive number") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be a finite, positive number")
    return parsed


def review_schwab_protected_entry(
    *, side: str, shares: int, limit_price: float, stop_price: float,
    target_r: float, max_risk_usd: float,
) -> ProtectedEntryReview:
    """Evaluate an intended LIMIT entry + stop + initial 3R bracket.

    All returned reviews are NOT authorized for submission. 'risk_usd'
    is stop-distance exposure before fees/slippage, NOT guaranteed loss.
    No live LEAN order types or simulated fills are constructed here.
    """
    if side not in ("long", "short"):
        raise ValueError("side must be long or short")
    if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise ValueError("shares must be a positive whole number")
    entry = _positive_decimal("limit_price", limit_price)
    stop = _positive_decimal("stop_price", stop_price)
    target_ratio = _positive_decimal("target_r", target_r)
    risk_cap = _positive_decimal("max_risk_usd", max_risk_usd)
    if ((side == "long" and stop >= entry) or
            (side == "short" and stop <= entry)):
        raise ValueError("protective stop must be on the loss side of the limit entry")

    per_share = abs(entry - stop)
    exposure = per_share * shares
    target = entry + per_share * target_ratio * (1 if side == "long" else -1)
    if target <= 0:
        raise ValueError("derived take-profit must be positive")

    blockers = []
    if exposure > risk_cap:
        blockers.append("planned stop-distance exposure exceeds configured risk budget")
    if shares != 1:
        blockers.append(
            "multi-share LEAN Bracket/OTO leaves partial limit entry "
            "without active child stop"
        )
        blockers.append(
            "Schwab lacks OUO; OCO can cancel the sibling stop "
            "on partial profit exit"
        )
    blockers.append(
        "actual LEAN/Schwab contingent activation and order acknowledgements "
        "are not runtime-verified"
    )
    blockers.append(
        "stop-market fill price and absolute maximum loss cannot be guaranteed"
    )
    return ProtectedEntryReview(
        native_candidate=(shares == 1),
        can_submit=False,  # NEVER promote from documentation alone
        risk_usd=float(exposure),
        target_price=float(target),
        blockers=tuple(blockers),
    )
