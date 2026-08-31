---
story_id: "2.6"
title: "Memulihkan lifecycle tanpa decision baru"
epic: "2"
status: "done"
baseline_commit: "51f1660451d0519d133fef2e04e34e2b88f6b839"
---

# Story 2.6: Memulihkan lifecycle tanpa decision baru

Status: done

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

- Review-ready implementation commit: `9dbde0c`.
- RED: import error karena canonical recovery checkpoint/correction/plan surface belum ada.
- Focused recovery contracts: 8/8 PASS; recovery + identity/import matrix: 31/31 PASS.
- Seluruh AutoTrade Next contracts: 373/373 PASS.
- Strategy2/dry-run regression: 63/63 PASS.
- `compileall` dan `git diff --check`: exit 0.
- Checkpoint content-bound mencakup Account, Order, Position/protection/policy ref, preparation, pending command refs, inbox, PENDING outbox, projection high-water, freeze, UNKNOWN deadline, dan captured high-water.
- Plan deterministik tidak menjalankan strategy evaluation, mengutamakan UNKNOWN query, membekukan mismatch, meredeliver outbox satu kali sebagai satu-satunya resume-dispatch path, serta menerima hanya empat correction kind dengan evidence/approval/high-water/idempotency.
- Factual verdict: **PARTIAL**, bukan PASS/done, karena belum ada SQLite replay/startup adapter, crash-process proof, dispatcher/inbox/projection restoration runtime, atau correction commit handler.

## Automated Review Repair — 2026-08-31

- Memblokir redelivery `IntentPrepared` untuk order `UNKNOWN`, mismatch, atau order yang sudah memiliki acknowledgment/receipt sehingga query-before-resubmit tidak dapat dilangkahi oleh jalur outbox.
- Hasil query venue non-`UNKNOWN` sekarang menyelesaikan query set dan masuk ke jalur mismatch/correction tanpa redispatch.
- Checkpoint schema `v3` mengikat seluruh pending Position state, scope/status outbox, dan menolak account/instrument, preparation/outbox, atau state high-water yang tidak konsisten.
- Recovery correction menolak target asing; public `RecoveryPlan` menolak action graph yang tidak konsisten.
- Recovery plan schema `v2` mengikat venue evidence sehingga evidence `FILLED` dan `REJECTED` tidak lagi menghasilkan plan identity yang sama.
- Verifikasi: focused recovery **15/15 PASS**; recovery + identity/import matrix **38/38 PASS**; seluruh AutoTrade Next contracts **438/438 PASS**; Strategy2/dry-run regression **61/61 PASS**; `compileall` dan `git diff --check` exit 0.
- Verdict tetap **PARTIAL / Changes Requested**: durable startup/replay dan atomic correction commit belum diimplementasikan.

## Automated Review Repair — 2026-08-31 (Durable Completion)

- Menambahkan `SQLiteRecoveryStore` dengan snapshot JSON eksplisit (tanpa pickle), content verification, append-only head history, writer fence, expected checkpoint CAS, typed outcomes, dan reconciliation untuk indeterminate commit.
- Checkpoint schema `v5` sekarang menyimpan cash-ledger settlement entries, full `PolicyState`, applied correction IDs, inbox, pending outbox, projection high-water, Order/Position, pending command, preparation, dan freeze state sebagai satu consistency cut.
- Delivery acknowledgment dapat menghapus PENDING outbox tanpa menghapus historical preparation; restart tidak meredeliver pesan yang sudah acknowledged.
- Startup `load_recovery_plan` memulihkan checkpoint exact dan selalu menghasilkan plan `no_strategy_evaluation=True`; restart dengan `UNKNOWN` menghasilkan query-first tanpa submit/redelivery.
- Successor validation menolak history/cash rewrite, state removal, projection regression, correction bypass, serta perubahan account yang tidak ditopang append-only settlement ledger.
- Correction commit memakai typed authenticated approval port, exact high-water, fence, idempotency, audit row, applied-correction checkpoint binding, dan satu transaksi SQLite.
- Fault matrix membuktikan rollback sebelum commit, deterministic redelivery sesudah crash sebelum ack, reconciliation sesudah commit return hilang, restart process-equivalent, corruption fail-closed, dan atomic correction authorization.
- Verifikasi final: recovery/persistence + identity/import matrix **48/48 PASS**; seluruh AutoTrade Next contracts **449/449 PASS**; Strategy2/dry-run regression **69/69 PASS**; `compileall` dan `git diff --check` exit 0.
- Verdict final: **PASS / Approved**; seluruh acceptance criteria Story 2.6 terpenuhi pada canonical SQLite DRY RUN boundary.

## Operational Scope

