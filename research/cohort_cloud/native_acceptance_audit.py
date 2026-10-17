"""Read-only native M1/M5 coverage and acceptance-evidence accounting.

No synthetic bars, fill-forward, historical TVX authorization, risk changes,
signals or orders. Works on already returned native LEAN TradeBars.
"""
from datetime import datetime, timedelta
from math import isfinite


def native_minute_coverage(bars, session_open, session_close, time_index=None):
    """Inspect real native M1 starts and identify missing 5-minute buckets.

    The expected grid is a *clock*, not fabricated OHLC data. Missing
    observations remain missing. Return only JSON-safe primitive values.
    """
    if (not isinstance(session_open, datetime)
            or not isinstance(session_close, datetime)
            or session_open.tzinfo is None or session_close.tzinfo is None
            or session_open.utcoffset() is None
            or session_close.utcoffset() is None
            or session_close <= session_open
            or (session_close-session_open).total_seconds() % 300 != 0):
        raise ValueError("INVALID_NATIVE_SESSION_WINDOW")
    total = int((session_close-session_open).total_seconds()//60)
    if total > 390:
        raise ValueError("SESSION_EXCEEDS_REGULAR_EQUITY_DAY")
    seen = set()
    invalid = []
    for bar in bars:
        try:
            start, end = bar.time, bar.end_time
            # Use caller's existing LEAN-to-ET adapter.
            if time_index is not None:
                start, end = time_index(start), time_index(end)
            start = start if isinstance(start, datetime) else None
            end = end if isinstance(end, datetime) else None
            if start is None or end is None:
                invalid.append("NATIVE_TIMESTAMP_NOT_PYTHON_DATETIME")
                continue
            if (start.tzinfo is None or end.tzinfo is None
                    or end-start != timedelta(minutes=1)
                    or start < session_open or end > session_close
                    or (start-session_open).total_seconds() % 60 != 0
                    or getattr(bar, "is_fill_forward", False)
                    or not isfinite(float(bar.volume))
                    or float(bar.volume) <= 0):
                invalid.append("INVALID_OR_FILL_FORWARD_M1")
                continue
            if start in seen:
                invalid.append("DUPLICATE_NATIVE_M1")
                continue
            seen.add(start)
        except (TypeError, ValueError, AttributeError, OverflowError):
            invalid.append("INVALID_NATIVE_M1")
    missing = [session_open+timedelta(minutes=i)
               for i in range(total)
               if session_open+timedelta(minutes=i) not in seen]
    missing_set = set(missing)
    absent_m5 = [
        session_open+timedelta(minutes=i+5)
        for i in range(0, total, 5)
        if any(session_open+timedelta(minutes=j) in missing_set
               for j in range(i, i+5))
    ]
    return {
        "expected_m1": total, "observed_valid_m1": len(seen),
        "missing_m1": [x.strftime("%H:%M") for x in missing],
        "expected_complete_m5": total//5,
        "m5_buckets_with_missing_m1": [x.strftime("%H:%M")
                                       for x in absent_m5],
        "invalid_source_rows": len(invalid),
        "source_errors": sorted(set(invalid)),
        "status": ("PASS" if not missing and not invalid else "INCOMPLETE"),
    }


def acceptance_evidence_status(*, strict_bpu1, strict_bpu2,
                               native_cutoff_observed=False,
                               preclose_asof_verified=False,
                               canonical_bsu_verified=False,
                               features_evaluated=False,
                               gates_evaluated=False):
    """Do not promote a retrospective BPU2 into a real -30s TVX.

    This cohort runner cannot observe a live native SECOND cutoff, so
    callers must leave the corresponding arguments False. The booleans
    represent *evidence observed*, not predictions.
    """
    if strict_bpu2 and not strict_bpu1:
        raise ValueError("BPU2_WITHOUT_STRICT_BPU1")
    tvx = ("PASS" if native_cutoff_observed and preclose_asof_verified
           else "UNKNOWN")
    accepted = (canonical_bsu_verified and strict_bpu1 and strict_bpu2
                and tvx == "PASS")
    return {
        "bpu1": "PASS" if strict_bpu1 else "UNKNOWN",
        "bpu2": "PASS" if strict_bpu2 else "UNKNOWN",
        "tvx_30s": tvx,
        "canonical_bsu": "PASS" if canonical_bsu_verified else "UNKNOWN",
        "accepted_setup": "PASS" if accepted else "UNKNOWN",
        "features_14": ("PASS" if accepted and features_evaluated
                        else "UNKNOWN"),
        "gates_8": ("PASS" if accepted and gates_evaluated
                    else "UNKNOWN"),
        "orders": "DISABLED",
    }
