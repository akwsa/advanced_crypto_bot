---
story_id: "5.6"
title: "Melakukan additive rollback dan evidence retention"
epic: "5"
status: "done"
baseline_commit: "fba49bb"
---

# Story 5.6: Melakukan additive rollback dan evidence retention

Status: done

## Story

As a Officer,
I want rollback memulihkan safe replacement release tanpa menghidupkan writer lama atau menimpa fakta baru,
so that recovery tidak mengorbankan history dan evidence.

## Acceptance Criteria

1. **Additive Rollback & Retention Governance**:
   - Menjalankan rollback secara aditif (*additive rollback*) tanpa menimpa atau mengedit sejarah fakta kanonikal yang sudah tercatat.
   - Mengelola retensi bukti (*evidence retention*) melalui pembuatan manifest penghapusan teraudit (*tombstone manifest*) saat data kadaluarsa.
