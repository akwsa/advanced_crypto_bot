---
story_id: "2.6"
title: "Memulihkan lifecycle tanpa decision baru"
epic: "2"
status: "review"
baseline_commit: "51f1660451d0519d133fef2e04e34e2b88f6b839"
---

# Story 2.6: Memulihkan lifecycle tanpa decision baru

Status: review

## Story

As a Officer,
I want restart dan reconciliation mengembalikan state yang sama,
so that crash atau ambiguous acknowledgment tidak mengubah sejarah atau menambah exposure.

## Acceptance Criteria

1. **Deterministic Recovery & Replay**:
   - Startup recovery mengembalikan `Order`, `Position`, `CashLedger`, dan `PolicyState` persis ke high-water mark terakhir tanpa membuat keputusan strategi baru atau mengirim order ganda.
   - Penanganan ambiguous status (`UNKNOWN`) wajib menjalankan *query-before-resubmit*.

## Factual Reopen — 2026-08-30

- Baseline audit E12: **FAIL**.
- Existing helper hanya memilih `QUERY_VENUE` dari tuple UNKNOWN dan tidak merepresentasikan recovery high-water.
- Missing: account/order/Position/policy/pending/inbox/outbox/projection checkpoint, deterministic crash plan, dispatch dedupe, mismatch freeze, correction taxonomy/evidence/approval, dan replay identity.
- Remediasi dibatasi ke semantic checkpoint/plan; durable restart integration tetap dependency sehingga verdict maksimal PARTIAL.

## Completion Evidence — 2026-08-30

- RED: import error karena canonical recovery checkpoint/correction/plan surface belum ada.
- Focused recovery contracts: 8/8 PASS; recovery + identity/import matrix: 31/31 PASS.
- Seluruh AutoTrade Next contracts: 373/373 PASS.
- Strategy2/dry-run regression: 63/63 PASS.
- `compileall` dan `git diff --check`: exit 0.
- Checkpoint content-bound mencakup Account, Order, Position/protection/policy ref, preparation, pending command refs, inbox, PENDING outbox, projection high-water, freeze, UNKNOWN deadline, dan captured high-water.
- Plan deterministik tidak menjalankan strategy evaluation, mengutamakan UNKNOWN query, membekukan mismatch, meredeliver outbox satu kali sebagai satu-satunya resume-dispatch path, serta menerima hanya empat correction kind dengan evidence/approval/high-water/idempotency.
- Factual verdict: **PARTIAL**, bukan PASS/done, karena belum ada SQLite replay/startup adapter, crash-process proof, dispatcher/inbox/projection restoration runtime, atau correction commit handler.

## Known Limits / Dependency Blockers

- Checkpoint/plan adalah semantic contract; tidak membaca atau menulis durable journal sendiri.
- Redelivery IDs dan high-waters sudah deterministic, tetapi delivery acknowledgment, inbox transaction, projection rebuild, RTO/RPO, dan restart crash matrix memerlukan Story 3.1/5.3 persistence foundation.
- Correction request fail-closed pada taxonomy/reference/high-water, tetapi approval authorization dan atomic additive correction commit belum tersedia.
- VM/runtime tidak diaudit atau diubah dalam story ini.

## File List

- `advanced_crypto_bot/autotrade_next/domain/recovery.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_recovery.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-2-6-deterministic-recovery-plan.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Semantic deterministic recovery checkpoint/plan review-ready; durable restart dependency tetap terbuka.
