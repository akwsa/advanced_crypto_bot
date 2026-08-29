---
story_id: "2.3"
title: "Menjalankan satu deterministic simulator lifecycle"
epic: "2"
status: "done"
baseline_commit: "148c43e912051e014094f5b01920f21ac1646a13"
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
