---
story_id: "2.3"
title: "Menjalankan satu deterministic simulator lifecycle"
epic: "2"
status: "done"
baseline_commit: "13c46fa231deb0de4606cea60f10e496c03f3877"
---

# Story 2.3: Menjalankan satu deterministic simulator lifecycle

Status: done

## Story

As a Officer,
I want historical replay dan live DRY RUN memakai venue lifecycle serta simulator version yang sama,
so that evidence fill tidak berasal dari model berbeda.

## Acceptance Criteria

1. **Deterministic Order Simulator Lifecycle**:
   - Mendukung status order: ACCEPTED, OPEN, PARTIAL, FILLED, CANCELLED, REJECTED, EXPIRED, UNKNOWN.
   - Mengimplementasikan book walk, maker/taker fees, fee tax, precision, partial/non-fill, adverse selection, dan cancel/fill race scenarios secara deterministik dengan seed.
   - Event schema yang dihasilkan simulator identik dengan schema `VenuePort` lifecycle.

2. **Negative Isolation & Security**:
   - Mode DRY RUN memverifikasi bahwa live trade submission adapter tidak dapat di-import/diakses dan credential transaksi live tidak ada/tidak dapat dibaca.

## Implementation Plan

- Gunakan immutable versioned scenario dan cost rules sebagai seluruh entropy simulator.
- Bentuk ordered lifecycle event stream dengan legal-transition reducer dan canonical content references.
- Gunakan schema `SimulatorEvent` yang sama pada simulator dan `VenuePort` Protocol.
- Pertahankan `simulate_execution` sebagai compatibility wrapper untuk consumer Story 2.2/2.4.
- Buktikan dependency graph simulator tidak memiliki I/O, live-submit path, atau credential provider.

## Completion Evidence — 2026-08-30

- RED focused: 2 collection errors karena lifecycle contracts dan `ports.venue` belum tersedia.
- GREEN focused awal: 14/14 PASS; setelah boundary dan adversarial hardening: 18/18 PASS.
- Identity/import matrix plus focused contracts: 39/39 PASS.
- Seluruh AutoTrade Next contract suite: 339/339 PASS.
- Strategy2/dry-run regression: 61/61 PASS.
- `compileall` dan `git diff --check`: exit 0.
- Dua adversarial reviewer selesai dan seluruh patch tervalidasi; acceptance pengguna diterima melalui instruksi `continue` pada 2026-08-30.

## File List

- `advanced_crypto_bot/autotrade_next/domain/simulator.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/ports/venue.py`
- `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_dry_run_isolation.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-2-3-deterministic-simulator-lifecycle-remediation.md`
- `_bmad-output/implementation-artifacts/2-3-menjalankan-satu-deterministic-simulator-lifecycle.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Story 2.3 diremediasi dari enum-only/single-terminal simulator menjadi review-ready deterministic lifecycle stream.
- 2026-08-30: Human acceptance diterima; status Story 2.3 disinkronkan ke `done`.
