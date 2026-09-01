---
story_id: "3.2"
title: "Mengalokasikan exposure dan reservation secara atomik"
epic: "3"
status: "done"
baseline_commit: "379360c"
---

# Story 3.2: Mengalokasikan exposure dan reservation secara atomik

Status: done

## Story

As a Officer,
I want seluruh Candidate pada cutoff yang sama berbagi satu portfolio/risk consistency cut,
so that pair, Horizon, capacity, dan exposure tidak bergantung pada scan order atau stale Fill state.

## Acceptance Criteria

1. **Frozen Atomic Batch Commit**
   - **Given** frozen opportunity set, equity, market cutoff, journal high-water, Positions, working orders, dan RiskState.
   - **When** `PortfolioAllocation` meng-commit batch.
   - **Then** final Decisions, unique pair-to-Horizon ownership, reservations, RiskState, event, dan outbox committed melalui satu fenced expected-sequence CAS tanpa partial executable batch.
   - **And** stale constituent checkpoint menolak seluruh risk-increasing batch dengan structured reason.

2. **Reservation Conservation**
   - **Given** partial/multiple Fill atau terminal cancel/reject/expiry.
   - **When** reservation berubah.
   - **Then** notional, planned loss, fees, slippage/impact buffer, dan turnover memenuhi `initial = consumed + active_remainder + released`; UNKNOWN/partial tidak melepaskan remainder dan rounding residual tetap reserved sampai terminal evidence.

## Factual Reopen — 2026-08-30

- Baseline audit E15/R04: **PARTIAL**; conservation membandingkan raw units lintas scale dan tidak memodelkan batch consistency cut maupun lima risk dimensions.
- Remediasi pure-domain di file bersih; dirty `numeric.py` dan `accounting.py` tidak disentuh atau dijadikan dependency.
- Target verdict tetap **PARTIAL** sampai atomic persistence wiring ke Story 3.1 tersedia.

## Completion Evidence — 2026-08-30

- Review-ready implementation commit: `e8e3a39e77ca021fae0bf189d2d70fa0176bf298`.
- RED: import/collection gagal karena atomic allocation types belum ada.
- Focused allocation 8/8; allocation+identity/import 31/31 PASS.
- Seluruh AutoTrade Next contracts 404/404; canonical Strategy2/dry-run regression 61/61 PASS.
- `compileall` dan `git diff --check` exit 0.
- Reservation sekarang memiliki exact common-scale conservation untuk notional, planned loss, fees, slippage/impact, dan turnover. Multiple/partial Fill content-bound; UNKNOWN dan partial mempertahankan remainder/residual sampai terminal evidence.
- Frozen cut mengikat opportunity set, equity, market cutoff, journal high-water, positions, working orders, RiskState, dan observed constituent checkpoints.
- Batch deterministic/scan-order independent menolak stale checkpoint, duplicate decision/reservation/pair ownership, dan equity overflow tanpa executable subset. Accepted/rejected refs diregenerasi dari preimage sehingga caller tidak dapat self-attest event/outbox.
- Factual verdict tetap **PARTIAL**: belum ada application handler yang mem-persist final decisions, reservations, RiskState, event, dan outbox melalui satu fenced expected-sequence CAS.

## Review Resolution — 2026-09-01

- Verdict dinaikkan menjadi **DONE** setelah application handler, typed port, dan `SQLiteFencedJournal.append_allocation()` mengikat final Decision payload, reservation lima dimensi, pair-to-Horizon ownership, next RiskState payload, canonical event, serta outbox `PENDING` dalam satu `BEGIN IMMEDIATE` expected-sequence CAS.
- Seluruh payload Decision/RiskState diverifikasi terhadap `ContentRef` sebelum lock transaksi; transaksi SQLite hanya menjalankan operasi lokal dan idempotency membedakan append event biasa dari portfolio allocation.
- Frozen cut sekarang mewajibkan observed checkpoint untuk opportunity set, market cutoff, journal high-water, Positions, working orders, dan RiskState.
- Review juga menutup fake zero Fill, `FILLED` tanpa Fill, reservation pada proposal non-risk-increasing, serta duplicate pair ownership berbasis case alias.
- Evidence: focused Story 3.2/3.1/identity 67/67 PASS; seluruh AutoTrade Next contracts 475/475 PASS; Strategy2/dry-run regression 63/63 PASS; `compileall` dan `git diff --check` exit 0.

