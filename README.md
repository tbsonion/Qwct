# Qwct — Gerchik D1/M5 research on QuantConnect LEAN

**Current status (2026-10-12): RESEARCH ONLY. ALL ORDERS DISABLED.**

**Canonical current backlog:** [TODO.md](TODO.md) — status of every subsystem, verification criteria, outstanding deep research, and release gates. The dated reports under `docs/` are **historical snapshots**; some say no LEAN run was performed or refer to old draft PRs. Do not treat them as current status.

## What was actually verified in Cloud

User-supplied QuantConnect Cloud signal-only backtest, LEAN 2.5.0.0.18178, 2024-01-01 to 2024-02-05:

| Measure | Observed |
| --- | ---: |
| Processed data points | 1,233,385 |
| Native M5 bars processed | 18,240 |
| Accepted D1 scenarios | 6 |
| M5 evaluations | 456 |
| Two-bar M5 proxy passes | 6 |
| Native BPU1 | **0** |
| Confirmed SEC TVX -30s | **0** (disabled) |
| Research candidates / trade intents | **0 / 0** |
| Runtime errors | **0** |

The standard LEAN equity curve remains flat **because orders are intentionally disabled**. No win rate, Sharpe, expected monthly returns, or executable trade P&L has been established.

**BSU price-basis status (2026-10-13):** native Cloud (LEAN 2.5.0.0.18179) verified the 2024-01-02 NVDA D1 original pivot from 2023-08-24: **RAW high $502.66**, **SCALED_RAW high $502.57439794**, native tick **$0.01**; RAW offset = 0, scaled offset = $0.00439794, latest completed D1 closes agree ($495.22). The historical cluster median is distinct from the original pivot. The research bridge now uses a native RAW historical origin only after strict as-of pivot/latest-date, EndTime, symbol, tick and latest-close reconciliation, and always fails closed on missing evidence. **Verified in LEAN Cloud 2.5.0.0.18179 (2026-10-13):** on 2024-01-02 NVDA, the RAW bridge **armed** with original high **$502.66** and the normalization BSU block disappeared (BSU block reasons `{}`, `ERROR=0`). The native M5 touch audit found **0 exact touches in 76 M5 bars**: highest M5 high was **$493.00**, $9.66 below the BSU pivot. Thus **BPU1=0, BPU2=0, research candidates=0, intents=0** is an expected *no-touch observation*, not a remaining price-normalization error. Not a certified Gerchik setup, no orders or P&L.

## Design constraints

- **Use official LEAN** for subscriptions, fundamental universes, native ATR/SMA, consolidators, History, Exchange.Hours, Portfolio, scheduled events and (later) broker executions. No synthetic fills, homemade OrderManager/OMS, shadow portfolio, software OCO, or parallel brokerage connector.
- `main.py`: dynamic US stock universe → D1 premarket frozen levels and scenarios → completed M5 research → optionally native SEC/-30s research. Strict `risk_approved` UNKNOWN prevents trade intents; no actual orders are placed.
- `strategy/`: original Gerchik-specific levels/features/scenarios/signals, BSU/BPU1/BPU2 proxy, native SEC research, read-only risk checks, diagnostics.
- Maximum 50 fundamental candidates / 10 D1-qualified research watchlist (not a guaranteed all-market scanner); RVOL comparator exists **but is not connected** to screening.
- Existing native EOD cancel/flat verification code is **disabled** and **not broker verified**. The first contemplated trading target is single **3R**, not 70/20/10; partial-fill protective-stop compatibility must be proven before execution.
- The Gerchik course reference is [docs/strategy_spec.md](docs/strategy_spec.md). Algorithmic swing levels and two-bar M5 tests are **research proxies**, not proof of equivalence to annotated course examples.

## Run pure source tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

GitHub CI is not a LEAN/Schwab runtime test. Pure tests cannot prove native market data precision, broker support, actual execution, or profitability.

## QuantConnect Cloud Free package

Do not hand-edit or delete canonical `strategy/*.py` to fit the editor quota. Generate the deployable **24-Python-file** Cloud package; keep the existing `research.ipynb` as the 25th project file:

```bash
python tools/package_quantconnect_free.py --output dist/Qwct-QuantConnect-Free-24py.zip
```

Deploy the *entire generated bundle* together when syncing a new Cloud project, not a mixture of old/new import layouts. Live and paper brokerage orders must remain disabled.

## Documentation / next work

- **[TODO.md](TODO.md)** — single current project plan and research questions.
- **[Ready-made LEAN research](docs/READY_BUILT_LEAN_RESEARCH_2026-10-12.md)** — official native RDV, pivot points, RAW/SCALED_RAW diagnostic approach, seconds, risk, Schwab contingent-order constraints, and what NOT to rebuild.
- [strategy specification](docs/strategy_spec.md)
- [historical corporate-action/tick-grid investigation](docs/NVDA_BSU_RAW_ASOF_2026-10-12.md)
- [native SEC -30s Cloud smoke protocol](docs/LEAN_CLOUD_TVX_30S_SMOKE_2026-10-11.md)
- [deep source-vs-LEAN-vs-Gerchik audit](docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md)
- [native Schwab compatibility notes](docs/SCHWAB_LEAN_COMPATIBILITY_2026-10-09.md)

**Next research:** locate independently verifiable historical bounce sessions where native RAW M5 reaches the reconciled RAW D1 pivot, then investigate BPU1→BPU2 and actual second-resolution TVX separately. Do not lower exact-touch constraints, invent signals, or enable orders to compensate for NVDA's $9.66 no-touch gap. Independent annotated Gerchik-level and corporate-action/factor validation remain outstanding.
