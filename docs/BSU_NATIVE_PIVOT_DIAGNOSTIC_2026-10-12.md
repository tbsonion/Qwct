# Qwct — BSU RAW/SCALED_RAW one-session diagnostic (2026-10-12)

**Research only; NO ORDERS.** This audit does not unblock BSU, round prices, replace Gerchik levels, or claim a confirmed setup.

## Source changes
- `strategy/bsu_bridge.py::audit_bsu_price_basis`: pure read-only examination of **one original swing pivot** in the already loaded `SCALED_RAW` D1 frame against the **same trade date** in native `RAW` `TradeBar` History.
- `main.py`: runs **exactly one extra** native 180-D1-bar `History[TradeBar]` request only for accepted **NVDA bounce on 2024-01-02** (at the 09:29 a.m. ET frozen scenario), then writes one `QWCT BSU BASIS` log. No per-M5 History, no live SEC, no orders.
- `tests/test_bsu_price_basis_audit.py`: rejects missing/duplicate/future RAW bars and native EndTime mismatches. Checks 24-.py bundle and that all orders remain disabled.

## How to run in Cloud Free
1. Keep existing `research.ipynb`. Deploy the fresh **24-file generated package**, or replace only **`main.py` and `strategy/bsu_bridge.py`** if the current Cloud project is the previous complete 24-file package.
2. Start backtest at **2024-01-01** / end **2024-02-05**, `tvx_seconds` **OFF**.
3. Find a single `QWCT BSU BASIS NVDA ...` line and `QWCT BSU BLOCKED NVDA ...` line. If `QWCT BSU BASIS UNVERIFIED` appears, capture the exact reason; **do not infer parity**.
4. Share the full lines. Interpret fields:
   - `pivot_date` and `pivot_end`: first actual confirmed swing bar, not the median of the cluster.
   - `raw`: original same-date RAW trade high/low; `scaled`: corresponding SCALED_RAW high/low; `cluster`: scenario D1 median, a distinct value.
   - `raw_off` and `scaled_off`: absolute difference between price and nearest native `minimum_price_variation` grid point, **in dollars**, not ticks.
   - `factor_scaled/raw`: *observed ratio*, **NOT proof** of which corporate action/factor produced it.
   - `last`, `raw_close`, `scaled_close`: most recent completed D1 comparison; `bars`: historical RAW bar count.
5. Check `Qwct research summary`, **ERROR=0**, orders disabled, model counts unaffected. No requirement that BPU1 signals suddenly appear.

## Next decision after actual Cloud output
- If `raw_off` is close to zero but `scaled_off` materially nonzero, determine which split/dividend transformations make pivot and M5 comparable, using only native as-of factors and stock exchange events. Preserve strict exact-touch and adapt **data basis**, not thresholds.
- If both are off-grid or no origin match, investigate dataset/vendor precision, exchange native tick at **historical** date, origins/cluster lookback, and native daily timestamps.
- If native RAW request unavailable, investigate official `History[TradeBar]` API/data entitlement. Do not fabricate RAW pivot.

Docs: [US Equity Data Normalization](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data), [History Requests](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-requests).

**Not tested here:** native Cloud execution of this changed version; Schwab fills; profitability; split-spanning portfolio/indicator rewarm. Order execution remains hard-disabled.
