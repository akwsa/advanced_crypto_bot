---
story_id: "3.5"
title: "Menjalankan kill dan hard-drawdown zeroing"
epic: "3"
status: "done"
baseline_commit: "c15052d"
---

# Story 3.5: Menjalankan kill dan hard-drawdown zeroing

Status: done

## Story

As a Officer,
I want kill/drawdown menghentikan exposure baru dan mengurangi exposure menuju nol,
so that emergency control tetap deterministik melewati retry dan restart.

## Acceptance Criteria

1. **Kill Switch & Hard-Drawdown State Machine**:
   - Mengontrol transisi emergency state: `ARMED -> TRIGGERED -> CANCEL_PENDING -> EXIT_PENDING -> RECONCILING -> LATCHED_SAFE`.
   - Menghentikan semua order masuk baru dan memicu penutupan posisi (*zeroing*) secara deterministik.
