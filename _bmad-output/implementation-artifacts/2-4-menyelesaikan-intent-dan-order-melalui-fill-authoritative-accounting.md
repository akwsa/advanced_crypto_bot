---
story_id: "2.4"
title: "Menyelesaikan Intent dan Order melalui Fill-authoritative accounting"
epic: "2"
status: "review"
baseline_commit: "6a215cea3ff470c7a3f980e4acbede84d56bd548"
---

# Story 2.4: Menyelesaikan Intent dan Order melalui Fill-authoritative accounting

Status: review

## Story

As a Officer,
I want setiap execution effect dicatat sekali dan hanya Fill mengubah cash/exposure,
so that partial/retry tidak menciptakan ghost Position atau P&L ganda.

## Acceptance Criteria

1. **Fill-Authoritative Accounting**:
   - Hanya Fill yang dapat mengubah cash, fee, tax, quantity, dan Position.
   - Acknowledgment submission tanpa Fill tidak pernah mengubah balance/position.
   - Venue Fill ID dideduplikasi secara eksplisit; duplicate/delayed fill tidak menghasilkan double accounting.

## Implementation Plan

- Tambahkan canonical execution domain terpisah tanpa mengubah dirty compatibility `accounting.py`.
- Gunakan identity recipes existing untuk Intent, client order, dan outbox event.
- Settle hanya suffix fill baru dari cumulative Story 2.3 lifecycle evidence.
- Letakkan prepare-before-dispatch dan atomic settlement di transaction-scoped UnitOfWork port.
- Pertahankan status PARTIAL sampai durable SQLite/fence/migration foundation tersedia.

## Completion Evidence — 2026-08-30

- RED: collection error `autotrade_next.application` belum tersedia.
- Focused settlement + AST matrix: 37/37 PASS setelah adversarial patch.
- Seluruh AutoTrade Next contracts: 353/353 PASS.
- Strategy2/dry-run regression: 63/63 PASS.
- `compileall` dan `git diff --check`: exit 0.
- Semantic atomicity/fault rollback terbukti dengan reference UoW; durable production commit belum terbukti.
- Stream lifecycle Story 2.3 diuji end-to-end ke settlement, termasuk notional coarse quote-scale hasil conservative rounding tanpa rewrite evidence.
- Blind review dan edge-case review menemukan lalu memicu patch untuk event-time/schema/scale guards, UNKNOWN freeze, account revision CAS, composite binding, fill-history split-brain, provenance entry, serta cleanup transaksi.
- Factual verdict: **PARTIAL**, bukan PASS/done.

## Known Limits / Dependency Blockers

- Belum ada SQLite production adapter, persistent writer fence, offline migration, atau crash/restart proof.
- `AccountState` adalah semantic account-instrument slice. Canonical account-cash/per-instrument-position persistence dan cross-instrument CAS/reservation harus diputuskan di Story 3.1/3.2/5.3.
- Freeze UNKNOWN telah menjadi kontrak UoW untuk mencegah entry baru pada scope/account yang sama, tetapi recovery/persistence freeze lintas proses belum tersedia.
- Story 2.4 sengaja membatasi satu order ordinal (`0`) per Intent sampai multi-order reservation semantics dispecifikasikan.

## File List

- `advanced_crypto_bot/autotrade_next/domain/execution.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/ports/settlement.py`
- `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- `advanced_crypto_bot/autotrade_next/application/settlement.py`
- `advanced_crypto_bot/autotrade_next/application/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_fill_settlement_kernel.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-2-4-fill-authoritative-settlement-kernel.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Semantic settlement kernel menjadi review-ready; durability dependency tetap terbuka.
- 2026-08-30: Adversarial review iteration 1 ditutup dengan regression guards dan factual verdict tetap PARTIAL.
