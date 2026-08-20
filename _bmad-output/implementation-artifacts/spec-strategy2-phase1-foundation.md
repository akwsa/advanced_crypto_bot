---
title: 'Fondasi Strategi 2: kontrak, state machine, virtual ledger, dan taxonomy'
type: 'feature'
created: '2026-08-17'
status: 'done'
baseline_commit: '6e4f159'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-patient-net-profit-swing-autotrade-research-2026-08-16.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Bot belum memiliki fondasi terisolasi untuk Strategi 2 sehingga eksperimen patient net-profit swing berisiko mencampur state, cash, keputusan, atau lifecycle dengan Strategi 1. Tanpa kontrak typed dan ledger virtual sendiri, hasil shadow tidak dapat diaudit atau dibandingkan secara sah.

**Approach:** Tambahkan package Strategi 2 yang pure dan deterministic, taxonomy typed, state machine tervalidasi, serta repository SQLite dengan journal/projection namespaced. Seluruh kapabilitas default-off dan belum dihubungkan ke runtime atau private-order execution pada Fase 1.

## Boundaries & Constraints

**Always:** `AUTOTRADE_STRATEGY2_ENABLED` default `false`; mode yang diterima Fase 1 hanya `off` dan `shadow` serta nilai tidak valid harus fail-closed; seluruh row membawa strategy version dan identity/idempotency yang stabil; decision/state transition/portfolio mutation atomic dan idempotent; virtual cash dan position tidak boleh memakai `users.balance`, `trades`, atau tabel normalized Strategi 1; hard invalidation/protective stop tidak boleh diblokir kebijakan menunggu profit; input numerik harus finite dan valid; schema migration rerunnable.

**Ask First:** Integrasi ke signal worker/runtime; aktivasi shadow di VM; perubahan modal/default risk; penambahan order/fill simulator; deployment; segala akses private API atau live trading.

