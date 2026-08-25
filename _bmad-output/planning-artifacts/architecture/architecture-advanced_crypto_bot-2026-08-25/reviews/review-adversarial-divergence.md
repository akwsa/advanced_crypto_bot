# Adversarial Divergence Review — Architecture Spine

**Target:** `ARCHITECTURE-SPINE.md` (draft, 2026-08-25)  
**Review lens:** construct pairs of lower-level units that obey the stated ADs locally but remain mutually incompatible at shared-data, ownership, mutation, and failure/recovery boundaries.  
**Verdict:** **FAIL — the spine is directionally strong but not yet a sufficient build substrate.** The invariants prevent many individually unsafe implementations, yet several cross-unit protocols are underspecified. Independent teams can implement every named rule in good faith and still produce a system that cannot compose safely or replay identically.

This review does not dispute the chosen paradigm. It attacks only places where compliance is non-compositional.

## Finding 1 — Deterministic identity is versioned but not canonically encoded

**Severity:** Critical  
**Divergence class:** shared data / replay / idempotency  
**Implicated:** AD-02, AD-06, AD-12, AD-14; Consistency Conventions “Identifiers” and “Numeric values”

### Pair that obeys the ADs but is incompatible

- **Candidate/Decision producer** derives `candidate_id` as SHA-256 over UTF-8 canonical JSON, with sorted object keys, decimal values rendered as normalized strings, and timestamps rendered with `Z`.
- **Replay/OrderCoordinator unit** derives the same versioned deterministic digest over canonical CBOR, stores fixed-point numerics as integers, and renders UTC timestamps with `+00:00`.

Both avoid UUID/wall-clock generation, use deterministic canonical bytes, pin a version, and can reproduce their own results perfectly. They nevertheless generate different Candidate, Decision, Intent, and client-order IDs for the same semantic input. Inbox dedupe, venue idempotency, replay comparison, and causation links consequently disagree.

The word “canonical” does not choose a byte representation. The spine also does not state whether a digest version identifies the hash algorithm only, the serialization profile, or the complete field projection. “Versioned canonical semantic projection/hash” permits each unit to version a different projection.

### Required closure

Define one normative **Canonical Encoding and Identity Contract** containing:

1. exact serialization format/profile, Unicode normalization, map ordering, null/absent treatment, enum representation, timestamp grammar, decimal scale/rounding, and byte encoding;
2. exact input-field projection and domain separator for every deterministic ID kind;
3. digest algorithm and textual storage encoding;
4. compatibility rules when an ID recipe version changes; and
5. cross-language golden vectors consumed by producer, replay, simulator, OrderCoordinator, migration, and projection tests.

Until that exists, deterministic behavior is unit-local rather than system-wide.

## Finding 2 — Allocation-cycle ownership is not an atomic portfolio reservation

**Severity:** Critical  
**Divergence class:** ownership / concurrent mutation  
**Implicated:** AD-03, AD-04, AD-06, AD-11, AD-24

### Pair that obeys the ADs but is incompatible

- **Horizon H1 AllocationCycle** evaluates its complete deterministic cutoff batch against frozen canonical equity, sees pair `BTC_IDR` flat and unowned, and commits an `ENTER` decision with a legal target.
- **Horizon H2 AllocationCycle** evaluates a different deterministic cutoff (or a concurrently prepared cycle) against the same committed starting state, also sees `BTC_IDR` flat and unowned, and commits an `ENTER` decision with a legal target.

Each cycle emits one final decision per Candidate, applies deterministic tie-breaking within its own opportunity set, respects the 10%/40% envelopes, and uses expected sequence on its own Decision/Candidate aggregates. Neither pyramids an existing Position because no Position existed at its read point. Yet the pair violates the intended one-Horizon-per-pair ownership after both commits and can authorize two Intents. The ADs never identify the aggregate whose sequence serializes portfolio allocation, nor require the pair-ownership claim, risk-state transition, Decisions, and outbox records to share one atomic commit.

An implementation that treats `AllocationCycle` as the serialization aggregate and one that treats each `Candidate` as the aggregate both satisfy the prose. They do not compose.

### Required closure

Define a canonical **PortfolioAllocation aggregate/transaction protocol**:

