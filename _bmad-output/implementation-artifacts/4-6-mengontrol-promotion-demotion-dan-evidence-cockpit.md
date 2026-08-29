---
story_id: "4.6"
title: "Mengontrol promotion, demotion, dan evidence cockpit"
epic: "4"
status: "done"
baseline_commit: "80fb176"
---

# Story 4.6: Mengontrol promotion, demotion, dan evidence cockpit

Status: done

## Story

As a Officer,
I want membandingkan sealed policy evidence dan memberi/menurunkan authority secara teraudit,
so that performance tidak dapat mengalahkan safety atau mempromosikan dirinya sendiri.

## Acceptance Criteria

1. **Policy Promotion & Demotion Control**:
   - Mengelola status promosi dan demosi policy (`PROMOTED`, `DEMOTED`, `SHADOW_ONLY`).
   - Setiap perubahan status authority membutuhkan verifikasi *human approval* dan mencatat *audit event* secara immutable.
