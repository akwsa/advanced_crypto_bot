---
story_id: "3.4"
title: "Menggabungkan safety cause tanpa premature clear"
epic: "3"
status: "done"
baseline_commit: "3d52be2"
---

# Story 3.4: Menggabungkan safety cause tanpa premature clear

Status: done

## Story

As a Officer,
I want setiap incident memiliki cause, scope, severity, evidence, dan clear predicate canonical,
so that satu subsystem tidak membuka entry ketika cause lain masih aktif.

## Acceptance Criteria

1. **Safety Cause Matrix & Lattice**:
   - Menggabungkan berbagai penyebab kegagalan (*Safety Cause*) tanpa menghapus pemicu aktif lainnya secara prematur (*no premature clear*).
   - Menegakkan hirarki scope: `ORDER < INSTRUMENT < PORTFOLIO < AUTHORITY`.