- one namespace key and sequence/CAS covering portfolio risk capacity, pair-to-Horizon ownership, working risk-increasing Intents, and the cycle cutoff;
- an explicit uniqueness invariant for active `(authority_scope_id, portfolio_id, instrument_id)` ownership;
- atomic commit semantics for all final Decisions in the batch (or a deterministic prepare/commit protocol with no executable partial batch);
- conflict behavior: which cycle loses, which canonical `ABSTAIN`/supersession fact is emitted, and whether a losing already-committed Decision can remain executable; and
- recovery rules for a crash after partial materialization.

## Finding 3 — Fill settlement and persisted risk state have no common consistency cut

**Severity:** Critical  
**Divergence class:** shared data / mutation path / safety  
**Implicated:** AD-05, AD-06, AD-10, AD-11, AD-21, AD-24

### Pair that obeys the ADs but is incompatible

- **Settlement unit** atomically appends a canonical Fill, updates cash/exposure aggregate state derived solely from that Fill, and publishes an outbox record. It correctly treats risk as another persisted consumer.
- **RiskGovernor unit** owns independent persisted peak, daily-loss, turnover, and latch state. It evaluates a new AllocationCycle using the latest risk checkpoint it has consumed plus an equity snapshot that was canonical when queried.

Both follow their ownership rules. If the new Fill is committed but the RiskGovernor has not consumed it, a fresh Candidate may be evaluated against pre-fill exposure, pre-fee cash, pre-turnover, and pre-loss state. AD-06 freezes entry when a trading-critical backlog crosses 60 seconds or dead-letters grow; it does not close the normal delivery gap below that threshold. “One canonical equity snapshot” defines internal consistency of a snapshot, but not the required event high-water shared by Position, cash, market marks, working orders, and persisted RiskState.

The opposite implementation—updating RiskState synchronously in the Fill transaction—also obeys “independent persisted RiskGovernor,” but is incompatible with a RiskGovernor designed as an inbox consumer. The spine does not choose.

### Required closure

Specify a **Risk Consistency Cut** for every risk-increasing decision:

- mandatory canonical journal high-water and market-mark cutoff carried by `CanonicalEquitySnapshot`;
- minimum checkpoints for Fill/accounting, working-order reservations, turnover, daily-loss/peak, latches, and reconciliation;
- fail-closed behavior whenever any constituent checkpoint trails that high-water, regardless of the operational backlog SLO;
- whether RiskState transitions are synchronous members of the producer UoW or asynchronous materializations; and
- atomic reservation/consumption/release semantics for planned loss and exposure between Decision, Intent, Order, UNKNOWN, Fill, cancel, and terminal rejection.

Without this, “one equity snapshot” can still be a coherent snapshot of an obsolete portfolio.

## Finding 4 — UNKNOWN/reconciliation/freeze has multiple owners and no canonical release protocol

**Severity:** High  
**Divergence class:** ownership / failure and recovery  
**Implicated:** AD-11, AD-12, AD-13, AD-18, AD-21, AD-22

### Pair that obeys the ADs but is incompatible

- **OrderCoordinator** records `UNKNOWN`, freezes “exposure baru” for the affected instrument, and later records a terminal simulator/venue lifecycle result after deterministic recovery.
- **RiskGovernor/Reconciliation service** records a persistent reconciliation latch at portfolio scope and requires operator approval plus evidence to clear it.

Both are supported by the prose: UNKNOWN freezes new exposure; reconciliation latches fail closed; approval-required latches clear only through operator evidence; recovery precedes reopening. They can nevertheless disagree on all consequential details:

- instrument scope versus portfolio scope;
- whether a recovered terminal `REJECTED` auto-clears the UNKNOWN freeze;
- whether recovery evidence is itself sufficient or merely enables an approval command;
- whether protective EXIT on another Order is permitted when order state is ambiguous;
- what happens when order recovery succeeds but market continuity remains unproven; and
- which service is authoritative for the transition from `ENTRY_FROZEN` back to `HEALTHY`.

One implementation can lawfully reopen the pair after terminal recovery while the other lawfully retains a portfolio latch forever. Conversely, a projection can show `HEALTHY` from lifecycle state while RiskGovernor still rejects entries. The architecture names states and triggers but not the product state machine that composes them.

### Required closure

Define a single canonical **Safety/Degradation aggregate** with:

- typed cause, scope lattice (order/instrument/portfolio/authority), severity, creation event, and evidence refs;
- deterministic join rule when multiple causes coexist (never “last writer wins”);
- cause-specific automated recovery preconditions versus approval-required clear commands;
- explicit authority for each transition and CAS/expected sequence;
- rules for protective EXIT under each cause and evidence-quality state; and
- restart/replay behavior, including how lifecycle recovery and reconciliation commands link to the same cause ID.

Operational projections should derive status from this aggregate, not independently infer it.

## Finding 5 — Event ordering and hash-chain scope admit mutually valid journals

**Severity:** High  
**Divergence class:** shared data / tamper evidence / replay  
**Implicated:** AD-05, AD-06, AD-07, AD-14; event envelope convention

### Pair that obeys the ADs but is incompatible

- **SQLite journal adapter** interprets `previous_stream_hash` as the previous event in each `aggregate_id` stream and assigns `aggregate_seq` independently per aggregate.
- **Integrity/checkpoint/replay unit** interprets “stream” as the canonical authority-scope journal, expecting a single total order and one previous head hash for off-host checkpoint verification.

Both implementations provide append-only ordered idempotent lifecycle facts, expected aggregate sequences, payload hashes, previous-stream hashes, and deterministic replay. Aggregate-local chains are good for concurrency and local verification; a global chain is good for detecting removal/reordering across aggregates. But the two cannot verify each other. Aggregate-local chains do not by themselves prove that an entire aggregate stream was deleted or that cross-aggregate events were reordered unless the checkpoint commits to the complete set of stream heads. A global chain requires a canonical global sequence/tie-break not currently specified.

The same ambiguity affects `recorded_at_utc`, ordering keys for multiple events committed in one transaction, outbox ordering, and clean-store regeneration comparison.

### Required closure

Choose and specify one tamper-evidence topology:

- **global journal chain:** authority-scope monotonic journal sequence, canonical event order inside a transaction, previous global hash, and checkpoint semantics; or
- **aggregate chains plus authenticated head set:** exact aggregate stream key, per-stream sequence, canonical ordered Merkle/head-set commitment, inclusion/deletion proofs, and off-host checkpoint format.

Also define whether `event_id` participates in the hashed bytes, how additive correction links to the corrected fact, and how schema upcasting preserves verification of original stored bytes.

Publish failure/corruption golden fixtures for Journal, replay, integrity projection, backup verification, and migration.

## Finding 6 — CommandPort names one mutation boundary but does not define transaction ownership

**Severity:** High  
**Divergence class:** mutation path / failure recovery  
**Implicated:** AD-01, AD-05, AD-06, AD-07, AD-12, AD-16; canonical lifecycle sequence

### Pair that obeys the ADs but is incompatible

- **OrderCoordinator implementation A** handles venue evidence and calls a typed `AppendFillCommand` through `CommandPort`; the application command handler opens the UoW, validates fencing/sequence, appends lifecycle facts, updates aggregate state, and writes outbox.
- **Journal/OrderCoordinator implementation B** treats the sequence step “OrderCoordinator → Journal: append Order and Fill facts atomically” literally: OrderCoordinator opens `JournalTransaction`, appends Order and Fill, and asks a command surface only for downstream delivery outcomes.

Both can claim all I/O is behind typed ports, all mutation passes through a command boundary, one fenced application writer exists, and Fill/outbox are atomic. Yet they disagree over who owns transaction begin/commit, retry, expected-sequence reload, and domain validation. Composing A’s coordinator with B’s journal either creates nested UoWs or splits validation from commit. A `SQLITE_BUSY`, fencing loss, or crash can then be retried at different layers: one retries the whole command while the other retries only append, producing stale decisions, duplicate external calls, or a returned success for a transaction later rolled back.

AD-06 describes producer and consumer UoWs but does not state that port methods cannot accept an already-open transaction, whether application services may hold a transaction across adapter calls, or the result/exception semantics at the commit boundary.

### Required closure

Define one **Command/UoW protocol**:

- command handler is the sole owner of transaction begin/commit/rollback;
- no transaction spans Venue/Redis/network calls;
- domain transition executes against state and fence validated in the same SQLite transaction;
- commit success is the only success acknowledgment to the caller;
- typed outcomes distinguish committed, rejected, conflict, fence lost, transient pre-commit failure, and indeterminate local commit;
- retries occur only at the command envelope with the same idempotency/causation identity; and
- repository/journal ports are transaction-scoped capabilities unavailable directly to coordinators/adapters.

