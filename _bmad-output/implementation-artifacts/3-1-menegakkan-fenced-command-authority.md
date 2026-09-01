---
story_id: "3.1"
title: "Menegakkan fenced command authority"
epic: "3"
status: "done"
baseline_commit: "7da4fe9"
---

# Story 3.1: Menegakkan fenced command authority

Status: done

## Story

As a Officer,
I want hanya satu writer epoch dapat melakukan canonical mutation,
so that restart, takeover, atau network partition tidak menciptakan split brain.

## Acceptance Criteria

1. **Fenced Writer Authority**:
   - Menegakkan `FencedWriterAuthority` yang mengelola `epoch` dan `lease_token` secara monotonik.
   - Penolakan mutasi mutlak (*fail-closed*) jika epoch/token yang dibawa oleh command lebih kecil dari epoch aktif (*stale epoch*).

## Factual Reopen — 2026-08-30

- Baseline audit E14/R01: **FAIL**; committed domain guard menerima future epoch dengan forged token.
- Dirty perubahan user/Gemini pada `domain/fencing.py` menolak future epoch, tetapi belum committed dan tidak membuktikan authority persistence atau atomic append.
- Remediasi Codex dibatasi pada adapter/test/file dokumentasi baru agar perubahan user tidak ditimpa atau diambil alih.
- Target verdict maksimal **PARTIAL** sampai runtime wiring dan migration/restart proof tersedia.

## Completion Evidence — 2026-08-30

- Review-ready implementation commit: `1094c7704bbde23f673a460c7835f223337ff3ad`.
- RED: collection gagal karena `autotrade_next.adapters.sqlite` belum ada.
- GREEN awal 15/15; review final durable fencing 19/19 PASS.
- Fencing+identity/import 42/42 PASS; seluruh AutoTrade Next contracts 397/397 PASS.
- Canonical Strategy2/dry-run regression command 61/61 PASS; `compileall` dan `git diff --check` exit 0.
- SQLite adapter memakai `BEGIN IMMEDIATE`, satu authority row per scope, exact expected-epoch CAS, epoch `+1`, token history non-reuse, dan idempotent immutable claim identity.
- Append transaction memverifikasi exact scope/epoch/token, authoritative lease window, backward clock, dan expected sequence sebelum atomically menulis command journal, event, pending outbox, serta aggregate high-water.
- Stale/future epoch, token loss, expired lease, clock anomaly, sequence conflict, identity reuse, dan `SQLITE_BUSY` memberi typed fail-closed outcome dengan nol stale write.
- Crash-before-commit terbukti rollback; indeterminate commit return direkonsiliasi memakai immutable command/claim identity. Adapter tidak mengimpor network/Redis.
- Factual verdict **PARTIAL**: belum ada wiring seluruh canonical mutation, schema migration/cutover, multi-process restart matrix, atau deployment evidence.

## File List

