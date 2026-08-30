---
title: "Spec Story 3.1 — Durable Fenced Journal"
story: "3.1"
status: done
baseline_commit: "bcfac1683d433854d3c14a727b39e1f1948a612a"
date: "2026-08-30"
---

# SPEC Kernel

## Intent

Menyediakan foundation SQLite yang membuktikan satu authority row per scope, takeover dengan `BEGIN IMMEDIATE` compare-and-swap, serta canonical append yang memverifikasi exact scope/epoch/token/lease dan expected aggregate sequence di transaksi yang sama.

## Scope

- File adapter dan test baru; tidak mengedit dirty `domain/fencing.py` milik user/Gemini.
- Claim identity idempotent, epoch meningkat tepat satu, token tidak dapat dipakai ulang.
- Atomic journal/event/outbox/high-water append dengan typed fail-closed outcome.
- Bukti stale/future epoch, token loss, expired lease, backward clock, sequence conflict, `SQLITE_BUSY`, crash-before-commit, dan indeterminate commit return.
- Tidak ada network/Redis call dalam transaction boundary.

## Out of Scope

- Runtime wiring ke settlement/EXIT/recovery handler.
- Production schema migration/cutover dan VM deployment.
- Mengambil alih atau memasukkan perubahan uncommitted user/Gemini ke commit Codex.

## Invariants

1. Satu row `writer_authority` per scope; hanya exact expected epoch boleh takeover.
2. Epoch baru selalu `active_epoch + 1`; token baru non-empty dan belum pernah digunakan pada scope tersebut.
3. Command retry hanya idempotent bila seluruh immutable input sama; reuse identity berbeda fail closed.
4. Append sah hanya pada exact active epoch/token dan waktu `granted <= now < expires`.
5. Expected sequence diverifikasi sebelum journal, event, outbox, dan high-water committed atomically.
6. Kegagalan sebelum commit meninggalkan nol write; hasil commit indeterminate direkonsiliasi melalui command identity.
7. Adapter transaksi hanya menggunakan SQLite dan deterministic local values, tanpa network.

## Verification Plan

- RED: contract test mengimpor adapter yang belum ada.
- GREEN: focused durable fencing contracts.
- Regression: seluruh AutoTrade Next contracts dan Strategy2/dry-run suite.
- Static: `compileall`, AST/import isolation, dan `git diff --check`.

## Completion Policy

Implementasi adapter dapat menaikkan verdict audit Story 3.1 dari FAIL menjadi paling tinggi PARTIAL. PASS memerlukan wiring seluruh canonical mutation, production migration, serta crash/restart/process evidence.

## Execution Record

- RED: import/collection gagal karena package adapter SQLite belum ada.
- GREEN awal: 15/15 focused contracts PASS.
- Review fix: deterministic connection close; claim-path busy, crash-before-commit, dan indeterminate-return coverage; architecture allowlist tetap sempit.
- Final: durable fencing 19/19; fencing+identity/import 42/42; all AutoTrade Next 397/397; Strategy2/dry-run 61/61; compile/diff gates PASS.
- Disposition: implementation scope selesai; Story tetap `review/PARTIAL` berdasarkan Completion Policy.
