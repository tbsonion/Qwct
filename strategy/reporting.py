"""Export LEAN's actual events and completed trades; never simulate fills.

These are formatting functions, not a broker state machine. TradeBuilder and
Transactions remain the sole authorities for fills and closed positions.
"""
import csv
import io
import json

SIGNAL_FIELDS = (
    "time_et", "symbol", "type", "model", "side", "level", "score",
    "entry", "stop", "risk_per_share", "gates", "reason"
)
ORDER_FIELDS = (
    "utc_time", "order_id", "symbol", "status", "direction",
    "fill_quantity", "fill_price", "fee", "tag", "message"
)
TRADE_FIELDS = (
    "symbol", "entry_time", "exit_time", "direction", "quantity",
    "entry_price", "exit_price", "profit_loss", "fees", "is_win"
)


def csv_rows(rows, columns):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in columns})
    return output.getvalue()


def native_order_event_row(event, tag=""):
    """Fields come only from LEAN OnOrderEvent (not synthetic fill records)."""
    return {
        "utc_time": str(event.utc_time),
        "order_id": str(event.order_id),
        "symbol": str(event.symbol),
        "status": str(event.status),
        "direction": str(event.direction),
        "fill_quantity": str(event.fill_quantity),
        "fill_price": str(event.fill_price),
        "fee": str(event.order_fee),
        "tag": tag,
        "message": str(event.message),
    }


def native_closed_trade_rows(trades):
    """TradeBuilder.closed_trades owns the calculation of trade P&L."""
    return [
        {field: str(getattr(trade, field, ""))
         for field in TRADE_FIELDS}
        for trade in trades
    ]


def summary_json(signal_rows, order_rows, closed_trade_rows, invested):
    """Counts and P&L are derived from native TradeBuilder trades only."""
    realized = sum(float(row["profit_loss"]) for row in closed_trade_rows)
    wins = sum(float(row["profit_loss"]) > 0 for row in closed_trade_rows)
    return json.dumps({
        "signals": len([r for r in signal_rows if r.get("type") == "INTENT"]),
        "order_events": len(order_rows),
        "closed_trades": len(closed_trade_rows),
        "winning_trades": wins,
        "closed_trade_profit_loss": round(realized, 2),
        "positions_still_open": bool(invested),
        "source": "LEAN OnOrderEvent + TradeBuilder; no fabricated fills",
    }, ensure_ascii=False, sort_keys=True, indent=2)