## File List

- `advanced_crypto_bot/autotrade_next/domain/portfolio_allocation.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/ports/portfolio_allocation.py`
- `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- `advanced_crypto_bot/autotrade_next/application/portfolio_allocation.py`
- `advanced_crypto_bot/autotrade_next/application/__init__.py`
- `advanced_crypto_bot/autotrade_next/adapters/sqlite/fenced_journal.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_portfolio_allocation.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_portfolio_allocation_persistence.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-3-2-atomic-portfolio-allocation.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Atomic allocation semantic kernel review-ready; fenced persistence composition tetap terbuka.
- 2026-09-01: Senior review menutup tujuh finding, menambahkan fenced atomic persistence, dan menyetujui Story 3.2 sebagai done.

## Senior Developer Review (AI)

**Reviewer:** Officer

**Tanggal:** 2026-09-01

**Outcome:** Approve

### Ringkasan Temuan dan Perbaikan

- **HIGH — AC atomic persistence belum diterapkan:** kernel hanya menghasilkan reference. Diperbaiki dengan handler `allocate_portfolio`, typed commit bundle, dan satu transaksi fenced CAS yang menyimpan batch, Decisions, reservations, ownership, RiskState, event, outbox, dan aggregate high-water.
- **HIGH — consistency cut belum mengobservasi semua constituent:** opportunity set, market cutoff, dan journal high-water dapat stale tanpa penolakan. Ketiganya sekarang menjadi checkpoint wajib dan diuji fail-closed.
- **HIGH — risk direction dapat digunakan untuk menyelundupkan reservation:** proposal `risk_increasing=False` dengan reservation nonzero sekarang ditolak.
- **HIGH — lifecycle `FILLED` dapat dibuat tanpa Fill:** transition tersebut sekarang membutuhkan minimal satu applied Fill.
- **HIGH — Decision/RiskState payload dapat self-attested sebagai reference saja:** `AllocationContentRecord` sekarang memverifikasi payload terhadap `ContentRef` dan menyimpan canonical bytes immutable.
- **MEDIUM — zero-value Fill dapat menciptakan lifecycle PARTIAL palsu:** konsumsi Fill sekarang membutuhkan notional dan turnover positif.
- **MEDIUM — case alias dapat melewati unique pair ownership:** uniqueness sekarang memakai case-folded pair identity.

### Validasi Acceptance Criteria

- Frozen consistency cut dan stale rejection: **PASS**.
- Satu fenced expected-sequence CAS tanpa partial executable batch: **PASS**, termasuk stale epoch, crash-before-commit, indeterminate commit reconciliation, dan idempotent retry.
- Conservation lima dimensi pada partial/multiple Fill serta terminal release: **PASS**.
- Security/code quality: payload content-bound, tidak ada network/Redis call di transaction, pair ownership dan risk-direction bypass tertutup.
- Story tidak memiliki bagian Tasks/Subtasks bertanda selesai; karena itu tidak ada completed-task claim yang dapat diaudit sebagai false completion.
- Dedicated Epic 3 context tidak tersedia. Review memakai `epics.md`, spec Story 3.2, dan Architecture Spine sebagai authoritative context; warning ini tidak memblokir karena AC dan invariants lengkap tersedia pada ketiga artefak tersebut.

### Evidence dan Referensi

- 67 focused contract tests: **PASS**.
- 475 AutoTrade Next contract tests: **PASS**.
- 63 Strategy2/dry-run regression tests: **PASS**.
- `python -m compileall` dan `git diff --check`: **PASS**.
- Satu legacy collection tambahan tidak dijalankan karena environment tidak memasang dependency `aiohttp` yang sudah tercantum pada `requirements.txt`; tidak ada perubahan Story 3.2 pada jalur tersebut.
- Desain transaksi dicocokkan dengan dokumentasi resmi [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html), dan [Python sqlite3 transaction control](https://docs.python.org/3/library/sqlite3.html#transaction-control).

### Git vs Story

- Implementasi awal Story 3.2 telah berada pada commit `e8e3a39`; karena itu file lama tidak muncul sebagai uncommitted diff saat review dan bukan false claim.
- Seluruh file source/test yang berubah akibat review telah ditambahkan ke File List.
- Perubahan user pada `_bmad-output/story-automator/orchestration-2-20260827-163501.md` tidak terkait dan dikecualikan dari review.
