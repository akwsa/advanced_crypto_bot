---
story_id: "2.6"
title: "Memulihkan lifecycle tanpa decision baru"
epic: "2"
status: "done"
baseline_commit: "7e9a133"
---

# Story 2.6: Memulihkan lifecycle tanpa decision baru

Status: done

## Story

As a Officer,
I want restart dan reconciliation mengembalikan state yang sama,
so that crash atau ambiguous acknowledgment tidak mengubah sejarah atau menambah exposure.

## Acceptance Criteria

1. **Deterministic Recovery & Replay**:
   - Startup recovery mengembalikan `Order`, `Position`, `CashLedger`, dan `PolicyState` persis ke high-water mark terakhir tanpa membuat keputusan strategi baru atau mengirim order ganda.
   - Penanganan ambiguous status (`UNKNOWN`) wajib menjalankan *query-before-resubmit*.
