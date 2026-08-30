---
title: 'Story 2.6 Deterministic Recovery Plan'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 1
baseline_commit: '51f1660'
---

<frozen-after-approval reason="autonomous continuation authorized by user on 2026-08-30">

## Intent

Replace the two-field UNKNOWN helper with an immutable, content-bound recovery checkpoint and deterministic plan covering account, orders, Positions/protection, preparations, pending commands, inbox/outbox, projection high-waters, freeze, venue evidence, and approved additive corrections. SQLite/restart runtime remains deferred; factual verdict maximum PARTIAL.

## Boundaries

**Always:** query-before-resubmit for UNKNOWN; deterministic ordered plan; no strategy evaluation; no new decision; exact duplicate plan; mismatch freezes entry; only four correction kinds with evidence+approval+expected high-water; pending outbox redelivery is idempotent.

**Never:** touch dirty compatibility accounting/numeric/fencing/config files, infer terminal venue state, overwrite history, fabricate approval, submit live, claim crash-durable PASS.

## Tasks

- [x] RED contracts for checkpoint, crash-equivalent plan, UNKNOWN, mismatch, corrections, duplicates.
- [x] Pure canonical checkpoint/evidence/correction/plan values and reducer.
- [x] Full gates, review, rolling documentation, isolated local commit.

## Code Map

- `advanced_crypto_bot/autotrade_next/domain/recovery.py`
- domain exports/import matrix
- `advanced_crypto_bot/tests/autotrade_next/contract/test_recovery.py`
- story/deferred/sprint/audit artifacts

## Verification

- RED import failure; final recovery 8/8, recovery+identity 31/31, all contracts 373/373, Strategy2/dry-run 63/63 PASS.
- `compileall` dan `git diff --check` exit 0.

## Adversarial Review Disposition

- **Patched:** mutable/minimal UNKNOWN helper, missing content identity, duplicate state IDs, scope/time/high-water drift, UNKNOWN without freeze/deadline, foreign/stale venue evidence, unsupported/unapproved correction, correction high-water conflict, and duplicate direct redispatch alongside outbox redelivery.
- **Single resume path:** pending `IntentPrepared` hanya kembali lewat PENDING outbox redelivery; plan tidak menerbitkan direct redispatch untuk order yang sama.
- **Deferred:** durable checkpoint loader, journal replay, inbox acknowledgment, dispatcher, projection rebuild, correction handler, fence, startup/RTO/RPO proof.

## Suggested Review Order

1. `domain/recovery.py` checkpoint invariants and binding.
2. `plan_recovery` UNKNOWN/mismatch/correction ordering.
3. `test_recovery.py` deterministic, duplicate, query-first, and correction evidence.
4. Story/deferred/sprint/audit artifacts.