- Implementasi dibatasi pada canonical AutoTrade Next DRY RUN SQLite boundary; tidak menambahkan live venue submission path atau credential.
- Deployment VM, exact SQLite runtime allowlist, backup/off-host checkpoint, dan composition-root rollout tetap merupakan deployment/readiness evidence lintas story, bukan defect acceptance criteria Story 2.6.

## File List

- `advanced_crypto_bot/autotrade_next/domain/recovery.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/ports/recovery.py`
- `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- `advanced_crypto_bot/autotrade_next/adapters/sqlite/recovery_store.py`
- `advanced_crypto_bot/autotrade_next/adapters/sqlite/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_recovery.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_sqlite_recovery_store.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-2-6-deterministic-recovery-plan.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Semantic deterministic recovery checkpoint/plan review-ready; durable restart dependency tetap terbuka.
- 2026-08-31: Adversarial review memperbaiki delapan defect semantic recovery; status dikembalikan ke `in-progress` karena durable startup/replay AC masih belum terpenuhi.
- 2026-08-31: Review loop 3 menutup durable startup/replay, complete checkpoint content, delivery acknowledgment, append-only history, dan authenticated atomic correction; status menjadi `done`.

## Senior Developer Review (AI) — 2026-08-31 (Review Loop 2)

**Reviewer:** Officer (AI-assisted)
**Outcome:** Changes Requested
**Git vs Story:** 0 discrepancy untuk perubahan story pada `51f1660..9dbde0c`; perubahan orchestration yang sedang dirty berada di `_bmad-output/` dan dikecualikan dari source review.

### Acceptance Criteria

- **Startup recovery ke high-water yang sama:** **PARTIAL**. Semantic checkpoint/plan memodelkan state dan sekarang lebih fail-closed, tetapi tidak ada durable loader, event payload replay, inbox/outbox acknowledgment restore, projection rebuild, atau process-crash proof.
- **Tanpa decision baru/duplicate submit:** **IMPLEMENTED pada semantic plan** setelah pending submit untuk `UNKNOWN`, mismatch, dan acknowledged order ditahan; `no_strategy_evaluation` tetap wajib `True`.
- **Query-before-resubmit:** **IMPLEMENTED pada semantic plan**; query result non-`UNKNOWN` kini dapat maju ke correction tanpa redelivery/redispatch.

### Findings dan Disposition

- **CRITICAL — fixed:** `UNKNOWN` masih meredeliver `IntentPrepared`, membuka duplicate submit sebelum query selesai.
- **HIGH — fixed:** Order yang sudah acknowledged masih dapat meredeliver initial submit.
- **HIGH — fixed:** Venue evidence non-`UNKNOWN` tidak pernah menghapus order dari query set, sehingga correction resolution mustahil.
- **HIGH — fixed:** Checkpoint hash tidak mengikat `pending_reason`, `pending_target_quantity`, `partial_exit`, dan metadata outbox lengkap.
- **HIGH — fixed:** Checkpoint menerima state lintas account/instrument, state di depan journal, atau preparation/outbox dengan isi berbeda tetapi ID sama.
- **HIGH — fixed:** Correction untuk target asing diterima.
- **MEDIUM — fixed:** Public `RecoveryPlan` menerima action graph yang secara semantic kontradiktif.
- **MEDIUM — fixed:** Plan identity tidak mengikat venue evidence; status/evidence berbeda dapat berbagi hash yang sama.
- **CRITICAL — open:** AC durable startup/replay dan atomic authenticated correction commit belum memiliki implementasi runtime.

### Task dan Test Audit

- Tiga task pada spec semantic terverifikasi selesai; tidak ditemukan task `[x]` yang palsu dalam batas spec tersebut.
- Regression tests ditambahkan untuk duplicate-submit guards, UNKNOWN resolution, checkpoint identity collision, cross-account/high-water rejection, foreign correction, plan invariants, dan evidence-bound identity.
- Referensi teknis primer diperiksa: Python `sqlite3` transaction control, SQLite atomic commit, dan SQLite WAL. Referensi ini menegaskan bahwa durability harus dibuktikan pada transaction/restart boundary, bukan hanya melalui immutable in-memory plan.

### Validation Checklist

- Story, Epic 2 context, epic requirements, config, spec, deferred work, seluruh File List, dan Git baseline telah dibaca.
- AC, task completion, source quality, security/fail-closed behavior, dan test quality telah diaudit.
- Review notes dan Change Log diperbarui; sprint status disinkronkan ke `in-progress`.

## Senior Developer Review (AI) — 2026-08-31 (Review Loop 3)

