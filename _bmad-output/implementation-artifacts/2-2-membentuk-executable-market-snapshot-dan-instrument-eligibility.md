---
story_id: "2.2"
title: "Membentuk executable MarketSnapshot dan instrument eligibility"
epic: "2"
status: "ready-for-dev"
baseline_commit: "7d1cf495bed5d3828105d3d3052c4162ffacc46a"
---

# Story 2.2: Membentuk executable MarketSnapshot dan instrument eligibility

Status: done

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
