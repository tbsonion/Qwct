# AGENTS.md — Qwct

## Fixed architecture

This repository is an official QuantConnect LEAN Python algorithm with
portable Gerchik-specific signal modules. NEVER create or migrate:
- OrderManager / BrokerAdapter / NativeGateway / MockBroker
- Software OCO, separate ticket state machines, fill simulations, shadow
  portfolio / cash / broker reconciliation
- Homemade exchange holidays/schedules, SMA, ATR, feed/consolidator systems.

Use native LEAN Portfolio, buying-power model, OrderTickets, Transactions,
OnOrderEvent, Schedule, Exchange.Hours, History, Consolidate and indicators.

## Current stage

Only coding and pure unit checks. No strategy profitability backtests, no
Schwab connection, credentials, paper/live trading, broker orders, or merges
without user instruction. All Qwct paths are signal-only until native LEAN
runtime behavior is validated in an explicitly approved separate phase.
Never claim mock tests demonstrate actual broker behavior.

The first exit requirement in docs/strategy_spec.md is one 3R TP. 70/20/10
is a later research requirement; native Bracket only triggers exits after
complete entry fill. Schwab OUO/update restrictions must be respected:
do NOT implement a manual workaround without express user direction.

Preserve original Gerchik business rules and their explicit fail-closed
behaviors, explain differences from the source in changes, use focused PRs.
