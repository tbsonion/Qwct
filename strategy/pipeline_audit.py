"""Offline read-only audit of the EXISTING 14-feature / eight-gate pipeline.

Never authorizes trading, changes thresholds, fetches data or infers a TVX
from closed candles. Caller provides native data and the frozen decision.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .features import FEATURES, _coerce
from .signals import GATE_IDS, build_intent

ET = ZoneInfo("America/New_York")


def _aware(value):
    at = pd.Timestamp(value)
    if pd.isna(at) or at.tzinfo is None:
        raise ValueError("AUDIT_TIMEZONE_REQUIRED")
    return at.tz_convert(ET)


def _chronology(frame, *, daily, at):
    """Check actual chronology, never sort/drop bad rows into a success."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("D1_MISSING" if daily else "M5_MISSING")
    idx = frame.index
    if (not isinstance(idx, pd.DatetimeIndex) or idx.tz is None
            or idx.hasnans or not idx.is_unique or not idx.is_monotonic_increasing):
        raise ValueError("D1_CHRONOLOGY" if daily else "M5_CHRONOLOGY")
    if daily:
        if any(x.tz_convert(ET).date() >= at.date() for x in idx):
            raise ValueError("D1_CURRENT_OR_FUTURE_SESSION")
        if "bar_end" not in frame:
            raise ValueError("D1_NATIVE_ENDTIME_MISSING")
        ends = [_aware(x) for x in frame.bar_end]
        if (any(end <= start or end > at for start, end in zip(idx, ends))
                or any(a >= b for a, b in zip(ends, ends[1:]))):
            raise ValueError("D1_NOT_CLOSED_AT_FREEZE")
    elif (idx[-1] != at or any(x.tz_convert(ET).date() != at.date() for x in idx)
          or any(x.second or x.microsecond or x.minute % 5 for x in idx)
          or any(b-a != pd.Timedelta(minutes=5) for a, b in zip(idx, idx[1:]))):
        raise ValueError("M5_STALE_GAPPED_OR_UNALIGNED")


def feature_snapshot(features):
    """All fourteen identities with explicit UNKNOWN and unavailable details."""
    expected = {name for name, _ in FEATURES}
    rows, blockers = {}, []
    if set(features) != expected:
        blockers.append("FEATURE_IDENTITIES_INCOMPLETE_OR_EXTRA")
    for name in sorted(expected):
        feature = features.get(name)
        if feature is None:
            rows[name] = {"value": None, "reason": "FEATURE_MISSING", "detail": {}}
            continue
        try:
            value = _coerce(feature.value)
        except ValueError:
            value = None
            blockers.append(name + ":INVALID_BOOLEAN")
        reason = str(feature.reason)
        if reason.startswith("ошибка:"):
            blockers.append(name + ":CALCULATION_ERROR")
        rows[name] = {"value": value, "reason": reason, "detail": dict(feature.detail)}
    return rows, blockers


def gate_snapshot(gates):
    """Reject missing, relabelled or truthy non-boolean approval records."""
    rows, blockers = {}, []
    if set(gates) != set(GATE_IDS):
        blockers.append("GATE_IDENTITIES_INCOMPLETE_OR_EXTRA")
    for name in GATE_IDS:
        gate = gates.get(name)
        if gate is None:
            rows[name] = {"passed": None, "reason": "GATE_MISSING"}
            continue
        value = gate.passed
        if gate.id != name or (value is not None and type(value) is not bool):
            blockers.append(name + ":INVALID_GATE_RECORD")
            value = None
        rows[name] = {"passed": value, "reason": str(gate.reason)}
        if value is not True:
            blockers.append(name + (":UNKNOWN" if value is None else ":FALSE"))
    return rows, blockers


def audit_pipeline(decision, market, observed_at, cfg, *, equity=25000.0):
    """Inspect one frozen scenario with canonical build_intent unchanged.

    M5 input may include later bars: MarketData.m5_asof excludes them.
    D1 is frozen at the morning decision, not recomputed from today's bar.
    Current in-memory records cannot prove receive-time or author accuracy.
    """
    feature_rows, blockers = feature_snapshot(decision.features)
    gate_rows, _ = gate_snapshot({})
    report = {
        "symbol": str(market.symbol), "can_trade": False,
        "availability": "EVENT_TIME_ONLY_RECEIVE_TIME_UNVERIFIED",
        "author_accuracy": "UNKNOWN", "status": "BLOCKED",
        "features": feature_rows, "gates": gate_rows,
        "blockers": blockers, "stage": "INPUT_VALIDATION",
        "bpu_tvx_evidence": "UNVERIFIED", "intent": None,
    }
    try:
        at, freeze = _aware(observed_at), _aware(decision.decided_at)
        if (decision.symbol != market.symbol or decision.session != at.date()
                or freeze.date() != decision.session or freeze >= at
                or not decision.accepted or decision.level is None):
            raise ValueError("FROZEN_DECISION_IDENTITY_OR_TIME_INVALID")
        if (market.session_levels is None
                or decision.level not in market.session_levels
                or any(l.valid_from is None or l.valid_from > decision.session
                       for l in market.session_levels)):
            raise ValueError("SESSION_LEVEL_SNAPSHOT_UNVERIFIED")
        # The raw frames must have a trustworthy order before as-of slicing.
        for frame in (market.d1, market.m5):
            if (frame is None or not isinstance(frame.index, pd.DatetimeIndex)
                    or frame.index.tz is None or frame.index.hasnans
                    or not frame.index.is_unique or not frame.index.is_monotonic_increasing):
                raise ValueError("INPUT_CHRONOLOGY_UNVERIFIED")
        d1, m5 = market.d1_asof(freeze), market.m5_asof(at)
        _chronology(d1, daily=True, at=freeze)
        _chronology(m5, daily=False, at=at)
        report["observed_at"] = at.isoformat()
        report["frozen_at"] = freeze.isoformat()
        report["level_price"] = float(decision.level.price)
        report["level_source"] = str(decision.level.source)
        report["d1_bars"] = len(d1)
        report["m5_bars"] = len(m5)
        if blockers:
            return report
        # Do not let the intraday builder see a mutable/current D1 view.
        from .data import MarketData
        frozen_market = MarketData(
            market.symbol, d1, m5, session_levels=market.session_levels,
            breakout_retest=market.breakout_retest, bpu_tvx=market.bpu_tvx)
        report["stage"] = "CANONICAL_GATES"
        intent = build_intent(decision, frozen_market, at.to_pydatetime(), cfg, equity=equity)
        if intent is None:
            blockers.append("CANONICAL_INTENT_UNAVAILABLE")
            return report
        gate_rows, gate_blockers = gate_snapshot(intent.gates)
        report["gates"] = gate_rows
        blockers.extend(gate_blockers)
        report["intent"] = {
            "model": intent.model, "side": intent.side,
            "entry": intent.limit_price, "stop": intent.stop_price,
            "risk_per_share": intent.risk_per_share,
        }
        if decision.model == "bounce":
            report["bpu_tvx_evidence"] = (
                "MATCHED_CANONICAL_MECHANICS_NOT_AUTHOR_OR_DELIVERY_PROOF"
                if gate_rows["m5_confirmed"]["passed"] is True else "MISSING_OR_REJECTED")
        # Even a caller-provided matching object is not a verified receive-time
        # callback, author BSU, brokerage authorization or permission to trade.
        blockers.extend(("AUTHOR_BSU_NOT_CERTIFIED", "RECEIVE_TIME_NOT_CERTIFIED", "ORDERS_DISABLED"))
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError) as exc:
        blockers.append(str(exc)[:180] or type(exc).__name__)
    return report
