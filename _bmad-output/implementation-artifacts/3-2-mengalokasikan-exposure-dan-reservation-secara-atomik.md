---
story_id: "3.2"
title: "Mengalokasikan exposure dan reservation secara atomik"
epic: "3"
status: "done"
baseline_commit: "379360c"
---

# Story 3.2: Mengalokasikan exposure dan reservation secara atomik

Status: done

## Story

As a Officer,
I want seluruh Candidate pada cutoff yang sama berbagi satu portfolio/risk consistency cut,
so that pair, Horizon, capacity, dan exposure tidak bergantung pada scan order atau stale Fill state.

## Acceptance Criteria

1. **Atomic Allocation & Reservation**:
   - `PortfolioAllocation` mengelola alokasi notional, reservasi risiko, dan alokasi modal secara atomik.
   - Persamaan reservasi `initial = consumed + active_remainder + released` wajib terpenuhi pada setiap pembaruan alokasi.
