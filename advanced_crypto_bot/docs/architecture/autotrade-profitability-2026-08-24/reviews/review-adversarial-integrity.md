# Adversarial Integrity Review — Autotrade Dry-Run Profitability

**Reviewed:** `ARCHITECTURE-SPINE.md` (draft, 2026-08-24)  
**Lens:** downstream consistency, data integrity, entity ownership, mutation paths,
experiment isolation, and risk/accounting semantics  
**Verdict:** **CONDITIONAL / not yet a sufficient build substrate**

The spine has the right high-level boundaries and strong intent, but its rules do
not yet force independently implemented units to agree on the data model or on
financial semantics. Two implementations can obey every stated AD and still
produce irreconcilable ledgers, different equity and drawdown, and incomparable
champion/challenger results. The missing pieces should be resolved as binding
contracts before parallel implementation begins.

## Adversarial construction: two compliant but divergent units

The following units both satisfy AD-1 through AD-10 as written.

| Concern | Unit A — portfolio-centric projection | Unit B — order-centric projection |
| --- | --- | --- |
| Decision payload | One decision row per `(experiment_id, snapshot_id, strategy_version, pair)`; `intent` embeds requested base quantity and one reason code | One decision aggregate per candidate; child intents permit staged entries and multiple reason/evidence records |
| Fill identity | Fill journal key is simulator-generated fill ID; a retry is deduplicated by decision idempotency key | Fill journal key is `(order_id, fill_sequence)`; a decision may generate replacement orders and many fill streams |
| Position ownership | One net position per `(experiment_id, strategy_version, pair)`; buys and sells update weighted-average cost | Tax lots per `(portfolio_id, pair)`; sells use FIFO and positions are an aggregate projection |
| Cash mutation | Reserve full quote amount when an intent becomes a pending order; release remainder on expiry | Do not mutate or reserve ledger cash until a fill occurs; pending buying power is a risk-layer projection |
| Fees and precision | Buy fee is capitalized into average entry cost; base received is reduced where exchange convention requires | Every fee is a separate IDR ledger posting; base quantity remains gross and fee affects realized P&L |
| Event ordering | Simulator appends fills synchronously in snapshot event-time order | Simulator appends fills in ingestion order and records event time independently; late snapshots are accepted |
| Mark to market | Last canonical trade price at or before the valuation snapshot | Executable liquidation bid, including estimated exit fees/slippage |
| Counterfactual | Every rejected intent gets an unconstrained synthetic position independent of portfolio capacity | Rejected intents are simulated only if historical cash, exposure, and pair limits would have admitted them |
| Challenger isolation | Separate `experiment_id` partitions in shared journal and projections | Separate virtual `portfolio_id`s, with multiple experiments allowed to reuse a portfolio baseline |
| Risk state | Daily loss is change in marked equity since UTC midnight; unrealized P&L participates | Daily loss is realized P&L plus fees since experiment-session start; unrealized loss is handled only by drawdown |

Both units can claim compliance:

- Both bind decisions to all AD-1 identity fields and are deterministically replayable.
- Both use an immutable normalized fill journal as the sole accounting authority and
  update their chosen projections atomically (AD-2).
- Both keep policies pure and produce terminal attributed decisions (AD-3/AD-4).
- Both label accepted and rejected candidates over equal horizons using their single,
  shared simulator implementation (AD-5/AD-6).
- Both can perform disjoint walk-forward analysis (AD-7), calculate an equity made of
  virtual cash plus marked open positions (AD-8), run under one VM writer (AD-9), and
  isolate challengers according to their own interpretation (AD-10).

Nevertheless, Unit A and Unit B disagree on available cash, position quantity,
cost basis, realized P&L, equity, drawdown, circuit-breaker activation, candidate
labels, and promotion results. Their records also cannot be losslessly exchanged
without implementation-specific inference. This is a contract failure, not merely
an implementation choice.

## Findings

### 1. Critical — No canonical schemas or aggregate keys bind the architecture

AD-1 specifies fields but not a canonical decision/event envelope, field types,
cardinality, serialization, hash algorithm, or identity scope. The conventions do
not define whether `strategy_version` is code, policy parameters, or both; whether
`snapshot_id` identifies one pair or a cross-pair observation; whether an
`experiment_id` has exactly one portfolio; or whether `operation` distinguishes a
candidate, decision, order, or fill. Lowercasing a pair and using ISO time is not
enough to make records interoperable.

**Integrity risk:** semantically different events can collide under the suggested
identity string, while semantically identical inputs can hash differently due to
decimal, timestamp, map-order, or omitted/default-field serialization. Duplicate
candidate decisions or cross-experiment fill attribution can then pass local
idempotency checks.

**Required binding decision:** define versioned schemas and ownership keys for
`MarketSnapshot`, `Candidate`, `Decision`, `TradeIntent`, `SimulatedOrder`, `Fill`,
`LedgerPosting`, `PositionProjection`, `Valuation`, and `OutcomeLabel`. Specify
canonical serialization, decimal scale/rounding, ID derivation, required partition
keys, causal links, and uniqueness constraints. State the cardinality chain from
snapshot through fill and label.

### 2. Critical — “Fill journal is the accounting authority” is not a complete ledger contract

