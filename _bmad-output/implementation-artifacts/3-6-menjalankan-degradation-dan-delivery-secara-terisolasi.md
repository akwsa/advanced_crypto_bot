---
story_id: "3.6"
title: "Menjalankan degradation dan delivery secara terisolasi"
epic: "3"
status: "done"
baseline_commit: "0aff894"
---

# Story 3.6: Menjalankan degradation dan delivery secara terisolasi

Status: done

## Story

As a Officer,
I want runtime menurunkan authority sebelum availability failure menjadi trading failure,
so that reconciliation dan protective action tetap hidup ketika scanning, Redis, atau notification terganggu.

## Acceptance Criteria

1. **Degradation State Machine**:
   - Menjalankan penurunan taraf runtime secara teratur: `HEALTHY -> ENTRY_FROZEN -> SHADOW_ONLY -> SAFE_LATCHED`.
   - Mengisolasi kegagalan sistem non-kritis (seperti Redis/Telegram/Notifikasi) agar tidak menghambat pertahanan posisi.
