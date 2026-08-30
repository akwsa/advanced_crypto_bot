---
story_id: "3.1"
title: "Menegakkan fenced command authority"
epic: "3"
status: "review"
baseline_commit: "7da4fe9"
---

# Story 3.1: Menegakkan fenced command authority

Status: review

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
- `advanced_crypto_bot/tests/autotrade_next/contract/test_sqlite_fenced_journal.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-3-1-durable-fenced-journal.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Durable fenced journal foundation review-ready; runtime wiring/migration evidence tetap terbuka.
