---
story_id: "3.4"
title: "Menggabungkan safety cause tanpa premature clear"
epic: "3"
status: "in-progress"
baseline_commit: "3d52be2"
---

# Story 3.4: Menggabungkan safety cause tanpa premature clear

Status: in-progress

## Story

As a Officer,
I want setiap incident memiliki cause, scope, severity, evidence, dan clear predicate canonical,
so that satu subsystem tidak membuka entry ketika cause lain masih aktif.

## Acceptance Criteria

1. **Safety Cause Matrix & Lattice**:
   - Menggabungkan berbagai penyebab kegagalan (*Safety Cause*) tanpa menghapus pemicu aktif lainnya secara prematur (*no premature clear*).
   - Menegakkan hirarki scope: `ORDER < INSTRUMENT < PORTFOLIO < AUTHORITY`.

## Factual Reopen — 2026-08-30

- Baseline audit E17: **FAIL**; `clear_cause(cause_id)` menghapus cause tanpa evidence, predicate, sequence, atau authority.
- Remediasi pure-domain di file bersih; protected dirty files dan VM tidak termasuk scope.
- Target verdict maksimal **PARTIAL** sampai durable/authenticated runtime integration tersedia.
