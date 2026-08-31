---
title: 'Story 2.6 Deterministic Recovery Plan'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 3
baseline_commit: '51f1660'
---

<frozen-after-approval reason="autonomous continuation authorized by user on 2026-08-30">

## Intent

Replace the two-field UNKNOWN helper with an immutable, content-bound recovery checkpoint and deterministic plan covering account/cash ledger, orders, Positions/protection, full PolicyState, preparations, pending commands, inbox/outbox, projection high-waters, freeze, venue evidence, and approved additive corrections; persist and restore the exact checkpoint through the fenced SQLite boundary.

## Boundaries

**Always:** query-before-resubmit for UNKNOWN; deterministic ordered plan; no strategy evaluation; no new decision; exact duplicate plan; mismatch freezes entry; only four correction kinds with evidence+approval+expected high-water; pending outbox redelivery is idempotent.

**Never:** touch dirty compatibility accounting/numeric/fencing/config files, infer terminal venue state, overwrite history, fabricate approval, submit live, atau mengklaim durability tanpa fault-boundary proof.

## Tasks

- [x] RED contracts for checkpoint, crash-equivalent plan, UNKNOWN, mismatch, corrections, duplicates.
- [x] Pure canonical checkpoint/evidence/correction/plan values and reducer.
- [x] Full gates, review, rolling documentation, isolated local commit.
- [x] Durable explicit checkpoint codec, fenced SQLite head/history, startup load/plan, and delivery acknowledgment restoration.
- [x] Authenticated atomic additive correction commit, append-only successor validation, corruption handling, and crash-boundary matrix.

## Code Map

- `advanced_crypto_bot/autotrade_next/domain/recovery.py`
- `advanced_crypto_bot/autotrade_next/ports/recovery.py`
- `advanced_crypto_bot/autotrade_next/adapters/sqlite/recovery_store.py`
- domain exports/import matrix
- `advanced_crypto_bot/tests/autotrade_next/contract/test_recovery.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_sqlite_recovery_store.py`
- story/deferred/sprint/audit artifacts

## Verification

- RED import failure; final recovery 8/8, recovery+identity 31/31, all contracts 373/373, Strategy2/dry-run 63/63 PASS.
- `compileall` dan `git diff --check` exit 0.
- Review loop 3: recovery/persistence+identity 48/48, all AutoTrade Next contracts 449/449, Strategy2/dry-run 69/69 PASS; compileall dan diff check exit 0.

## Adversarial Review Disposition

- **Patched:** mutable/minimal UNKNOWN helper, missing content identity, duplicate state IDs, scope/time/high-water drift, UNKNOWN without freeze/deadline, foreign/stale venue evidence, unsupported/unapproved correction, correction high-water conflict, and duplicate direct redispatch alongside outbox redelivery.
- **Review-loop-2 patched:** pending `IntentPrepared` sekarang ditahan untuk `UNKNOWN`, mismatch, dan order yang sudah acknowledged; venue query dapat resolve; checkpoint `v3` mengikat complete pending Position/outbox state; plan `v2` mengikat venue evidence; foreign correction dan inconsistent public plan ditolak.
- **Review-loop-3 patched:** checkpoint `v5` menyimpan full PolicyState, cash ledger, dan applied corrections; durable SQLite restart, delivery ack, corruption fail-closed, append-only successor, authenticated correction, fence/CAS, serta crash/indeterminate-commit recovery dibuktikan.
- **Single resume path:** hanya order yang belum memiliki receipt/status dan tidak ambiguous yang dapat kembali lewat PENDING outbox redelivery; plan tidak menerbitkan direct redispatch untuk order yang sama.
- **Resolved:** durable checkpoint loader, canonical-state rehydration, inbox/outbox restoration, deterministic dispatcher redelivery identity, projection high-water restore, correction handler, fence, startup, dan RPO crash boundaries.

## Suggested Review Order

1. `domain/recovery.py` checkpoint invariants and binding.
2. `plan_recovery` UNKNOWN/mismatch/correction ordering.
3. `adapters/sqlite/recovery_store.py` codec, fence/CAS, successor, correction, and startup loader.
4. `test_recovery.py` and `test_sqlite_recovery_store.py` deterministic, crash, query-first, delivery, ledger, and correction evidence.
5. Story/deferred/sprint/audit artifacts.
