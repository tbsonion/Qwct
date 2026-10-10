"""Format real LEAN OrderEvents and TradeBuilder closed trades, not synthetic fills.

LEAN Trade.ProfitLoss is GROSS; LEAN Trade.TotalFees is a separate positive
amount. Native TradeBuilder is the only source of completed trade results.
"""
import csv
import io
import json
from decimal import Decimal

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
    "entry_price", "exit_price", "gross_profit_loss", "total_fees",
    "net_profit_loss", "is_win"
)


def csv_rows(rows, columns):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in columns})
    return output.getvalue()


def native_order_event_row(event, tag=""):
    """Only actual LEAN OrderEvent data; do not fabricate a filled order."""
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
    """Read real LEAN Trade.ProfitLoss and Trade.TotalFees, no substitutions."""
    rows = []
    for trade in trades:
        gross = Decimal(str(trade.profit_loss))
        fees = Decimal(str(trade.total_fees))
        rows.append({
            "symbol": str(trade.symbol),
            "entry_time": str(trade.entry_time),
            "exit_time": str(trade.exit_time),
            "direction": str(trade.direction),
            "quantity": str(trade.quantity),
            "entry_price": str(trade.entry_price),
            "exit_price": str(trade.exit_price),
            "gross_profit_loss": str(gross),
            "total_fees": str(fees),
            "net_profit_loss": str(gross - fees),
            "is_win": str(trade.is_win),
        })
    return rows


def summary_json(signal_rows, order_rows, closed_trade_rows, invested):
    """Gross, fees and net MUST stay separate, including negative net trades."""
    gross = sum((Decimal(r["gross_profit_loss"])
                 for r in closed_trade_rows), Decimal(0))
    fees = sum((Decimal(r["total_fees"])
                for r in closed_trade_rows), Decimal(0))
    net_wins = sum(Decimal(r["net_profit_loss"]) > 0
                   for r in closed_trade_rows)
    return json.dumps({
        "signals": sum(r.get("type") == "INTENT" for r in signal_rows),
        "order_events": len(order_rows),
        "closed_trades": len(closed_trade_rows),
        "net_winning_trades": net_wins,
        "closed_trade_gross_profit_loss": float(gross),
        "closed_trade_total_fees": float(fees),
        "closed_trade_net_profit_loss": float(gross - fees),
        "positions_still_open": bool(invested),
        "source": "LEAN OnOrderEvent + TradeBuilder; no fabricated fills",
    }, ensure_ascii=False, sort_keys=True, indent=2)