Contract tests should inject crash/fence loss/`SQLITE_BUSY` before append, between event and outbox writes, immediately before commit, and immediately after commit-before-return.

## Cross-cutting acceptance bar

The spine can pass this adversarial lens when the companion contracts provide executable tests proving that independently built units agree on:

1. byte-for-byte identity and event encodings;
2. one atomic serialization point for portfolio allocation and pair ownership;
3. a journal high-water consistency cut for all risk-increasing actions;
4. one composed safety/freeze/recovery state machine;
5. one verifiable event-order/hash topology; and
6. one owner and result model for every mutation transaction.

For each boundary, require at least two substitute implementations (for example in-memory model and SQLite adapter, or original run and clean-store replay) to pass the same golden vectors, state-machine properties, and crash matrices. Unit compliance with individual AD prose is not sufficient evidence of interoperability.

## Verdict rationale

The spine makes excellent safety choices—single writer, Fill authority, append-only facts, deterministic replay, isolated strategy evaluation, fail-closed risk, and physically excluded live execution. The failure is narrower but decisive for implementation readiness: several concepts are named without a single shared protocol that fixes serialization, aggregate ownership, consistency cuts, or recovery authority. These are exactly the seams where independently correct lower-level units can diverge. Therefore the document should remain **draft / not implementation-ready** until at least Findings 1–4 are closed normatively and Findings 5–6 are backed by cross-component contract tests.

## Delta Verification — updated spine

**Verification target:** updated `ARCHITECTURE-SPINE.md`, including AD-26 and AD-27  
**Delta verdict:** **FAIL — four prior seams are closed, but two blocking protocol details remain.**

### Prior-finding disposition

| Prior finding | Status | Delta evidence |
| --- | --- | --- |
| 1. Deterministic identity encoding | **CLOSED** | AD-26 now fixes canonical JSON/UTF-8, NFC, key order, null semantics, enums, UTC grammar, scaled integers, domain-separated SHA-256 projections, hex form, recipe versioning, and cross-unit golden vectors. |
| 2. Allocation-cycle ownership | **CLOSED, subject to Finding 3 lifecycle detail** | AD-27 establishes `PortfolioAllocation` as the per-portfolio serialization aggregate and atomically binds cutoff, full Decision batch, pair ownership, risk reservation, RiskState, events, and outbox; conflicts are explicitly non-executable and partial executable batches are prohibited. |
| 3. Fill/risk consistency cut | **PARTIALLY CLOSED — BLOCKING** | AD-27 establishes the required journal high-water/market cutoff and rejects entry if any named checkpoint trails. It also introduces reservation, but does not normatively define reservation quantity transitions for partial fills and multi-fill Orders. |
| 4. UNKNOWN/reconciliation/freeze ownership | **PARTIALLY CLOSED — BLOCKING** | AD-27 makes `SafetyState` canonical, gives it typed causes/scopes/severity/evidence/CAS, defines deterministic severity join, and makes SafetyState commands the only transition owner. It does not define the cause-specific clear predicates or scope-propagation lattice it requires. |
| 5. Journal/hash-chain topology | **CLOSED** | AD-26 selects an authority-scope global journal sequence, deterministic intra-transaction order, previous-global-hash, hashing of stored original bytes, and immutable upcast views. |
| 6. Command/UoW ownership | **CLOSED** | AD-06 now assigns begin/commit/rollback exclusively to the application command handler, forbids network-spanning transactions, transaction-scopes repositories, fixes commit acknowledgment and typed outcomes, and places retry at the command envelope. |

### Remaining blocker A — Reservation behavior under partial Fill is ambiguous

AD-27 says a risk-increasing reservation is retained through `Intent/Order/UNKNOWN` and “released or consumed atomically” on terminal rejection/cancel/Fill. A Fill is not necessarily terminal. Two implementations still obey that text but are incompatible:

- **Settlement A** consumes the entire Order reservation on the first partial Fill, reasoning that Fill is listed as a consume event; the open remainder is then no longer represented in reserved exposure/planned loss.
- **Settlement B** consumes only the filled quantity and retains reservation for remaining executable quantity, fees, adverse slippage, and stop loss until terminal completion/cancel.

