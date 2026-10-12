"""Read-only LEAN portfolio evidence adapter for M5 risk research.

Uses official native Portfolio, Transactions, Security.Exchange.Hours APIs.
It never infers realized closed trades, period-start balances, protected
stops, cashflows or order execution from an empty account. These required
fields stay None, so risk approval cannot become True. No order calls.
"""
from .risk_research import RiskSnapshot, review_risk


def review_native_lean_risk(algorithm, symbol, intent, observed_at, time_index):
    """Construct partial native evidence; never broker approval.

    `time_index` is the caller's documented ET-aware conversion for LEAN's
    algorithm-local naive DateTime. Native margin buying power is sourced
    for this security and direction, not estimated as cash.
    """
    # A consolidator can publish its completed bar later than its nominal
    # EndTime when sparse ticks/minute data arrive late. Portfolio state
    # observed at that later algorithm time is NOT evidence as-of the bar.
    native_asof = time_index(algorithm.time).to_pydatetime()
    if native_asof != observed_at:
        raise ValueError("native portfolio time is not aligned to completed M5")
    # Delayed import avoids requiring AlgorithmImports in pure-rule tests.
    from AlgorithmImports import OrderDirection

    direction = OrderDirection.BUY if intent.side == "long" else OrderDirection.SELL
    security = algorithm.securities[symbol]
    portfolio = algorithm.portfolio
    # LEAN portfolio.values() contains *all* holdings, not only active
    # universe members. A nonzero quantity must consume one risk slot.
    positions = sum(
        1 for holding in portfolio.values() if float(holding.quantity) != 0)
    # Counting every open order as an ENTRY would be a false statement.
    # We can certify 0 entries only if there are 0 open orders at all.
    # Otherwise their purpose/reservations have not been reconciled.
    pending_orders = list(algorithm.transactions.get_open_orders())
    pending_entries = 0 if not pending_orders else None
    native_close = security.exchange.hours.get_next_market_close(
        algorithm.time, extended_market_hours=False)
    snapshot = RiskSnapshot(
        equity=float(portfolio.total_portfolio_value),
        available_buying_power=float(portfolio.get_buying_power(symbol, direction)),
        current_positions=positions,
        pending_entries=pending_entries,
        reserved_open_risk=None,  # STOP exposure must be verified from native orders
        daily_realized_pnl=None, weekly_realized_pnl=None,
        monthly_realized_pnl=None,
        losing_trades_today=None, winning_trades_today=None,
        entries_today=None, consecutive_losing_days=None,
        pause_days_remaining=None,
        daily_start_equity=None, weekly_start_equity=None,
        monthly_start_equity=None, period_cashflows_verified=None,
        exchange_close=time_index(native_close).to_pydatetime(),
        asof=observed_at,
    )
    return review_risk(
        snapshot, side=intent.side, shares=intent.shares,
        entry_price=intent.limit_price, stop_price=intent.stop_price,
        cfg=algorithm.cfg)
