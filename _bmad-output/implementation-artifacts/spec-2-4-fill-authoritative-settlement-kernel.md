---
title: 'Story 2.4 Fill-Authoritative Settlement Kernel'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 1
baseline_commit: '6a215ce'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-2-3-deterministic-simulator-lifecycle-remediation.md'
  - '{project-root}/advanced_crypto_bot/docs/AUDIT_FAKTUAL_MIGRASI_AUTOTRADE_NEXT_2026-08-30.md'
---

<frozen-after-approval reason="autonomous continuation authorized by user on 2026-08-30">

## Intent

**Problem:** Story 2.4 memiliki ledger sederhana tetapi tidak mempunyai Intent→Order transaction boundary, pending outbox, event/fill conflict detection, strict aggregate sequence, atomic transition, tax, atau conservation proof. Acknowledgment dan cumulative simulator events belum dihubungkan ke fill-authoritative state.

**Approach:** Tambahkan pure canonical execution/settlement kernel, transaction-scoped Unit-of-Work port, dan application handlers yang mengubah accounting hanya dari fill baru. Durable SQLite adapter/fence tidak diklaim selesai; Story tetap dependency-blocked maksimal PARTIAL sampai Story 3.1/5.3 menyediakan persistence foundation.

## Boundaries & Constraints

**Always:** Deterministic intent/order/idempotency IDs; Intent+PENDING outbox satu commit sebelum dispatch envelope keluar; strict event sequence; exact duplicate noop; conflicting duplicate fail-closed; cumulative fill-prefix; BUY/SELL cash, fee, tax, quantity conservation; ACK/OPEN tanpa fill tidak mengubah account; UNKNOWN mempertahankan remainder dan entry freeze; commit failure menghasilkan zero partial state.

**Ask First:** SQLite production adapter/schema, persistent writer fence, reservation persistence, perubahan dirty `accounting.py`/`numeric.py`/`fencing.py`, runtime wiring.

**Never:** Fake durable-PASS claim, float, network/Redis, live submit, administrative fill, overdraft/oversell, mutation di luar UoW.

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Failure |
|---|---|---|---|
| Prepare | Canonical decision/request | Intent+Order+PENDING outbox atomically staged | No dispatch on failed commit |
| ACK/OPEN | Event without fill | Sequence advances; account unchanged | Conflict/order fault typed |
| Partial→filled | Cumulative lifecycle events | Only new fill IDs settle once | Conservation enforced |
| Duplicate/race | Repeated/delayed/conflicting event | Exact noop; UNKNOWN freezes | Conflict fail-closed |
| BUY/SELL | Mixed-scale fill costs | Exact cash/qty/fee/tax | Overdraft/oversell rejected |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/autotrade_next/domain/execution.py` -- canonical intent/order/account/fill settlement state and pure transitions.
- `advanced_crypto_bot/autotrade_next/ports/settlement.py` -- atomic UnitOfWork protocol and immutable commit bundle.
- `advanced_crypto_bot/autotrade_next/application/settlement.py` -- prepare-before-dispatch and settle-event handlers.
- package exports and import allowlists -- explicit dependency boundary.
- `advanced_crypto_bot/tests/autotrade_next/contract/test_fill_settlement_kernel.py` -- RED/GREEN matrix and fault-injected UoW.
- Story artifact, deferred-work, sprint tracker, and audit ledger -- factual PARTIAL evidence.

## Tasks & Acceptance

**Execution:**
- [x] Add RED contracts for matrix, deterministic IDs, replay, and atomic failure.
- [x] Implement immutable domain kernel and exact common-scale conservation.
- [x] Implement UoW port/application handlers without persistence implementation.
- [x] Run full gates, adversarial review, and document truthful PARTIAL dependency.

**Acceptance Criteria:**
- Identical input produces identical intent/order/outbox and semantic transition.
- Only new canonical fills alter cash/quantity/fee/tax; cumulative repeats cannot double-settle.
- Sequence, fill-prefix, terminal remainder, overdraft/oversell, and conservation fail closed.
- Fault before commit exposes no dispatch or partial state; retry is idempotent.
- No claim of durable atomicity until SQLite/fence/migration evidence exists.

## Spec Change Log

- 2026-08-30: RED collection failed karena application boundary belum ada; GREEN focused+AST 29/29, full contracts 345/345, Strategy2/dry-run 61/61, compileall/diff-check exit 0. Verdict remains PARTIAL pending durable SQLite/fence dependency.
- 2026-08-30: Blind dan edge-case review menghasilkan patch untuk coarse quote-scale notional compatibility, input scale cap, schema/time/quantity monotonicity, UNKNOWN mutation/freeze, account revision CAS, account+instrument lookup, preparation/commit bundle composition, ledger provenance, corrupted fill-history detection, serta UoW close/rollback fault handling.
- 2026-08-30: Final review gates: focused settlement+AST 37/37, seluruh contracts 353/353, Strategy2/dry-run 63/63, compileall dan diff-check exit 0. Spec execution selesai; verdict story tetap PARTIAL karena durable adapter/fence/migration tidak termasuk implementasi ini.

## Verification

- Focused settlement contracts RED then 37/37 PASS.
- Entire AutoTrade Next contracts 353/353 dan 63 Strategy2/dry-run regressions PASS.
- `compileall` and `git diff --check` exit 0.

## Adversarial Review Disposition

- **Patched:** simulator notional rounding compatibility; event schema/time/scale monotonicity; duplicate fill evidence; UNKNOWN quantity freeze; cross-aggregate DTO/bundle binding; corrupted account/order fill-history; account revision expectation; account+instrument lookup; entry provenance; unbounded scale; read/noop transaction cleanup; rollback-fault masking.
- **Constrained:** `order_ordinal` hanya `0` sampai reservation semantics untuk multi-order Intent tersedia.
- **Deferred, not claimed:** durable atomicity, persistent fencing/freeze recovery, account-cash plus per-instrument position storage, cross-order reservation/CAS, migration, dan crash/restart proof.

## Suggested Review Order

1. `domain/execution.py` — invariant dan pure transition.
2. `ports/settlement.py` — commit bundle/CAS boundary.
3. `application/settlement.py` — transaction lifecycle dan prepare-before-dispatch.
4. `test_fill_settlement_kernel.py` — positive, negative, integration, dan injected-fault evidence.
5. Story artifact, deferred ledger, sprint tracker, lalu audit rolling ledger.
