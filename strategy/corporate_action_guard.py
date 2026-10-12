"""Native LEAN Split event quarantine and original-LEAN-history rewarm.

Only LEAN SplitType.SPLIT_OCCURRED triggers. Never invent a
historical split factor, a corrected quote, a feed, or adjusted
indicators. When a split actually occurs, clear the old intraday
signal and let main.py recreate the official native consolidators,
indicators and 180-day SPLIT_ADJUSTED History at the next morning.
The entire affected session stays blocked; no trade authorization.
"""
from datetime import date


def process_native_split_events(self, data, split_occurred):
    splits = getattr(data, "splits", None)
    if splits is None:
        return
    for symbol, event in splits.items():
        if getattr(event, "type", None) != split_occurred:
            continue
        state = self._symbols.get(symbol)
        if state is None:
            # An unregistered stock cannot have an active BPU trade.
            continue
        event_day = self.time.date()
        if state.get("split_blocked_date") == event_day:
            continue
        state["split_blocked_date"] = event_day
        state["split_rewarm_pending"] = True
        state["bsu_link"] = None
        state["tvx_sec_window"] = None
        state["preclose_review"] = None
        state["bsu_tvx_evidence"] = None
        state["breakout_retest"] = None
        state["decision"] = None
        state["qualified_today"] = False
        self._record(
            symbol, "SPLIT_RESEARCH_BLOCKED",
            reason="official LEAN SplitOccurred; invalidate native SEC/"
                   "M5/D1 pattern and rewarm after corporate action; "
                   "NO ORDERS")


def rewarm_split_symbols(self):
    """At the morning schedule, re-create native LEAN state, block today.

    Reuses only the existing algorithm's built-in remove_consolidator,
    registration, and typed history; no homemade corporate price math.
    """
    today = self.time.date()
    for symbol, state in tuple(self._symbols.items()):
        if not state.get("split_rewarm_pending"):
            continue
        for consolidator in (
                state["daily_consolidator"], state["m5_consolidator"]):
            self.subscription_manager.remove_consolidator(
                symbol, consolidator)
        del self._symbols[symbol]
        if not self._register_symbol(symbol):
            raise RuntimeError("native symbol failed to re-register post split")
        self._symbols[symbol]["split_blocked_date"] = today
        self._symbols[symbol]["split_rewarm_pending"] = False
        self._warm_symbols([symbol])
        self._record(
            symbol, "SPLIT_REWARMED_BLOCKED",
            reason="native LEAN D1 history/ATR/SMA/consolidators reset; "
                   "skip split session, then re-evaluate next session; "
                   "NO ORDERS")


def split_research_blocked(state, session_date):
    return state.get("split_blocked_date") == session_date