**Never:** Mengubah control flow, queue ack, cooldown, pair lock, taxonomy, cash, position, order, atau fill Strategi 1; membaca network/database/global config dari pure state reducer; mengklaim profitability; mengaktifkan feature flag dalam `.env`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Default startup | Flag tidak ada | Strategi 2 disabled dan mode efektif `off` | Tidak ada side effect |
| Valid transition | `CANDIDATE → ARMED` dengan event identity baru | Event tersimpan sekali dan projection menjadi `ARMED` | Replay mengembalikan hasil sama |
| Illegal transition | `CLOSED → OPEN_RISK` | Tidak ada row/projection/cash berubah | Typed transition error |
| Virtual entry | Cash cukup dan posisi belum open | Cash berkurang, posisi `OPEN_RISK`, event atomik | Rollback penuh saat invariant gagal |
| Virtual close | Posisi cukup dan proceeds/fee valid | Cash dikredit sekali, quantity turun/closed | Duplicate key no-op; oversell ditolak |
| Invalid numeric | NaN/Inf, harga/qty nonpositif, fee negatif/lebih besar proceeds | Tidak ada state berubah | `ValueError` fail-closed |
| Cross-strategy collision | Identity mirip Strategi 1 atau versi Strategy 2 lain | Namespace tetap terpisah | Tidak membaca/menulis ledger lain |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/autotrade/strategy2/contracts.py` -- immutable snapshots, decisions, cost assumptions, dan stable identities.
- `advanced_crypto_bot/autotrade/strategy2/taxonomy.py` -- enum lifecycle, decision status, reason code, dan terminal sets.
- `advanced_crypto_bot/autotrade/strategy2/state_machine.py` -- pure legal-transition validator/reducer.
- `advanced_crypto_bot/autotrade/strategy2/repository.py` -- atomic SQLite journal dan virtual portfolio/position projection.
- `advanced_crypto_bot/core/database.py` -- additive, rerunnable Strategy 2 schema creation only.
- `advanced_crypto_bot/core/config.py` dan `advanced_crypto_bot/.env.example` -- namespaced default-off configuration.
- `advanced_crypto_bot/tests/test_strategy2_*.py` -- contract, transition, accounting, idempotency, rollback, migration, dan isolation coverage.
- `advanced_crypto_bot/docs/autotrade-strategy2.md` -- operator/developer contract dan batas fase.

## Tasks & Acceptance

**Execution:**
- [x] `advanced_crypto_bot/autotrade/strategy2/` -- implement immutable contracts, typed taxonomy, dan pure state machine.
- [x] `advanced_crypto_bot/core/config.py`, `advanced_crypto_bot/.env.example` -- tambah flag/version/initial-cash namespaced dengan validasi fail-closed.
- [x] `advanced_crypto_bot/core/database.py`, `advanced_crypto_bot/autotrade/strategy2/repository.py` -- tambah schema Strategy 2 dan transaksi idempotent untuk decision, event, virtual cash, serta position projection tanpa menyentuh ledger Strategi 1.
- [x] `advanced_crypto_bot/tests/test_strategy2_contracts.py`, `advanced_crypto_bot/tests/test_strategy2_state_machine.py`, `advanced_crypto_bot/tests/test_strategy2_repository.py`, `advanced_crypto_bot/tests/test_strategy2_isolation.py` -- uji seluruh matrix, concurrency/replay, dan non-regression isolation.
- [x] `advanced_crypto_bot/docs/autotrade-strategy2.md` -- dokumentasikan state graph, taxonomy, config, invariants, rollback, dan promotion boundary.

**Acceptance Criteria:**
- Given konfigurasi produksi lama, when aplikasi memuat config dan database, then Strategi 2 tetap off dan seluruh perilaku/tabel Strategi 1 tidak berubah.
- Given snapshot, version, dan portfolio state identik, when evaluator/reducer dijalankan berulang, then decision dan identity identik tanpa clock/network/global mutable state.
- Given transaksi virtual valid atau replay, when repository memprosesnya, then journal, cash, dan position konsisten serta cash hanya didebit/dikredit sekali.
- Given transition, ownership, numeric, cash, atau quantity invalid, when repository menolak operasi, then seluruh perubahan rollback dan reason/error tetap spesifik.
- Given database baru maupun `_create_tables()` rerun, when schema diperiksa, then tabel/index Strategy 2 tersedia tanpa migrasi destruktif.
- Given targeted dan existing autotrade ledger tests, when suite dijalankan, then semuanya lulus tanpa akses jaringan/private API.

## Spec Change Log

## Design Notes

Repository menerima koneksi melalui `Database` tetapi hanya mengakses tabel `strategy2_*`. Event journal adalah sumber kebenaran; portfolio dan position adalah projection atomik yang dapat diverifikasi/rebuild pada fase lanjutan. Idempotency key harus mencakup `strategy_version`, `experiment_id`, dan operation identity. Fase 1 menyediakan policy contract, bukan sinyal entry produksi.

## Verification

**Commands:**
- `python -m pytest -q tests/test_strategy2_contracts.py tests/test_strategy2_state_machine.py tests/test_strategy2_repository.py tests/test_strategy2_isolation.py` -- seluruh contract dan invariant Fase 1 lulus.
- `python -m pytest -q tests/test_autotrade_ledger.py tests/test_autotrade_dispatch_lifecycle.py tests/test_signal_decision_layer_contracts.py` -- ledger/taxonomy Strategi 1 tidak regresi.
- `python -m compileall -q autotrade/strategy2 core/config.py core/database.py` -- seluruh modul dapat dikompilasi.

## Suggested Review Order

**Isolated accounting boundary**

- Repository owns namespaced idempotency, lifecycle, cash, and position atomicity.
  [`repository.py:82`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L82)

- Conflicting decision replay fails instead of silently changing immutable attribution.
  [`repository.py:122`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L122)

- Virtual entry debits cash and opens risk in one transaction.
  [`repository.py:204`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L204)

- Virtual close validates ownership and credits proceeds exactly once.
  [`repository.py:241`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L241)

- Additive tables keep every Strategy 1 ledger untouched.
  [`database.py:446`](../../advanced_crypto_bot/core/database.py#L446)

**Deterministic domain**

- Immutable strategy identity binds version, experiment, and operation.
  [`contracts.py:69`](../../advanced_crypto_bot/autotrade/strategy2/contracts.py#L69)

- Typed decisions reject illegal lifecycle transitions at construction.
  [`contracts.py:146`](../../advanced_crypto_bot/autotrade/strategy2/contracts.py#L146)

- Explicit transition graph keeps terminal states closed and protective exits available.
  [`state_machine.py:16`](../../advanced_crypto_bot/autotrade/strategy2/state_machine.py#L16)

**Default-off operation and evidence**

- Invalid modes fail closed; effective enablement requires shadow mode.
  [`config.py:126`](../../advanced_crypto_bot/core/config.py#L126)

- Tests cover replay conflicts, accounting, rollback, concurrency, and isolation.
  [`test_strategy2_repository.py:71`](../../advanced_crypto_bot/tests/test_strategy2_repository.py#L71)

- Operator contract documents lifecycle, rollback, and future promotion boundary.
  [`autotrade-strategy2.md:1`](../../advanced_crypto_bot/docs/autotrade-strategy2.md#L1)

## Suggested Review Order

**Settlement and Replay Safety**

- Entry point for atomic close/invalidation, replay fidelity, and finite-cash guardrails.
  [`repository.py:276`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L276)

- Transition path now rejects fresh same-state events that bypass replay identity.
  [`repository.py:180`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L180)

- Open-path payloads now stamp operation type and reject underflowed notionals.
  [`repository.py:222`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L222)

**Deterministic Contracts**

- Pair normalization now revalidates empties and freezes text fields deterministically.
  [`contracts.py:41`](../../advanced_crypto_bot/autotrade/strategy2/contracts.py#L41)

- Derived round-trip costs now fail closed on overflow instead of leaking infinity.
  [`contracts.py:114`](../../advanced_crypto_bot/autotrade/strategy2/contracts.py#L114)

- Feature and decision payload contracts now reject mutable or malformed inputs earlier.
  [`contracts.py:157`](../../advanced_crypto_bot/autotrade/strategy2/contracts.py#L157)

**Default-Off and Schema Repair**

- Invalid Strategy 2 initial cash now disables enablement instead of silently running.
  [`config.py:126`](../../advanced_crypto_bot/core/config.py#L126)

- Rerun-safe column repair hardens half-created Strategy 2 tables without touching Strategy 1.
  [`database.py:150`](../../advanced_crypto_bot/core/database.py#L150)

**Regression Evidence**

- Repository tests lock replay, invalidation, epsilon-close, and finite-cash regressions.
  [`test_strategy2_repository.py:134`](../../advanced_crypto_bot/tests/test_strategy2_repository.py#L134)

- Isolation tests prove fail-closed config and additive schema repair behavior.
  [`test_strategy2_isolation.py:24`](../../advanced_crypto_bot/tests/test_strategy2_isolation.py#L24)
