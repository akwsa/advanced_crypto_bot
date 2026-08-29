---
story_id: "2.5"
title: "Mempertahankan Position protection melalui unified EXIT"
epic: "2"
status: "done"
baseline_commit: "09550ec"
---

# Story 2.5: Mempertahankan Position protection melalui unified EXIT

Status: done

## Story

As a Officer,
I want SL, invalidation, profit, trailing, time, alpha, dan operator exit memakai satu canonical path,
so that remaining quantity selalu protected dan tidak ditutup dua kali.

## Acceptance Criteria

1. **Unified Exit Processing**:
   - Menyatukan seluruh pemicu EXIT (Stop-Loss, Take-Profit, Invalidation, Trailing, Time Expiry, Alpha Exit, Operator Exit) dalam satu alur terpusat `ExitEvaluator`.
   - Mencegah penutupan ganda (*double exit*) dengan memverifikasi sisa kuantitas posisi aktif.
