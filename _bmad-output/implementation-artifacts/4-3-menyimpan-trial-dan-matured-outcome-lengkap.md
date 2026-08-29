---
story_id: "4.3"
title: "Menyimpan Trial dan matured outcome lengkap"
epic: "4"
status: "done"
baseline_commit: "e50542f"
---

# Story 4.3: Menyimpan Trial dan matured outcome lengkap

Status: done

## Story

As a Officer,
I want setiap percobaan serta outcome Candidate tercatat termasuk kegagalan,
so that multiple testing dan selection bias tidak dapat disembunyikan.

## Acceptance Criteria

1. **Trial Ledger & Outcome Classification**:
   - Mencatat seluruh trial eksekusi strategi secara immutable (`TrialLedgerEntry`).
   - Mengklasifikasikan outcome yang matured menggunakan taksonomi tertutup `STALE_OR_GAPPED_SOURCE | DELISTING_OR_HALT | MISSING_REQUIRED_HORIZON_DATA | INVALID_INSTRUMENT_METADATA`.
