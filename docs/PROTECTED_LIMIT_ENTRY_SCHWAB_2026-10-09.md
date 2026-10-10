# Qwct protected LIMIT entry + stop: Schwab/LEAN feasibility gate

Date: 2026-10-09. Documentation-based, **not a real LEAN run or broker test**.
Stacked on PR #4, which is stacked on #3 and #2. This branch must remain DRAFT.

## Decision

**NOT IMPLEMENTABLE AS A VERIFIED, AUTOMATED MULTI-SHARE PROTECTED ENTRY WITH CURRENT EVIDENCE.**
Do not issue a multi-share limit order and label it "protected" merely
because the native LEAN `bracket_order` method accepts `limit_price`.

Native API **exists**:
- LEAN `self.bracket_order(symbol, quantity, take_profit_price,
  stop_loss_price, limit_price=...)` natively submits a limit parent
  with broker-managed OCO stop/target children.
- Native `self.one_triggers_other_order(parent, [stop])` can attach
  only a protective stop to a limit parent.
- Schwab's QuantConnect integration lists Limit, Stop Market,
  Bracket, OCO and OTO for equities.

But **activation/cancellation semantics prevent claiming continuous
protection**:
1. The OTO/Bracket child stop does not activate until the parent
   limit entry **completely** fills. A 100-share entry filled for 40
   shares may leave 40 shares with no active stop.
2. If the parent is canceled after partial fill, LEAN cancels
   triggered children even though the partial holding can remain.
3. Native OCO cancels its sibling on **any partial** exit fill.
   Example: after buying 100 shares, if TP fills 30, the protective
   stop can be canceled while 70 shares remain.
4. OUO would resize the sibling on partial exit fills, but
   **Schwab explicitly does not support OUO in contingent sets**.
   Its contingent members cannot be updated; cancel/replace is not
   an atomic replacement and is NOT authorized as a homemade workaround.
5. Stop Market is supported but execution at the trigger price is
   not guaranteed; a fixed $50 max realized loss is not guaranteed.
6. Schwab may reject new liquidation while a canceled stop remains
   pending (Position_Sys_0001). Existing disabled EOD logic does not
   make this safe.

## Why this branch has no execution code

`strategy/protected_entry.py` is a **read-only, fail-closed preflight**.
It computes the intended initial 3R target and stop-distance exposure
WITHOUT placing a broker request or simulating a fill. Even the
one-whole-share candidate is marked `can_submit=False`.

The initial strategy requires a single 3R TP in month one. The later
70/20/10 scheme is **not** a reason to add unsupported OUO, synthetic
OCO, a shadow broker ledger, or per-fill manual order scripts.

### Bounded native research candidate — NOT APPROVED

A *single whole-share* limit bracket is worth a real LEAN/Schwab test:
the normal integer-share partial-fill issue may be avoided with 1-share
orders, and the all-or-nothing exit of one whole share avoids partial
OCO exit size. But this DOES NOT prove immediate activation,
broker handling of odd lots, all broker statuses, gap risk or
compatibility with the desired multi-share $50 risk budget.
Scaling to many individual brackets requires broker confirmation of
request consumption and 120 requests/minute / 4,000/day limits.
This is NOT the production solution and MUST NOT be enabled by merely
changing a Python flag.

## Required evidence before adding native order submission

1. **Real LEAN runtime test** with the exact code/version, a real
   `CharlesSchwabBrokerageModel`, and native `bracket_order`
   / `one_triggers_other_order` requests, *without* submitting
   live Schwab orders. Confirm Python API, status events and child
   activation timing. A pure-Python test isn't sufficient.
2. **Broker-behavior evidence**, only with explicit owner approval,
   in a controlled minimal-quantity live Schwab test (Schwab offers
   no paper API): verify true order ownership, native contingent
   acknowledgement, child working time, complete and canceled parent
   transitions. Do not assume QuantConnect paper models Schwab.
3. Prove protection for **partial parent fill**, **partial TP fill**,
   cancellation pending, rejected stop, symbol halts, network outages,
   early close and manual intervention. Any unverified case = NO GO.
4. Verify native Portfolio/Transactions exposure and max positions,
   buying power, risk budget, and final EOD flat on the real brokerage
   before letting an automated Gerchik signal submit any order.
5. No real/paper orders, credential use or merges until separate
   approval; do not replace broker contingent behavior with a custom
   OMS, software OCO or fabricated fills.

## Official sources

- QuantConnect Schwab: https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab
- LEAN Bracket: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders
- LEAN OTO: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/one-triggers-other-orders
- LEAN OCO: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/one-cancels-other-orders
- LEAN OUO: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/one-updates-other-orders
- LEAN stop market: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/stop-market-orders

**Status: researched and a risk preflight implemented; protected broker entry is
NOT implemented, tested, approved or enabled.**
