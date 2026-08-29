---
story_id: "3.7"
title: "Menyajikan integrity cockpit dan audited recovery"
epic: "3"
status: "done"
baseline_commit: "0107069"
---

# Story 3.7: Menyajikan integrity cockpit dan audited recovery

Status: done

## Story

As a Officer,
I want melihat authority, freshness, safety, risk, queue, order, reconciliation, dan approval evidence dalam satu cockpit read-only,
so that saya dapat memutuskan recovery tanpa direct database mutation.

## Acceptance Criteria

1. **Integrity Cockpit Read-Only Projection**:
   - Menampilkan status kesehatan sistem secara menyeluruh (*Writer epoch*, *data quality*, *Safety causes*, *risk reservations*, *order health*).
   - Proyeksi *read-only* murni tanpa mengizinkan mutasi langsung pada database canonical.
