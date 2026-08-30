---
title: 'Story 2.5 Unified Protective EXIT Kernel'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 1
baseline_commit: '9244acc'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md'
  - '{project-root}/advanced_crypto_bot/docs/AUDIT_FAKTUAL_MIGRASI_AUTOTRADE_NEXT_2026-08-30.md'
---

<frozen-after-approval reason="autonomous continuation authorized by user on 2026-08-30">

## Intent

**Problem:** Story 2.5 hanya mengevaluasi operator/time/SL/TP, membandingkan raw units, dan tidak menyimpan canonical Position protection transition. Invalidation, drawdown, reconciliation, trailing, alpha exit, deterministic key, expected sequence, partial-fill remainder, serta dust quarantine belum ada.

**Approach:** Ganti contract minimal dengan pure unified EXIT state machine, fixed precedence AD-04, deterministic event/outbox identity, same execution preparation schema dari Story 2.4, dan transaction-scoped composite UoW bundle. Durable SQLite/fence/restart tidak diklaim; verdict maksimal PARTIAL.

## Boundaries & Constraints

**Always:** common-scale comparison; explicit remaining quantity; operator/drawdown/invalidation-stop/reconciliation/profit-trailing-time/alpha/HOLD precedence; one deterministic EXIT request per expected Position sequence; only canonical exit Fill reduces Position; partial remainder keeps protection; sub-minimum remainder is quarantined dust with incident+valuation; commit before dispatch.

**Ask First:** production SQLite adapter/schema, persistent writer fence, migration, runtime wiring, change to dirty `accounting.py`/`numeric.py`/`fencing.py`/`core/config.py`.

**Never:** close Position from acknowledgment, discard remainder, block protective EXIT because entry is frozen, float arithmetic, network call in transaction, claim durable PASS.

## Edge-Case Matrix

| Scenario | Expected |
|---|---|
| Multiple triggers | Fixed precedence selects one reason deterministically |
| Mixed price/quantity scales | Economic comparison at common scale; no raw-unit bug |
| Duplicate request | Same expected sequence and inputs return identical bundle/no duplicate dispatch |
| Partial exit Fill | Reduce only Fill quantity; retain high-water/trailing/invalidation/deadline |
| Remainder below venue minimum | `QUARANTINED_DUST`, incident+valuation, never false `CLOSED` |
| Full Fill | `CLOSED` only when remaining quantity is exactly zero |
| Commit fault | No dispatch and no partial policy/intent/outbox state |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/autotrade_next/domain/exit_protection.py`
- `advanced_crypto_bot/autotrade_next/ports/exit.py`
- `advanced_crypto_bot/autotrade_next/application/exit.py`
- package exports/import allowlist
- `advanced_crypto_bot/tests/autotrade_next/contract/test_exit_protection.py`
- story artifact, deferred ledger, sprint tracker, rolling audit

## Tasks & Acceptance

- [x] Capture RED contracts for missing unified surface and raw-unit regression.
- [x] Implement immutable Position protection, signal, transition, Fill, dust/incident values.
- [x] Bind transition to Story 2.4 execution preparation and composite UoW.
- [x] Run full gates and adversarial review; document truthful PARTIAL dependency.

Acceptance requires deterministic fixed precedence, exact mixed-scale behavior, expected-sequence conflict detection, no double exit, protection-preserving partial Fill, dust quarantine, and zero dispatch on commit fault.

## Verification

- RED collection error karena application/port belum ada; final focused Story 2.5 + identity/import matrix 39/39 PASS.
- Entire AutoTrade Next contracts 367/367 dan Strategy2/dry-run regressions 63/63 PASS.
- `compileall` and `git diff --check` exit 0.

## Adversarial Review Disposition

- **Patched:** raw-unit comparison; absent precedence families; boolean self-attestation; unbounded scale; event/command/composite mismatch; time regression; unrelated Fill/order; partial target/remainder; false close; preexisting dan post-Fill dust; missing valuation provenance; commit/noop cleanup; rollback fault masking.
- **Preserved:** partial Fill hanya mengurangi canonical Fill quantity dan seluruh stop/high-water/invalidation/deadline protection tetap ada pada remainder.
- **Deferred, not claimed:** durable SQLite/fence, restart/replay, atomic coupling exit Fill dengan settlement transaction, approval verifier, dan runtime OrderCoordinator wiring.

## Suggested Review Order

1. `domain/exit_protection.py` — precedence, state, partial/dust invariant.
2. `ports/exit.py` — command/evaluation/execution composite binding.
3. `application/exit.py` — expected sequence dan commit-before-dispatch.
4. `test_exit_protection.py` — RED/GREEN, fault, mixed-scale, partial, dust evidence.
5. Story artifact, deferred ledger, sprint tracker, rolling audit.

## Spec Change Log

- 2026-08-30: RED collection error; first GREEN 37/37; adversarial patches menambah evidence references, pending-order linkage, pre-dispatch dust, valuation provenance, entry/evaluation time, protection snapshot binding, dan direct composite validation. Final gates 39/39 focused, 367/367 contracts, 63/63 regressions.