- `advanced_crypto_bot/autotrade_next/adapters/sqlite/__init__.py`
- `advanced_crypto_bot/autotrade_next/adapters/sqlite/fenced_journal.py`
- `advanced_crypto_bot/autotrade_next/domain/fencing.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_sqlite_fenced_journal.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_fencing.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_sqlite_recovery_store.py`
- `_bmad-output/implementation-artifacts/spec-3-1-durable-fenced-journal.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Durable fenced journal foundation review-ready; runtime wiring/migration evidence tetap terbuka.
- 2026-08-31: Senior Developer Review (AI) memperbaiki 6 HIGH dan 3 MEDIUM findings; 64 focused, 463 AutoTrade Next, dan 63 Strategy2/dry-run tests lulus; workflow status menjadi `done` dengan factual capability verdict tetap PARTIAL karena runtime wiring, qualified migration, dan deployment evidence tetap deferred.

## Senior Developer Review (AI)

**Reviewer:** Officer (AI-assisted)

**Tanggal:** 2026-08-31

**Outcome:** Approve untuk scope durable fenced-journal foundation Story 3.1

**Workflow status:** done

**Factual capability verdict:** PARTIAL — seluruh canonical mutation belum di-wire ke adapter, production schema migration/cutover belum tersedia, dan multi-process restart/deployment evidence tetap deferred serta tidak diklaim selesai.

### Review Context

- Initial story status `review`; Story ID `3.1` dan Epic `3` terverifikasi. Tidak ada `project-context.md` atau Epic 3 Tech Spec terpisah; `epics.md`, `spec-3-1-durable-fenced-journal.md`, Architecture Spine, dan Implementation Notes dipakai sebagai context/standards.
- Target stack architecture adalah CPython 3.12.14, SQLite 3.53.4, dan uv 0.11.15. Gate lokal berjalan pada CPython 3.12.3, SQLite 3.45.1, dan uv 0.11.13; hasil lokal membuktikan contract semantics, bukan qualified runtime readiness.
- Documentation lookup memakai web fallback ke dokumentasi primer SQLite/Python yang direkam pada Verification Evidence.

### Validasi Acceptance Criteria

1. **Fenced Writer Authority — IMPLEMENTED untuk durable foundation.** `FencedWriterAuthority` dan `SQLiteFencedJournal` menolak stale/future epoch, scope/token mismatch, token reuse, active-lease takeover, lease expiry, dan clock rollback secara fail-closed. Claim persisten memakai satu row per scope, exact expected-epoch CAS, epoch `+1`, dan token history non-reuse.
2. **Atomic fenced append — IMPLEMENTED untuk adapter scope.** `BEGIN IMMEDIATE` membungkus exact scope/epoch/token/lease/sequence verification bersama journal, event, outbox, dan high-water write. Busy, storage, crash-before-commit, dan indeterminate return memiliki typed outcome; retry immutable tetap idempotent dan adapter transaction tidak mengimpor network/Redis.
3. **Runtime-wide single writer — PARTIAL dan tetap deferred.** Story tidak mengklaim bahwa seluruh handler canonical sudah memakai adapter atau bahwa production migration/restart/cutover telah dibuktikan. Batas factual ini tetap tercatat pada Completion Evidence dan deferred work.

### Findings dan Disposition

- **HIGH — FIXED:** Append baseline mempercayai `current_time_utc` dari command, sehingga stale writer dapat memalsukan waktu lease. Waktu observasi kini berasal dari injected trusted clock dan bukan bagian command envelope (`adapters/sqlite/fenced_journal.py`).
- **HIGH — FIXED:** Takeover baseline dapat menaikkan epoch selama lease aktif. Claim kini menghasilkan `LEASE_ACTIVE` sampai authoritative expiry dan contract membuktikan nol perubahan authority (`adapters/sqlite/fenced_journal.py`, `test_sqlite_fenced_journal.py`).
- **HIGH — FIXED:** Runtime connection dapat membuat database kosong saat file canonical hilang. Runtime kini membuka URI `mode=rw`; hanya helper schema test yang boleh membuat file (`adapters/sqlite/fenced_journal.py`).
- **HIGH — FIXED:** Clock callback invalid/gagal dapat melempar exception mentah setelah transaction dimulai. Claim/append kini memetakan kegagalan clock ke typed `CLOCK_ANOMALY` dengan nol write (`adapters/sqlite/fenced_journal.py`).
- **HIGH — FIXED:** Storage error dan reconciliation read yang gagal dapat melempar exception mentah atau menghilangkan status commit. Precommit failure kini `STORAGE_FAILURE`; reconciliation yang tidak dapat membuktikan commit tetap `INDETERMINATE_COMMIT` (`adapters/sqlite/fenced_journal.py`).
- **HIGH — FIXED:** Contract story dan recovery integration masih memakai constructor, `initialize()`, dan command timestamp lama sehingga focused audit awal gagal 19 test. Seluruh caller/test dimigrasikan ke trusted clock dan `initialize_schema_for_test()` (`test_sqlite_fenced_journal.py`, `test_sqlite_recovery_store.py`).
- **MEDIUM — FIXED:** Rollback failure dapat menimpa typed outcome asli. Rollback sekarang best-effort dan connection close tetap menjadi boundary fail-closed terakhir (`adapters/sqlite/fenced_journal.py`).
- **MEDIUM — FIXED:** Future epoch, invalid value-object state, clock rollback, dan token reuse domain tidak mempunyai regression coverage yang memadai (`test_fencing.py`).
- **MEDIUM — FIXED:** Dependency allowlist dan story File List tidak mengikuti import/caller/source yang benar; matrix dan File List sudah disinkronkan (`test_identity_vectors.py`, story File List).

### Task, Test, dan Git Audit

- Story tidak mempunyai bagian Tasks/Subtasks atau checkbox `[x]`; tidak ada task completed yang dapat diaudit sebagai false claim. Seluruh invariant dan verification item pada story spec dipetakan ke implementation/tests.
- Commit implementation Story 3.1 diverifikasi pada `bcfac1683d433854d3c14a727b39e1f1948a612a..1094c7704bbde23f673a460c7835f223337ff3ad`; seluruh source/test File List dibaca. Review juga memeriksa perubahan source lokal pada `domain/fencing.py` dan `adapters/sqlite/fenced_journal.py` serta caller recovery yang terdampak.
- Perubahan lokal `_bmad-output/story-automator/orchestration-2-20260827-163501.md` sudah ada sebelum review, bukan application source Story 3.1, dan dipertahankan tanpa modifikasi oleh review ini.

### Verification Evidence

- `python -m pytest -q tests/autotrade_next/contract/test_sqlite_fenced_journal.py tests/autotrade_next/contract/test_fencing.py tests/autotrade_next/contract/test_identity_vectors.py tests/autotrade_next/contract/test_sqlite_recovery_store.py` → **64 passed**.
- `python -m pytest -q tests/autotrade_next` → **463 passed**.
- `python -m pytest -q tests/test_strategy2_*.py tests/test_autotrade_dryrun_signal_cycle.py tests/test_dryrun_safety.py` → **63 passed**.
- `python -m compileall -q autotrade_next` dan `git diff --check` → exit 0.
- Dokumentasi primer diperiksa: SQLite [`BEGIN IMMEDIATE` dan transaction outcomes](https://www.sqlite.org/lang_transaction.html) serta Python [`sqlite3.connect` URI `mode=rw` dan exception hierarchy](https://docs.python.org/3.12/library/sqlite3.html).

### Validation Checklist

- Story/status/ID, config, story spec, epic requirements, architecture standards, Git baseline, File List, stack, dan documentation lookup telah diperiksa; warning context/epic-tech-spec yang tidak tersedia dicatat.
- Seluruh AC/spec invariant dipetakan ke source/test; code quality, security/fail-closed behavior, transaction atomicity, error handling, dependency isolation, dan test quality telah diaudit.
- Sembilan findings telah diperbaiki tanpa action item tersisa; review notes, Change Log, story status, File List, dan sprint status disinkronkan. Outcome **Approve** untuk durable foundation, dengan runtime capability tetap **PARTIAL**.
