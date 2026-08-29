---
story_id: "5.5"
title: "Melakukan stop-the-world fenced cutover"
epic: "5"
status: "done"
baseline_commit: "6ae4667"
---

# Story 5.5: Melakukan stop-the-world fenced cutover

Status: done

## Story

As a Officer,
I want memindahkan virtual portfolio authority ke replacement tepat satu kali,
so that legacy dan target tidak pernah submit atau settle scope yang sama bersamaan.

## Acceptance Criteria

1. **Stop-The-World Fenced Cutover Execution**:
   - Menjalankan urutan pengalihan kekuasaan (*cutover sequence*): `FREEZE -> STOP_LEGACY -> DRAIN -> CHECKPOINT -> CLAIM_EPOCH -> ENABLE_TARGET`.
   - Mengklaim epoch lebih tinggi (*higher epoch claim*) secara atomik untuk mencegah dual submission oleh legacy handler.
