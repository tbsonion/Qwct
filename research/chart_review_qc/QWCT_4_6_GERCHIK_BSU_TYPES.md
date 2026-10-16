# QWCT 4.6: Gerchik level-origin research

Eight source families are tracked separately: TREND_TURN, HISTORICAL,
MIRROR, LIMIT_PLAYER, PARANORMAL, CONSOLIDATION, GAP, FLOATING.

Implemented in strategy/gerchik_level_types.py:
- LIMIT_PLAYER: three exact wick hits with no adverse penetration.
- HISTORICAL: repeat of an exact source extremum.
- MIRROR: source on original side, later close across and exact retest.
- PARANORMAL: source bar >= 2 ATR, followed by an exact retest.
- TREND_TURN, CONSOLIDATION, GAP: INDETERMINATE pending specific evidence.
- FLOATING: FLOATING_ZONE.

These are read-only candidates, not author-certified BSU signals. The
classification is not yet connected to QuantConnect research backtests.

Pending: verify original source on actual historical data, complete
unresolved families, and compare with author-labelled chart examples.

References:
https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya
Gerchik, Kurs aktivnogo treidera, chapter on price levels.
