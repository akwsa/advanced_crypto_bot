---
story_id: "5.3"
title: "Menjalankan offline migration serta backup/restore gate"
epic: "5"
status: "done"
baseline_commit: "c1a57b9"
---

# Story 5.3: Menjalankan offline migration serta backup/restore gate

Status: done

## Story

As a Officer,
I want schema dan source database dipindahkan hanya melalui proses offline yang dapat dipulihkan,
so that migration/cutover tidak bergantung pada copy database aktif atau runtime DDL.

## Acceptance Criteria

1. **Offline Migration & Backup/Restore Gate**:
   - Menjalankan migrasi skema database secara terisolasi tanpa runtime DDL aktif.
   - Verifikasi pemulihan data (*restore gate*) wajib lulus inspeksi integritas dan `foreign_key` sebelum cutover disetujui.
