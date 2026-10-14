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

# Cloud Free: include canonical end-of-backtest reporting.
from collections import Counter

def write_reports(self):
    # Official native LEAN runtime statistics survive backtest logging
    # throttling and are available in the result view on Cloud Free.
    counts = Counter(row["type"] for row in self._signal_rows)
    for stat, kind in (("Qwct D1 setups", "SCENARIO"),
                       ("Qwct intents", "INTENT"),
                       ("Qwct rejects", "REJECT"),
                       ("Qwct errors", "ERROR")):
        self.set_runtime_statistic(stat, counts[kind])
    self.set_runtime_statistic(
        "Qwct research candidates", counts["RESEARCH_CANDIDATE"])
    self.set_runtime_statistic("Qwct D1 bounce", self._d1_models["bounce"])
    self.set_runtime_statistic("Qwct D1 breakout", self._d1_models["breakout"])
    self.set_runtime_statistic("Qwct D1 false",
                               self._d1_models["false_breakout"])
    self.set_runtime_statistic("Qwct BSU proxy blocked",
                               sum(self._bsu_block_reasons.values()))
    self.set_runtime_statistic("Qwct native BPU1", self._bsu_bpu1_count)
    self.set_runtime_statistic(
        "Qwct native SEC feed bars", getattr(self, "_native_sec_received", 0))
    preclose_reviews = [
        row for row in self._signal_rows
        if row["type"] == "TVX_PRECLOSE_REVIEW"]
    self.set_runtime_statistic(
        "Qwct as-of TVX -30s reviews", len(preclose_reviews))
    self.set_runtime_statistic(
        "Qwct as-of TVX observable",
        sum(str(row["reason"]).startswith("OBSERVABLE_READY")
            for row in preclose_reviews))
    self.set_runtime_statistic(
        "Qwct split quarantine", counts["SPLIT_RESEARCH_BLOCKED"])
    self.set_runtime_statistic(
        "Qwct SEC TVX -30s preliminary", self._tvx_preclose_count)
    self.set_runtime_statistic(
        "Qwct SEC TVX closed verified", self._tvx_preclose_reconciled)
    self.set_runtime_statistic(
        "Qwct SEC TVX rejected",
        sum(self._tvx_second_reasons.values()))
    self.set_runtime_statistic(
        "Qwct SEC TVX mode",
        "native SECOND enabled" if getattr(self, "_tvx_seconds_enabled", False)
        else "minute mode / TVX unobserved")
    self.set_runtime_statistic(
        "Qwct BPU invalidations", sum(self._bpu_invalid_reasons.values()))
    self.set_runtime_statistic(
        "Qwct chart focus", self._chart_symbol.value
        if self._chart_symbol is not None else "none")
    self.set_runtime_statistic(
        "Qwct focus M5 plotted", self._focus_m5_plotted)
    top_bsu = (
        self._bsu_block_reasons.most_common(1)[0]
        if self._bsu_block_reasons else None)
    top_gate = (
        self._gate_failures.most_common(1)[0]
        if self._gate_failures else None)
    self.set_runtime_statistic(
        "Qwct top BSU blocker",
        (f"{top_bsu[0][:60]} ({top_bsu[1]})" if top_bsu
         else ("no D1 bounce" if self._d1_models["bounce"] == 0
               else "none")))
    self.set_runtime_statistic(
        "Qwct top M5 gate",
        f"{top_gate[0]}:{top_gate[1]}" if top_gate else "none")
    self.set_runtime_statistic(
        "Qwct BSU swing proxies armed", self._bsu_proxy_armed_count)
    self.set_runtime_statistic(
        "Qwct closed M5 BPU2 proxies", self._bsu_proxy_bpu2_count)
    self.set_runtime_statistic("Qwct M5 bars", self._m5_bars_seen)
    self.set_runtime_statistic(
        "Qwct breakout retest confirmed",
        self._breakout_retest_counts["CONFIRMED"])
    self.set_runtime_statistic(
        "Qwct breakout waiting retest",
        self._breakout_retest_counts["WAIT_RETEST"])
    self.set_runtime_statistic(
        "Qwct breakout retest expired",
        self._breakout_retest_counts["EXPIRED"])
    self.set_runtime_statistic(
        "Qwct breakout invalidated",
        self._breakout_retest_counts["INVALIDATED"])
    self.set_runtime_statistic(
        "Qwct M5 feed rejected", sum(self._m5_input_rejections.values()))
    self.set_runtime_statistic("Qwct M5 checks", self._m5_checks)
    self.set_runtime_statistic(
        "Qwct M5 gate passes", sum(self._m5_true_by_model.values()))
    self.set_runtime_statistic(
        "Qwct M5 pass models", str(dict(self._m5_true_by_model)))
    self.set_runtime_statistic(
        "Qwct M5 pass blockers",
        str(dict(self._m5_true_other_blockers.most_common(4))))
    self.set_runtime_statistic(
        "Qwct traced D1 setups", len(self._setup_traces))
    self.set_runtime_statistic(
        "Qwct trace M5 checks",
        sum(t.m5_checks for t in self._setup_traces))
    self.set_runtime_statistic(
        "Qwct traced setups without M5",
        sum(t.m5_checks == 0 for t in self._setup_traces))
    if not self._object_store_export_enabled:
        if getattr(self, "_case_scan", False):
            cases = getattr(self, "_bsu_scan_best", ())
            self.log(f"QWCT SCAN completed: nearest={len(cases)} "
                     f"BPU1={self._bsu_bpu1_count} "
                     f"BPU2={self._bsu_proxy_bpu2_count}; NO ORDERS")
            a = self._scenario_evaluator.scan_model_audit
            self.log(
                "QWCT D1 BOUNCE AUDIT "
                f"nearby={a['nearby_evaluated']} "
                f"eligible_level={a['bsu_level_present']} "
                f"scored_ge_threshold={a['bounce_scored_eligible']} "
                f"below_threshold={a['bounce_below_threshold']} "
                f"outscored={a['bounce_outscored']} "
                f"tie_lost={a['bounce_tie_lost']} "
                f"selected={a['selected_bounce']} "
                f"no_eligible_level={a['no_bsu_eligible_level']}; "
                "read-only / no selection change")
            for _, ticker, day, level, extreme, gap, at, exact in cases:
                self.log(f"QWCT SCAN NEAREST {ticker} {day} pivot={level:.4f} "
                         f"M5={extreme:.4f} gap={gap:+.4f} "
                         f"at={at} exact={exact}")
            bpu_events = [r for r in self._signal_rows if r["type"] in
                          ("BSU_PROXY_BPU1", "BSU_PROXY_BPU2_CLOSED")]
            for row in bpu_events[:4]:
                self.log(f"QWCT SCAN EVENT {row['type']} "
                         f"{row['symbol']} {row['time_et']} "
                         f"pivot={row['level']}; NO ORDERS")
            if len(bpu_events) > 4:
                self.log(f"QWCT SCAN more BPU events={len(bpu_events)-4}")
        # The Free cloud plan has no ObjectStore write permission.
        # Emit only a short end-of-run count; DO NOT claim the complete
        # decision journal was saved (it remains in-memory only).
        reject_reasons = Counter(
            "insufficient D1" if row["reason"] == "insufficient closed D1"
            else "no nearby levels" if "нет уровней рядом" in row["reason"]
            else "model score below threshold" if "скор " in row["reason"]
            else "other" for row in self._signal_rows
            if row["type"] == "REJECT")
        self.log(
            "Qwct research summary: "
            + ", ".join(f"{key}={counts[key]}" for key in
                        ("SCENARIO", "RESEARCH_CANDIDATE", "INTENT",
                         "REJECT", "ERROR"))
            + f"; M5 bars={self._m5_bars_seen}, "
              f"M5 feed rejects={dict(self._m5_input_rejections.most_common(3))}, "
              f"M5 bar checks={self._m5_checks}, "
              f"unready={self._intent_missing_atr}"
            + "; D1 models=" + str(dict(self._d1_models))
            + "; breakout lifecycle=" +
              str(dict(self._breakout_retest_counts))
            + "; BSU block reasons=" +
              str(dict(self._bsu_block_reasons.most_common(7)))
            + f"; native BPU1={self._bsu_bpu1_count}"
            + f"; TVX -30s SEC={self._tvx_preclose_count},"
              f" verified={self._tvx_preclose_reconciled}"
            + "; SEC rejects=" + str(dict(self._tvx_second_reasons.most_common(3)))
            + "; BPU invalid reasons=" +
              str(dict(self._bpu_invalid_reasons.most_common(5)))
            + f"; chart focus={self._chart_symbol.value if self._chart_symbol else 'none'}"
            + f"; chart M5 drawn={self._focus_m5_plotted}"
            + "; daily rejects=" + str(dict(reject_reasons))
            + "; failed M5 gates=" +
              str(dict(self._gate_failures.most_common(8)))
            + "; M5 gate pass models=" + str(dict(self._m5_true_by_model))
            + "; other gates when M5 passed=" +
              str(dict(self._m5_true_other_blockers.most_common(6)))
            + "; ObjectStore DISABLED: decision CSV/JSON NOT saved."
        )
        # Keep the entire Free backtest below ~10 KB and make the
        # aggregate summary visible before more expensive per-setup lines.
        for trace in self._setup_traces[:8]:
            for line in trace.display_lines():
                self.log(line)
        if len(self._setup_traces) > 8:
            self.log(
                f"QWCT TRACE viewer limit: omitted "
                f"{len(self._setup_traces) - 8} retained accepted setups")
        if self._setup_traces_omitted:
            self.log(
                f"QWCT TRACE memory cap: {self._setup_traces_omitted} "
                "additional accepted D1 setups not retained")
        return
    # LEAN TradeBuilder owns the realized P&L and round-trip grouping.
    trades = native_closed_trade_rows(self.trade_builder.closed_trades)
    outputs = {
        "signal_decisions.csv": csv_rows(self._signal_rows, SIGNAL_FIELDS),
        "native_order_events.csv": csv_rows(
            self._order_event_rows, ORDER_FIELDS),
        "native_closed_trades.csv": csv_rows(trades, TRADE_FIELDS),
        "summary.json": summary_json(
            self._signal_rows, self._order_event_rows, trades,
            self.portfolio.invested),
    }
    # LEAN ObjectStore: save at algorithm end to avoid constant writes.
    # A unique AlgorithmId avoids overwriting another backtest's results.
    prefix = f"{self.project_id}/{self.algorithm_id}/gerchik"
    for filename, body in outputs.items():
        try:
            if not self.object_store.save(f"{prefix}/{filename}", body):
                self.error(f"ObjectStore could not save {filename}")
        except Exception as exc:
            self.error(f"ObjectStore error saving {filename}: {exc}")
    self.log(f"Gerchik journal and trade report: {prefix}")
