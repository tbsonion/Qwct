"""Choose ONE fixed ticker for QuantConnect Focus chart from actual D1 setups.

This is presentation only; changing the chart cannot change a screening
decision, risk gate, BSU level, order, subscription, or signal candidate.
"""
def choose_focus(watchlist, decisions, preferred=""):
    eligible = []
    for symbol in watchlist:
        name = getattr(symbol, "value", symbol)
        decision = decisions.get(symbol)
        if (decision is not None and decision.accepted
                and decision.symbol == name):
            eligible.append((symbol, name, decision))
    if not eligible:
        return None
    preferred = str(preferred).strip().upper()
    for symbol, name, _ in eligible:
        if name == preferred:
            return symbol
    for symbol, _, decision in eligible:
        if decision.model == "bounce":
            return symbol
    return eligible[0][0]