**Reviewer:** Officer (AI-assisted)
**Outcome:** Approved
**Git vs Story:** Tiga source/test files baru dan tiga export/import-matrix changes ditemukan saat review lalu ditambahkan ke File List; sesudah pembaruan tidak ada discrepancy source yang tersisa. Artifact `_bmad/`, `_bmad-output/`, orchestration, dan runtime config dikecualikan dari source-code review sesuai workflow.

### Acceptance Criteria

- **Startup recovery ke high-water yang sama:** **IMPLEMENTED**. Snapshot durable memulihkan Order, Position, account/cash ledger, full PolicyState, pending command, inbox/outbox, projection high-water, correction history, dan freeze state secara exact serta content-verified.
- **Tanpa decision baru/duplicate submit:** **IMPLEMENTED**. Loader hanya mendecode checkpoint dan memanggil pure recovery planner; tidak memiliki strategy callback. Crash sebelum ack hanya meredeliver message dan client-order identity yang sama, sedangkan acknowledged outbox tidak muncul kembali.
- **Query-before-resubmit:** **IMPLEMENTED**. `UNKNOWN` yang direstart tetap entry-frozen, selalu menghasilkan `QUERY_VENUE` pertama, dan tidak menghasilkan redispatch atau initial-submit redelivery.
- **Additive correction dengan evidence/approval:** **IMPLEMENTED**. Correction taxonomy domain, target/evidence/high-water validation, authenticated verifier port, writer fence, idempotency, audit record, checkpoint binding, dan commit atomik diuji fail-closed.

### Findings dan Disposition

- **CRITICAL — fixed:** Tidak ada durable startup loader atau crash/restart proof; ditutup oleh `SQLiteRecoveryStore`, explicit codec, head CAS, dan fault matrix.
- **HIGH — fixed:** Checkpoint hanya menyimpan string reference PolicyState, sehingga PolicyState tidak dapat direhidrasi; checkpoint `v5` menyimpan full content-bound state.
- **HIGH — fixed:** Cash balance disimpan tanpa append-only CashLedger; checkpoint kini membawa settlement entries dan successor memverifikasi cash/quantity/fee/tax dari ledger delta.
- **HIGH — fixed:** Historical preparation wajib selalu memiliki PENDING outbox, sehingga delivery acknowledgment mustahil dipersist; invariant kini membedakan preparation history dari pending delivery.
- **HIGH — fixed:** Snapshot successor dapat menulis ulang state/cash atau menurunkan projection; append-only successor validation dan exact high-water CAS menolak perubahan tersebut.
- **HIGH — fixed:** Correction belum authenticated/fenced/atomic; typed approval port dan satu SQLite transaction kini mengikat audit correction serta resulting checkpoint.
- **MEDIUM — fixed:** Idempotency correction tidak menjadi bagian recovered state; `applied_correction_refs` kini content-bound dan tidak dapat ditambahkan lewat generic checkpoint command.

### Task dan Test Audit

- Seluruh task semantic lama tetap terverifikasi; durable remediation ditambahkan dan diuji pada boundary sebelum commit, sesudah commit-return hilang, sebelum delivery ack, startup baru, corrupt payload, unauthorized correction, dan history rewrite.
- Final gates: **48/48** focused recovery/persistence/identity, **449/449** AutoTrade Next contracts, dan **69/69** Strategy2/dry-run regression PASS.
- Extended legacy `test_scalper_dryrun_positions.py` tidak termasuk gate 69-test dan tidak dapat dikoleksi pada environment ini karena dependency opsional `aiohttp` tidak terpasang; tidak ada import atau jalur scalper yang diubah oleh Story 2.6.
- Referensi primer: [Python sqlite3 transaction control](https://docs.python.org/3/library/sqlite3.html#transaction-control), [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html), dan [SQLite WAL](https://www.sqlite.org/wal.html).

### Validation Checklist

- Story berstatus `in-progress` akibat CRITICAL terbuka dari review loop 2, bukan `review`; invocation eksplisit user dipakai sebagai otorisasi melanjutkan review/fix non-interaktif. Story 2.6/Epic 2, context, epic requirements, architecture spine, implementation notes, config, spec, deferred work, Git state, dan seluruh source File List dibaca.
- Tidak ada Epic Tech Spec terpisah; `epic-2-context.md`, Epic 2 dalam `epics.md`, architecture spine, dan implementation notes dipakai sebagai sumber teknis pengganti dan warning ini dicatat.
- Semua AC dan task selesai dipetakan ke implementasi/test; code quality, security, approval boundary, corruption behavior, history monotonicity, and crash durability diaudit.
- Review notes, File List, Change Log, spec, deferred work, story status, dan sprint status disinkronkan; outcome **Approve**.
