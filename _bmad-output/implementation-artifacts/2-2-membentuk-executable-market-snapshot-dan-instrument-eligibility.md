---
story_id: "2.2"
title: "Membentuk executable MarketSnapshot dan instrument eligibility"
epic: "2"
status: "review"
baseline_commit: "5a83c99bc67f44917ac08188b45003c057bd88cb"
---

# Story 2.2: Membentuk executable MarketSnapshot dan instrument eligibility

Status: review

## Story

As a Officer,
I want Candidate memakai depth dan rules point-in-time pada requested size,
so that DRY RUN tidak mengisi order pada candle/last price yang tidak executable.

## Acceptance Criteria

1. **MarketSnapshot L2 Point-in-Time & Requested Size**:
   - `MarketSnapshot` menyimpan ordered L2 depth (bids & asks) yang mencukupi `requested_size` target.
   - Bids terurut menurun (*descending price*), Asks terurut menaik (*ascending price*).
   - Menyimpan event time & receive time UTC terpisah, serta exact cursors.
   - Menghitung weighted average executable price dan available capacity secara deterministik.

2. **Instrument Eligibility & Metadata Bounds**:
   - Memvalidasi minimum order size, price/quantity precision & step increment, maximum spread threshold, evidence freshness, depth coverage, dan universe membership efektif-waktu.
   - Kegagalan salah satu kriteria menghasilkan status pair-local `INELIGIBLE/ABSTAIN` dengan `EligibilityReason` spesifik tanpa menebak fallback/last price.

3. **Systemic Integrity Failure Handling**:
   - Kegagalan sistemik/shared source integrity membekukan entry portfolio tetapi tetap mempertahankan protective exit dan recovery path.

4. **100% Deterministic Execution & Contract Tests**:
   - Penentuan executable price dan capacity harus 100% deterministik tanpa pembulatan mengambang (menggunakan `ScaledInteger` / exact decimal representation).

## Implementation Plan

- Bekukan rules instrumen, universe membership efektif-waktu, quality evidence, requested size, dan execution side di dalam content-bound snapshot.
- Validasi invariant struktural order book saat konstruksi; evaluasi precision, increment, spread, freshness, membership, metadata, dan depth sebagai veto pair-local.
- Hitung capacity serta WAP dengan integer/common-scale math; pembulatan konservatif ASK-ceil dan BID-floor.
- Bedakan kegagalan source integrity sistemik melalui immutable portfolio entry-freeze signal tanpa persistence atau mutasi safety state.

## Completion Evidence — 2026-08-30

- RED: focused contract run menghasilkan 14 gagal dan 7 lulus karena `execution_side` belum menjadi bagian snapshot.
- GREEN final: focused Story 2.2 plus simulator compatibility menghasilkan 26/26 lulus.
- Full AutoTrade Next contract suite: 324/324 lulus.
- Strategy2 dan dry-run regression suite: 61/61 lulus.
- `compileall` untuk `autotrade_next`: exit 0.
- `git diff --check`: exit 0.
- Audit/review independen belum selesai; karena itu status faktual adalah `review`, bukan `done`.

## File List

- `advanced_crypto_bot/autotrade_next/domain/market.py`
- `advanced_crypto_bot/autotrade_next/domain/simulator.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_market_snapshot_eligibility.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py`
- `_bmad-output/implementation-artifacts/spec-2-2-market-snapshot-eligibility-remediation.md`
- `_bmad-output/implementation-artifacts/2-2-membentuk-executable-market-snapshot-dan-instrument-eligibility.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/deferred-work.md`

## Change Log

- 2026-08-30: Remediasi kontrak executable snapshot dan eligibility dibuat review-ready berdasarkan audit faktual migrasi.
- 2026-08-30: Review loop 1 memperbaiki arithmetic simulator mixed-scale atas persetujuan eksplisit pengguna; RED 1 gagal/2 lulus, GREEN simulator 3/3 dan combined focused 24/24 setelah hardening review.
