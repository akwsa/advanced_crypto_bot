---
story_id: "4.1"
title: "Membekukan Experiment dan opportunity universe"
epic: "4"
status: "done"
baseline_commit: "33023fe"
---

# Story 4.1: Membekukan Experiment dan opportunity universe

Status: done

## Story

As a Officer,
I want setiap Experiment mengunci seluruh input dan eligibility sebelum window dibuka,
so that universe, Horizon, cost, atau method tidak dapat diganti setelah outcome terlihat.

## Acceptance Criteria

1. **Experiment Spec Freezing**:
   - Membekukan spesifikasi experiment (`EvidenceSpecification`) yang mengunci universe, horizon, cost model, dan seed.
   - Perubahan apapun pada spesifikasi setelah pembekuan akan menghasilkan versi family experiment baru secara immutable.
