# D1 snapshot and exchange-time correctness — Qwct, 2026-10-10

Scope: signal-only code, independent Python fixtures and LEAN official
time and history semantics. No brokerage orders or profitability tests.

## Root causes fixed

1. **D1 levels recalculated for each M5 check.** Previously
   main.py prepared levels before 09:30 to determine the D1 scenario,
   but signals.py recalculated levels_for_session() from a pandas
   DataFrame on every subsequent M5 bar to calculate the next
   blocking level and room >=4R. This could be slow and, if
   underlying D1 history/state ever changed, could disagree with
   the original morning scenario.
   Now main.py freezes the EXACT ordered level set once each morning,
   keeps it with each symbol's session state, and passes it to
   MarketData.session_levels for use by the M5/room gate. Empty
   tuple is a real empty snapshot, NOT permission to reconstruct
   new levels. Pre-confirmation/future-dated levels are filtered.
   The fallback on MarketData(session_levels=None) exists only for
   existing pure-library callers and is not used by main.py.
2. **Untrusted UTC/local timestamps for Gerchik trade windows.**
   SessionPolicy.is_entry_allowed() previously read the .time()
   wall clock without timezone normalization. An input 15:00 UTC
   in February represents 10:00 EST, not 15:00 ET. It could
   accidentally enter a window that was closed in New York.
   Fixed by requiring tz-aware datetimes and converting to
   ZoneInfo('America/New_York') before checking the configured
   session windows. This also accounts for US DST.
3. **Naive timestamps in readonly historical data.**
   MarketData._et() previously implicitly localized missing
   timezones to ET. This can move a D1 cutoff across day boundaries
   if a naive UTC datetime was passed by mistake. All as-of
   views now require a genuine timezone and convert it explicitly.
   m5_asof validates the timestamp even if M5 data is absent.

## Regression evidence

- Red-first CI on the prior source: 4 failing tests,
  82 passing (missing session_levels and incorrect UTC/naive windows).
- Later regressions added for ET vs UTC D1 equivalence, summer DST,
  ambiguous as-of datetimes, M5 data absent, future-dated frozen
  levels, and daily level confirmation.
- All source/pure tests are run by GitHub CI, not Cloud LEAN.

## Known limitations: NOT fixed by this work

- A 'swing_cluster' from existing D1 code is still NOT a
  proven Gerchik BSU. The separate BSU/BPU1/BPU2/TVX observer is
  not hooked into main.py, because it lacks trustworthy
  exact BSU origin/tick size/30s native preclose observations.
- All brokerage orders remain disabled. Native risk manager and
  Schwab partial fill protection are not verified; output events
  should be read as RESEARCH_CANDIDATE, not executable trades.
- D1 native LEAN bars' actual timestamp, split-adjustment parity,
  native tick timestamps, market halts and live session behavior
  still require independent native LEAN integration evidence.
- Data freshness across unusual exchange closures, a
  tick-aligned stop/target and full journal export on Cloud Free
  are separate unresolved tasks.
- Unit tests with fabricated prices cannot prove that real
  Gerchik levels or the M5 classification are profitable or
  that LEAN native callbacks behave as expected.

Repository branch remains draft PR #5 and unmerged.
Official references:
- https://www.quantconnect.com/docs/v2/writing-algorithms/scheduled-events
- https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators
- https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-responses