AD-2 names an authority but leaves the economic posting model undefined. A fill
alone cannot reconstruct cash correctly without binding fee currency, fee timing,
gross/net quantity, precision/rounding residuals, funding deposits, reservations,
expiry releases, and corrections. Nor does the spine choose net positions versus
lots or a realized-cost-basis method. “Derived atomically” does not resolve which
projection is correct.

**Integrity risk:** conservation laws can silently fail. Cash and asset movements
may be counted twice, fees can disappear into cost basis, and replay after a code
change can yield a different balance from the same journal. Atomic wrong math is
still wrong math.

**Required binding decision:** either adopt a balanced double-entry virtual ledger
whose postings are generated from immutable fills and non-trade funding events, or
fully specify equivalent conservation equations. Define gross/net quantities, fee
assets, rounding policy, lot relief, realized/unrealized P&L, reservation semantics,
correction/reversal events, and replay/version-upgrade behavior. Persist accounting
rule version on each posting batch.

### 3. High — Experiment isolation is asserted but its namespace and ownership model are ambiguous

AD-10 says a challenger owns an isolated portfolio, while AD-1 centers experiment
identity and AD-9 mentions isolated experiment namespaces. The spine does not say
whether portfolio ownership is one-to-one with experiment, strategy, run, or
capital baseline. It also does not require namespace columns and composite foreign
keys on orders, fills, projections, risk state, labels, queues, caches, or leases.

**Integrity risk:** an unqualified `pair`, `order_id`, or idempotency key can mutate
another experiment's projection. A shared Redis queue/cache can route a champion
fill to a challenger, and a restarted experiment can inherit cash, pending orders,
or circuit-breaker state. A single runtime writer prevents concurrent hosts; it does
not prevent logical cross-tenant contamination.

**Required binding decision:** establish an explicit ownership hierarchy, for
example `run -> experiment -> virtual_portfolio -> order -> fill`, and require the
complete namespace in primary keys, foreign keys, queue subjects, leases, cache
keys, reconciliation queries, and metrics. Define initial funding and clone/reset
semantics. Enforce that a strategy may read only an immutable as-of portfolio view
belonging to its portfolio and that execution can write only within that namespace.

### 4. High — Mutation ordering and idempotency stop at the decision boundary

AD-1 requires a decision idempotency key and AD-2 requires one SQLite transaction
for fill append plus projection update, but there is no binding state machine or
idempotency contract for intent, order, partial fill, expiry, replacement,
protection, exit, and reconciliation. Event time and ingestion time are stored, yet
the authoritative ordering rule for late, duplicate, or same-time events is absent.

**Integrity risk:** retries can create two orders from one decision; an expiry can
race with a partial fill; fills can be applied in different order after replay; and
projection rebuilds can disagree with online state. SQLite's transaction boundary
does not protect transitions spanning a queue delivery and separate simulator
invocation.

**Required binding decision:** publish the order/position lifecycle as a legal
transition table with aggregate owner, expected prior version, command idempotency
key, deterministic event sequence, terminal states, and correction path. Define
inbox/outbox semantics across Redis/SQLite and uniqueness constraints for every
append operation. Specify replay ordering as a total order independent of arrival.

### 5. High — Risk, valuation, and counterfactual semantics allow incompatible profitability claims

AD-5 requires “same executable prices and cost model,” but does not decide whether
counterfactuals are capacity-constrained, whether simultaneous rejected candidates
compete for cash/liquidity, or how partial fills and exits are paired. AD-8 does not
define the mark source/as-of rule, stale-price handling, cost basis, day boundary,
peak-equity reset, pending exposure, fee accrual, or whether liquidation costs enter
equity. The diagram also places risk downstream of projections, leaving pre-trade
admission ownership unspecified.

**Integrity risk:** two reports can both be “net of costs” yet answer different
questions. One can show signal edge using unconstrained labels while another shows
portfolio feasibility. Different valuation marks can trip or suppress the circuit
breaker and alter future trades, making promotion results non-comparable.

**Required binding decision:** separate and name (a) unconstrained signal labels,
(b) capacity/risk-constrained counterfactual portfolios, and (c) realized simulated
portfolio results. Define the valuation policy and its version, as-of and staleness
rules, pending exposure, daily-loss timezone/baseline, drawdown peak lifecycle,
protective-exit classification, and pre-/post-trade risk APIs. Promotion must name
which metric family is authoritative and reconcile it to ledger-derived equity.

## Minimum acceptance bar before implementation fan-out

The spine is ready for parallel downstream construction only when one normative
contract (or explicitly bound companion specification) provides:

1. Versioned entity/event schemas, aggregate ownership, causal IDs, and database
   uniqueness/foreign-key constraints.
2. Accounting posting equations and valuation/risk definitions with executable
   invariants (cash/asset conservation, replay equivalence, and projection rebuild).
3. A namespaced lifecycle state machine with idempotent command handling and a total
   event-order rule.
4. Explicit experiment funding/reset/isolation semantics across SQLite, Redis,
   caches, queues, and metrics.
5. Distinct counterfactual metric families and a single promotion interpretation.

Until these are binding, the ADs are valuable design principles but insufficient
to guarantee that independently built components form one coherent profitability
platform.
