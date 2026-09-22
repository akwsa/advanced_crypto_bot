# Good-Spine Rubric Review

**Target:** `ARCHITECTURE-SPINE.md`  
**Companion context:** `IMPLEMENTATION-ROADMAP.md`  
**Review date:** 2026-08-24  
**Mechanical lint:** PASS (`lint_spine.py`, 0 findings)  
**Verdict:** **CONDITIONAL FAIL — the direction is coherent, but four high-impact divergence points remain insufficiently bound for independent implementation.**

The spine establishes a strong paradigm and sensible service boundaries. It directly addresses the observed brownfield failures: dual accounting, generic terminal reasons, incomplete Strategy 2 lifecycle, unrealistic evaluation, false drawdown, and duplicate runtime ownership. The roadmap is broadly consistent with the spine. However, several Rules state desired outcomes without fixing the identity, ownership, or failure semantics needed to enforce them.

## Critical findings

None.

## High findings

### H1 — Replay identity omits state that can change a policy result

**Checklist impact:** real divergence point missed; Rule is not sufficient to prevent its stated divergence.  
**Affected:** AD-1, AD-3, AD-6, AD-7.  
**Disposition:** autofix in spine.

AD-1 binds the market snapshot, strategy/configuration identity, event time, experiment ID, and idempotency key, but AD-3 also makes the policy consume an explicit portfolio view. The portfolio view is not included in decision identity. Nor are the universe selection/rules and execution-cost model identity explicitly bound to the decision or downstream fill. Two implementations can replay the same AD-1 tuple against different cash, positions, pending orders, risk limits, pair eligibility, or simulator versions and produce different intent/fill/P&L while each claims compliance.

Strengthen the contract so every policy decision binds an immutable portfolio-view ID/hash and policy-input schema version; every executable intent/fill additionally binds the universe/rules snapshot and execution-simulator version. Define replay equality at the typed policy-output boundary, while fills replay against the simulator inputs. This should also clarify that wall-clock-derived values are captured in the input snapshot rather than read during evaluation.

### H2 — “Single runtime writer” is placement, not split-brain prevention

**Checklist impact:** Rule is not enforceable and does not fully prevent its stated divergence; operational envelope incomplete.  
**Affected:** AD-9, Structural Seed, deployment map; roadmap Phase 0.  
**Disposition:** discuss briefly, then autofix the selected mechanism.

Declaring the VM the sole writer does not prevent WSL, a manually launched VM process, or overlapping systemd restarts from writing. The Structural Seed mentions a single-writer lease, but no AD defines lease ownership, fencing token propagation, renewal/expiry behavior, or fail-closed behavior. A normal distributed lease without fencing can still allow a paused former holder to resume writes.

Bind one concrete authority mechanism. At minimum: acquire a named runtime lease before scheduler/poller/journal startup; attach a monotonically increasing fencing epoch to all experiment writes; reject stale epochs at the persistence boundary; stop scheduling and polling on lease loss; keep test/replay namespaces and credentials structurally separate. Also declare whether Redis or SQLite is the lease authority and what happens when it is unavailable. Without this, AD-9 is a runbook hope rather than an invariant.

### H3 — Canonical equity has no canonical valuation policy

**Checklist impact:** real divergence point missed; AD-8 cannot consistently prevent false drawdown.  
**Affected:** AD-8, market-data boundary, risk; roadmap Phase 0.  
**Disposition:** autofix in spine.

“Mark-to-market normalized open positions” leaves independent risk and portfolio implementations free to choose last trade, bid, midpoint, candle close, or stale cached price. It also leaves quote staleness, missing-price behavior, valuation timestamp, peak-equity ownership, and daily-boundary semantics unspecified. Those choices materially change drawdown and circuit-breaker behavior—the exact failure AD-8 is intended to prevent.

Define a versioned valuation snapshot and conservative pricing rule (including stale/missing data behavior), make the ledger/risk calculation consume the same snapshot ID, and assign ownership of peak equity and daily-loss reset boundaries. Protective exits should remain enabled under both market-data degradation and breaker activation, with an explicit fail-safe rule when they cannot be valued.

### H4 — Durable experiment data has no lifecycle or recovery contract

**Checklist impact:** an owned operational/environmental dimension is largely silent.  
**Affected:** AD-1, AD-2, AD-5, AD-7, AD-9; roadmap Phases 0–5.  
**Disposition:** discuss retention needs, then add an AD or explicit Deferred item with revisit conditions.