After a 10% partial fill, A can admit another entry using capacity that the remaining 90% Order may still consume; B cannot. Both share the same high-water and perform atomic transitions, so the newly added consistency cut does not resolve the semantic disagreement.

**Required spine closure:** define reservation as a quantitative ledger with `reserved`, `consumed`, and `released` amounts; prescribe proportional or conservative allocation of notional, planned loss, fees, liquidity/impact buffer, and turnover for every partial Fill; retain the unfilled remainder through `PARTIALLY_FILLED` and `UNKNOWN`; release only the proven non-executable remainder at terminal state; and require conservation such as `initial reservation = consumed + active remainder + released` with rounding rules and property tests.

### Remaining blocker B — Safety cause clear and scope propagation remain delegated, not specified

AD-27 says each cause has a “cause-specific clear rule” and introduces a “scope lattice,” but neither the rule table nor the lattice ordering/propagation is present. The prior counterexample is narrowed but still constructible:

- **Safety implementation A** treats terminal `REJECTED` evidence as sufficient for an authenticated recovery command to clear an instrument-scoped UNKNOWN cause automatically; a systemic market-continuity cause remains portfolio-scoped.
- **Safety implementation B** requires operator approval plus reconciliation evidence for every UNKNOWN clear and promotes any instrument UNKNOWN to portfolio scope because shared equity/risk capacity may be affected.

Both use the single SafetyState aggregate, typed causes, expected sequence, max-severity join, and SafetyState commands exclusively. They still disagree on when and where entry reopens. A generic “cause-specific” requirement cannot be independently implemented without choosing policy outside the spine.

**Required spine closure:** add a normative table for at least `OPERATOR_KILL`, `HARD_DRAWDOWN`, `STALE_DATA`, `MARKET_CONTINUITY`, `UNKNOWN_ORDER`, `RECONCILIATION`, delivery dead-letter/backlog, clock anomaly, disk/storage, and writer-fence loss. For each specify default scope, scope escalation/containment, severity, allowed protective action, automatic recovery predicate, approval requirement, reconciliation evidence, and whether/when it can de-escalate. Define join over both severity and scope, and state that clearing one cause never lowers effective state while another joined cause remains.

### Updated acceptance decision

AD-26, the revised AD-06, and most of AD-27 successfully eliminate four of the six original divergence classes. The remaining two are not cosmetic implementation notes: partial-fill reservation can breach hard risk capacity, and unspecified SafetyState clear/scope policy can reopen entry inconsistently after ambiguity. The spine remains **not implementation-ready** under this adversarial lens until both protocols are made normative and exercised by shared state-machine/property fixtures.

## Final Delta Verification

**Verification scope:** only the two blockers remaining after the preceding delta.  
**Final verdict:** **PASS — no blocking divergence seam remains from Findings 1–6.**

### Partial-fill reservation — CLOSED

AD-27 now defines a quantitative conservation ledger across `initial`, `consumed`, `active_remainder`, and `released` for notional, planned loss, fees, conservative slippage/impact, and turnover. It requires a partial Fill to consume only its conservative filled share, retain capacity for all executable unfilled quantity, keep rounding residual reserved, prohibit release in `PARTIALLY_FILLED` and `UNKNOWN`, and release only proven non-executable remainder at terminal reject/cancel/expiry. Atomic transition and property-test requirements remove the previous full-release-versus-proportional-retention ambiguity.

### SafetyState clear and scope propagation — CLOSED

AD-27 now binds `SafetyState` to the Safety Cause Matrix and makes join operate across severity and scope while preventing one cause from clearing another. The matrix defines the scope lattice `ORDER < INSTRUMENT < PORTFOLIO < AUTHORITY`, constrained upward propagation, effective state/protective behavior, and clear predicate for every previously requested cause class: operator kill, hard drawdown, stale data, market continuity, UNKNOWN order, reconciliation, critical delivery, clock anomaly, storage failure, and writer-fence loss. Automated versus approval-gated recovery and reconciliation prerequisites are explicit enough that the prior incompatible clear/scope implementations are no longer both compliant.

### Acceptance

The latest spine closes both final blockers. This PASS is limited to the original adversarial Findings 1–6 and does not assert completeness beyond that review scope.
