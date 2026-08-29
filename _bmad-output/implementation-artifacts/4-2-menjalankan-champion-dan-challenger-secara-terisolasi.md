---
story_id: "4.2"
title: "Menjalankan Champion dan Challenger secara terisolasi"
epic: "4"
status: "done"
baseline_commit: "dc063fd"
---

# Story 4.2: Menjalankan Champion dan Challenger secara terisolasi

Status: done

## Story

As a Officer,
I want semua policy dinilai pada Candidate, cost, dan opportunity context sama,
so that legacy atau model kompleks tidak mendapat keuntungan authority/data tersembunyi.

## Acceptance Criteria

1. **Isolated Champion & Challenger Execution**:
   - Menjalankan alur evaluasi Champion dan Challenger dalam konteks yang sepenuhnya terisolasi tanpa shared mutable state.
   - Penolakan tegas (*fail-closed*) apabila Challenger mencoba mengirimkan order langsung (*live submit*) ke venue.
