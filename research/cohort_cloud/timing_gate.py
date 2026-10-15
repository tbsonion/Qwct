"""QWCT read-only Fundamental weekend/holiday callback gate.

LEAN supplies the exchange calendar and historical callback timestamps.
No homemade holiday rules or hindsight universe membership.
"""
from datetime import timedelta


def next_session_fundamentals(events, now, market_hours, localize):
    """Return one observed callback valid for its native next market open.

    The symbol list was already frozen by the LEAN Fundamental selector.
    Inputs now and event timestamps are aware exchange-local datetime.
    """
    due = []
    for event in events:
        at = event["at"]
        if at.tzinfo is None or now.tzinfo is None or not at < now:
            continue
        if at.date() >= now.date() or now - at > timedelta(days=5):
            continue
        if not event["symbols"]:
            continue
        # All selected Fundamental objects need actual source EndTime.
        lo, hi = event["source_min"], event["source_max"]
        if (not event["complete"] or lo is None or hi is None
                or lo.tzinfo is None or hi.tzinfo is None
                or not at - timedelta(days=2) <= lo <= hi <= at):
            continue
        try:
            # LEAN Exchange.Hours expects exchange-local naive DateTime.
            local = at.replace(tzinfo=None)
            if market_hours.is_date_open(local, extended_market_hours=False):
                continue
            next_open = localize(market_hours.get_next_market_open(
                local + timedelta(seconds=1), extended_market_hours=False))
        except Exception:
            continue
        if (next_open.date() != now.date()
                or not now < next_open or not at < next_open):
            continue
        due.append(event)
    if len(due) != 1:
        return None, ("NO_VERIFIED_NEXT_SESSION" if not due
                      else "AMBIGUOUS_NEXT_SESSION_CALLBACKS")
    return due[0], "VERIFIED_NEXT_EXCHANGE_SESSION"