Immutable snapshots, journals, counterfactual labels, and promotion reports are the evidence substrate, but the spine does not bind schema migration compatibility, backup/restore, retention/compaction, corruption handling, or recovery-point expectations. Independent Phase 0/1 implementations could retain different samples, break replay after schema changes, or restore the journal without the referenced market/config snapshots. SQLite migration is deferred only as a database-engine choice; that does not defer data durability semantics.

Bind atomic migration/versioning and recoverability of the complete replay closure (journal plus referenced snapshots/config/simulator artifacts). Define retention ownership and require evidence referenced by a promotion decision to remain immutable and restorable for a stated period. If exact periods are not ready, put them under Deferred with a fail-closed rule: promotion stays disabled until retention and restore verification are approved.

## Medium findings

### M1 — Deferred promotion thresholds can produce incompatible promotion behavior

**Checklist impact:** a Deferred item can let two units diverge.  
**Affected:** AD-7, Deferred; roadmap Phase 4.  
**Disposition:** autofix.

The roadmap’s thresholds are explicitly assumptions requiring approval, which is appropriate, but the spine does not say what the system does before approval or who owns approval. One implementation may promote on the provisional values while another may block. State that promotion is fail-closed until a versioned gate policy is operator-approved, and that any threshold change creates a new evaluation/promotion-policy version rather than mutating an active experiment.

### M2 — Execution realism is named but market-reference ownership is underspecified

**Checklist impact:** AD-6 permits divergent compliant simulators.  
**Affected:** AD-6, market data, simulator.  
**Disposition:** autofix or defer exact models while binding inputs.

Fee schedule, tick/size precision, latency, spread, and partial-fill logic change over time. AD-6 says the simulator is versioned, but does not require its exchange metadata and fee schedule to be effective-dated snapshots, nor identify the order-book/trade data required for size-aware fills. Bind these reference inputs to simulator version and event time. If available data cannot support a claimed model, the simulator must emit a quality limitation rather than silently substitute optimistic assumptions.

### M3 — Installed versions are evidenced, but “verified-current” is not

**Checklist impact:** named technology currentness/fit not demonstrated.  
**Affected:** Stack.  
**Disposition:** document verification metadata; no need to chase latest versions solely for this initiative.

The table accurately labels versions as “verified in WSL,” which ratifies the brownfield development environment, but it does not establish the VM versions, compatibility parity, support status, or the date/source of currentness verification. Since deployment is split across WSL and VM, require a lock/environment manifest and parity check for runtime dependencies. Record currentness/support verification separately; installed-version observation alone does not satisfy the checklist’s verified-current criterion.

## Low findings

### L1 — “Actionable candidate” and terminality need a shared lifecycle definition

**Checklist impact:** AD-4 can be interpreted differently.  
**Affected:** AD-4, AD-10.  
**Disposition:** autofix in conventions or typed event contract.

Define when a candidate becomes actionable, whether terminality is per candidate or per intent/order lifecycle, and how supersession/cancellation is represented. Otherwise one team may persist an `ARMED` state as terminal while another waits for `CLOSED`, producing different coverage denominators.

## Checklist summary

| Good-spine criterion | Result | Notes |
| --- | --- | --- |
| Fixes real divergence points for the level below | Partial | Strong boundaries; replay-state, valuation, fencing, and durability gaps remain. |
| Every Rule enforceable and prevents stated divergence | Partial | AD-1, AD-8, and AD-9 need additional enforceable semantics. |
| Deferred cannot allow incompatible implementations | Partial | Provisional promotion gates need fail-closed ownership/versioning. |
| Named technology verified-current | Partial | WSL installed versions are recorded; VM parity/support/currentness evidence is absent. |
| Ratifies brownfield codebase | Pass with caution | Decisions align with observed monolithic runtime, normalized/legacy accounting, SQLite/Redis, Telegram, and Strategy 2 integration; several items are intentionally target-state changes. |
| Covers source capabilities | Pass | Market data, strategy policy, simulator, ledger, risk, evaluation, promotion, and deployment are all mapped. |
| Inherited spine remains unweakened | N/A | No parent spine is declared. |
| Every owned dimension decided/deferred/open | Partial | Data lifecycle/recovery and split-brain failure semantics are not adequately covered. |

## Recommended gate outcome

Do not mark the spine `final` yet. Apply H1 and H3 directly; select and bind the H2 fencing authority; add the H4 durability/recovery contract; then make promotion fail-closed until its versioned gate is approved. The roadmap itself does not need restructuring, but its Phase 0 should explicitly include single-writer fencing and restore-tested schema migration, and Phase 1 should preserve the full replay closure.
