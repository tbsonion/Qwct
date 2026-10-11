"""Bounded, audit-only D1 -> M5 research decision trace.

No LEAN imports, broker access, simulated fills, price invention, or orders.
Each trace originates from one ACCEPTED morning D1 scenario and records
actual subsequent M5 gate outcomes, including UNKNOWN separately from TRUE.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from .scenarios import ScenarioDecision

_ET = ZoneInfo("America/New_York")


def _as_et(ts: datetime) -> datetime:
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("trace event must have timezone-aware time")
    return ts.astimezone(_ET)


def _short(value: object, limit: int = 84) -> str:
    # Single-line, deterministic and deliberately bounded for LEAN Cloud logs.
    return str(value).replace("\n", " ").replace("\r", " ")[:limit]



class BpuTouchAudit:
    """Native closed-M5 distance to the original BSU swing pivot.

    A resistance BPU1 requires the M5 HIGH to equal the reference
    pivot within the detector's native reference tick tolerance.
    A candle passing across the pivot does NOT equal a precise touch.
    Split-adjusted prices may have sub-cent effective precision;
    the reference tick is reported, NEVER silently widened.
    """

    def __init__(self, side: str, level: float, native_tick: float):
        if side not in ("long", "short"):
            raise ValueError("unsupported BPU side")
        self.side = side
        self.level = float(level)
        self.native_tick = float(native_tick)
        if (not isfinite(self.level) or self.level <= 0
                or not isfinite(self.native_tick) or self.native_tick <= 0):
            raise ValueError("native BPU price/tick must be finite and positive")
        self.tolerance = self.native_tick * 0.5 + self.native_tick * 1e-7
        self.bars = 0
        self.touches = 0
        self.undershoots = 0
        self.overshoots = 0
        self.closest_extreme = None
        self.closest_gap = None
        self.nearest_time = ""
        self.maximum_high = None
        self.minimum_low = None

    def observe(self, timestamp: datetime, low: float, high: float,
                close: float) -> None:
        at = _as_et(timestamp)
        low, high, close = float(low), float(high), float(close)
        if (not all(isfinite(v) and v > 0 for v in (low, high, close))
                or not low <= close <= high):
            raise ValueError("native M5 OHLC is invalid")
        high_before = self.maximum_high
        low_before = self.minimum_low
        self.maximum_high = high if high_before is None else max(high_before, high)
        self.minimum_low = low if low_before is None else min(low_before, low)
        extreme = high if self.side == "short" else low
        gap = extreme - self.level
        if self.closest_gap is None or abs(gap) < abs(self.closest_gap):
            self.closest_gap = gap
            self.closest_extreme = extreme
            self.nearest_time = at.isoformat(timespec="seconds")
        if abs(gap) <= self.tolerance:
            self.touches += 1
        elif gap < 0:
            self.undershoots += 1
        else:
            self.overshoots += 1
        self.bars += 1

    def as_dict(self):
        return {
            "side": self.side, "level": self.level,
            "native_tick": self.native_tick, "tolerance": self.tolerance,
            "bars": self.bars, "touches": self.touches,
            "undershoots": self.undershoots, "overshoots": self.overshoots,
            "closest_extreme": self.closest_extreme,
            "closest_gap": self.closest_gap,
            "closest_gap_ticks": (
                self.closest_gap / self.native_tick
                if self.closest_gap is not None else None),
            "nearest_time": self.nearest_time,
            "maximum_high": self.maximum_high, "minimum_low": self.minimum_low,
        }

    def short_line(self, symbol: str, session: str) -> str:
        if self.closest_gap is None:
            return f"QWCT TOUCH {symbol} {session} no observed M5 candles"
        return (
            f"QWCT TOUCH {symbol} {session} {self.side} "
            f"n={self.bars} pivot={self.level:.4f} "
            f"tick={self.native_tick:.5f} tolerance={self.tolerance:.5f} "
            f"closest={self.closest_extreme:.4f} "
            f"gap={self.closest_gap:+.4f} "
            f"at={self.nearest_time[11:16]} "
            f"exact={self.touches} under={self.undershoots} over={self.overshoots}"
        )[:190]


@dataclass
class SetupTrace:
    symbol: str
    session: str
    decided_at: datetime
    model: str
    side: str
    level: float
    score: float
    feature_positives: list[str]
    level_count: int
    level_kind: str
    level_source: str
    level_first_idx: int
    level_last_idx: int
    level_formed_at: str
    level_valid_from: str
    d1_close: float
    d1_atr: float
    bsu: str = "not_evaluated"
    bsu_reason: str = "not evaluated"
    m5_checks: int = 0
    missing_intent: int = 0
    first_m5: str = ""
    last_m5: str = ""
    last_gate_outcomes: dict[str, str] = field(default_factory=dict)
    last_gate_reasons: dict[str, str] = field(default_factory=dict)
    last_two_m5: list[dict] = field(default_factory=list)
    failed_gate_counts: Counter = field(default_factory=Counter)
    bpu1_count: int = 0
    bpu2_count: int = 0
    bpu_failure_reasons: Counter = field(default_factory=Counter)
    touch_audit: BpuTouchAudit | None = None
    m5_passes: int = 0
    first_m5_pass: str = ""
    first_m5_pass_gates: str = ""
    candidate: bool = False

    @classmethod
    def from_decision(cls, decision: ScenarioDecision,
                      d1_close: float, native_atr: float,
                      level_count: int) -> "SetupTrace":
        if not decision.accepted or decision.level is None:
            raise ValueError("only accepted D1 scenarios can be traced")
        decided = _as_et(decision.decided_at)
        if decision.session != decided.date():
            raise ValueError("scenario session must match morning decision time")
        try:
            close, atr, price, score = map(
                float, (d1_close, native_atr, decision.level.price, decision.score))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("D1 trace missing numeric source values") from None
        if (not all(isfinite(v) for v in (close, atr, price, score))
                or min(close, atr, price) <= 0 or level_count < 0):
            raise ValueError("D1 trace missing valid price/ATR/level context")
        return cls(
            symbol=str(decision.symbol), session=decision.session.isoformat(),
            decided_at=decided, model=str(decision.model), side=str(decision.side),
            level=price, score=score,
            feature_positives=list(decision.positives),
            level_count=level_count,
            level_kind=str(decision.level.kind),
            level_source=str(decision.level.source),
            level_first_idx=int(decision.level.first_idx),
            level_last_idx=int(decision.level.last_idx),
            level_formed_at=(decision.level.formed_at.isoformat()
                             if decision.level.formed_at is not None else ""),
            level_valid_from=(decision.level.valid_from.isoformat()
                              if decision.level.valid_from is not None else ""),
            d1_close=close, d1_atr=atr)

    def set_bsu(self, armed: bool, reason: str) -> None:
        self.bsu = "armed" if armed else "blocked"
        self.bsu_reason = _short(reason, 160)

    def observe_m5(self, timestamp: datetime,
                   gates: dict[str, tuple[bool | None, str]],
                   closed_bars: list[dict] | None = None) -> None:
        at = _as_et(timestamp)
        if at.date().isoformat() != self.session or at <= self.decided_at:
            raise ValueError("M5 event not in accepted scenario's session")
        iso = at.isoformat(timespec="seconds")
        if self.last_m5 and iso <= self.last_m5:
            raise ValueError("M5 event not chronologically newer than prior check")
        bars = []
        if closed_bars is not None:
            if len(closed_bars) > 2:
                raise ValueError("audit snapshot must contain at most two M5 bars")
            for row in closed_bars:
                ts = _as_et(row["date"])
                try:
                    o, h, lo, cl, vol = (
                        float(row[k]) for k in
                        ("open", "high", "low", "close", "volume"))
                except (KeyError, TypeError, ValueError, OverflowError):
                    raise ValueError("incomplete native M5 snapshot") from None
                if (not all(isfinite(v) for v in (o, h, lo, cl, vol))
                        or min(o, h, lo, cl) <= 0 or vol < 0
                        or h < max(o, lo, cl) or lo > min(o, h, cl)
                        or ts > at or ts.date().isoformat() != self.session
                        or ts <= self.decided_at):
                    raise ValueError("invalid or future M5 evidence")
                bars.append({
                    "time": ts.isoformat(timespec="seconds"),
                    "open": o, "high": h, "low": lo,
                    "close": cl, "volume": vol})
            if bars and (bars[-1]["time"] != iso or
                         any(bars[i]["time"] >= bars[i+1]["time"]
                             for i in range(len(bars)-1))):
                raise ValueError("native M5 snapshot timestamp mismatch")
        self.last_two_m5 = bars
        self.m5_checks += 1
        if not self.first_m5:
            self.first_m5 = iso
        self.last_m5 = iso
        self.last_gate_outcomes = {}
        self.last_gate_reasons = {}
        # Capture rare positive M5 confirmations, not just 450 failures:
        # the last-bar gate state is not representative of the full day.
        if gates.get("m5_confirmed", (None, ""))[0] is True:
            self.m5_passes += 1
            if not self.first_m5_pass:
                self.first_m5_pass = iso
                self.first_m5_pass_gates = ",".join(
                    f"{k}={'T' if v[0] is True else 'F' if v[0] is False else '?'}"
                    for k, v in gates.items())
        for name, (passed, reason) in gates.items():
            status = "TRUE" if passed is True else "FALSE" if passed is False else "UNKNOWN"
            self.last_gate_outcomes[name] = status
            self.last_gate_reasons[name] = _short(reason, 160)
            if status != "TRUE":
                self.failed_gate_counts[name] += 1

    def add_bpu_failure(self, reason: str) -> None:
        self.bpu_failure_reasons[_short(reason, 120)] += 1

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "session": self.session,
            "decided_at": self.decided_at.isoformat(timespec="seconds"),
            "model": self.model, "side": self.side,
            "level": self.level, "score": self.score,
            "feature_positives": list(self.feature_positives),
            "level_count": self.level_count,
            "level_kind": self.level_kind,
            "level_source": self.level_source,
            "level_first_idx": self.level_first_idx,
            "level_last_idx": self.level_last_idx,
            "level_formed_at": self.level_formed_at,
            "level_valid_from": self.level_valid_from,
            "d1_close": self.d1_close,
            "d1_atr": self.d1_atr, "bsu": self.bsu,
            "bsu_reason": self.bsu_reason, "m5_checks": self.m5_checks,
            "missing_intent": self.missing_intent,
            "first_m5": self.first_m5, "last_m5": self.last_m5,
            "last_gate_outcomes": dict(self.last_gate_outcomes),
            "last_gate_reasons": dict(self.last_gate_reasons),
            "last_two_m5": [dict(row) for row in self.last_two_m5],
            "failed_gate_counts": dict(self.failed_gate_counts),
            "bpu1_count": self.bpu1_count, "bpu2_count": self.bpu2_count,
            "bpu_failure_reasons": dict(self.bpu_failure_reasons),
            "bpu_touch": (self.touch_audit.as_dict()
                          if self.touch_audit is not None else None),
            "m5_passes": self.m5_passes,
            "first_m5_pass": self.first_m5_pass,
            "first_m5_pass_gates": self.first_m5_pass_gates,
            "candidate": self.candidate,
        }

    def display_lines(self) -> list[str]:
        """Four short native LEAN log lines per setup, each <=190 chars.

        Big single-line JSON/CSV is usually truncated in the Free
        backtest log viewport. Split genuine source evidence by stage.
        """
        label = f"{self.symbol} {self.session}"
        d1 = (
            f"QWCT D1 {label} {self.model}/{self.side} "
            f"L={self.level:.2f} score={self.score:.2f} "
            f"close={self.d1_close:.2f} ATR={self.d1_atr:.2f} "
            f"src={self.level_source}/{self.level_kind} "
            f"swing={self.level_first_idx}-{self.level_last_idx} "
            f"valid={self.level_valid_from}")
        candles = ",".join(
            f"{row['time'][11:16]}:"
            f"{row['open']:.2f}/{row['high']:.2f}/"
            f"{row['low']:.2f}/{row['close']:.2f}"
            for row in self.last_two_m5) or "no-native-bars"
        m5 = (
            f"QWCT M5 {label} checks={self.m5_checks} "
            f"first={self.first_m5[11:16]} last={self.last_m5[11:16]} "
            f"OHLC={candles} missing_intent={self.missing_intent} "
            f"candidate={'YES' if self.candidate else 'NO'}")
        last_failed = [
            (name, status, self.last_gate_reasons.get(name, ""))
            for name, status in self.last_gate_outcomes.items()
            if status != "TRUE"
        ]
        # Include both specific reason and aggregate count. Never infer
        # approval from a missing/UNKNOWN gate.
        gate_details = "; ".join(
            f"{name}:{status}:{_short(reason, 38)}"
            for name, status, reason in last_failed[:2]) or "none"
        gates = (
            f"QWCT GATES {label} last={gate_details} "
            f"fails={','.join(f'{k}:{v}' for k,v in self.failed_gate_counts.most_common(3))}")
        bpu_reasons = self.bpu_failure_reasons.most_common(1)
        bpu_text = (f"{_short(bpu_reasons[0][0], 42)}:{bpu_reasons[0][1]}"
                    if bpu_reasons else "none")
        bsu = (
            f"QWCT BSU {label} {self.bsu}:"
            f"{_short(self.bsu_reason, 75)} "
            f"BPU1={self.bpu1_count} BPU2={self.bpu2_count} "
            f"invalid={bpu_text}")
        lines = [line[:190] for line in (d1, m5, gates, bsu)]
        # Log the FIRST positive M5 event to explain why a rare valid
        # M5 candle still failed another independent risk/trend gate.
        if self.m5_passes:
            lines.append((
                f"QWCT M5 PASS {label} n={self.m5_passes} "
                f"first={self.first_m5_pass[11:16]} "
                f"gates={self.first_m5_pass_gates}")[:190])
        if self.touch_audit is not None:
            lines.append(self.touch_audit.short_line(
                self.symbol, self.session))
        return lines

    def log_line(self) -> str:
        problems = ",".join(
            f"{k}:{v}" for k, v in self.failed_gate_counts.most_common(4)
        ) or "none"
        latest = ",".join(
            f"{k}={v}" for k, v in self.last_gate_outcomes.items()
            if v != "TRUE"
        )[:180] or "none"
        # Last native M5 per-gate explanation is more actionable than
        # the aggregate 456-bar failures. Keep actual source text short
        # enough that LEAN Free does not silently truncate the message.
        detail = ";".join(
            f"{k}:{_short(self.last_gate_reasons.get(k, ''), 48)}"
            for k, v in self.last_gate_outcomes.items() if v != "TRUE"
        )[:150] or "none"
        m5_ohlc = ",".join(
            f"{row['time'][11:16]}:{row['open']:.2f}/"
            f"{row['high']:.2f}/{row['low']:.2f}/{row['close']:.2f}"
            for row in self.last_two_m5) or "no-native-bars"
        bpu_failure = self.bpu_failure_reasons.most_common(1)
        bpu_text = (
            f"{_short(bpu_failure[0][0], 52)}:{bpu_failure[0][1]}"
            if bpu_failure else "none")
        return (
            f"QWCT TRACE {self.symbol} {self.session} "
            f"{self.model}/{self.side} L={self.level:.2f} "
            f"score={self.score:.2f} D1={self.d1_close:.2f}/ATR={self.d1_atr:.2f} "
            f"levels={self.level_count} "
            f"src={self.level_source}/{self.level_kind} "
            f"swing={self.level_first_idx}-{self.level_last_idx} "
            f"valid={self.level_valid_from} "
            f"features={','.join(self.feature_positives)[:75]} "
            f"BSU={self.bsu}:{_short(self.bsu_reason, 60)} "
            f"M5={self.m5_checks} first={self.first_m5[-14:]} last={self.last_m5[-14:]} "
            f"failed={problems} last_fail={latest} reasons={detail} "
            f"m5_ohlc={m5_ohlc} "
            f"no_intent={self.missing_intent} BPU1={self.bpu1_count} "
            f"BPU2={self.bpu2_count} BPU-invalid={bpu_text} "
            f"candidate={'YES' if self.candidate else 'NO'}"
        )


def summarize_traces(traces: list[SetupTrace], limit: int = 20) -> list[str]:
    if limit < 1:
        raise ValueError("summary limit must be at least one")
    output = [t.log_line() for t in traces[:limit]]
    if len(traces) > limit:
        output.append(
            f"QWCT TRACE omitted {len(traces) - limit} accepted setups; "
            "per-setup Cloud Free log limit reached")
    return output
