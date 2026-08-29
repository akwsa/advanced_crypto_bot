---
story_id: "2.4"
title: "Menyelesaikan Intent dan Order melalui Fill-authoritative accounting"
epic: "2"
status: "done"
baseline_commit: "225b7c4"
---

# Story 2.4: Menyelesaikan Intent dan Order melalui Fill-authoritative accounting

Status: done

## Story

As a Officer,
I want setiap execution effect dicatat sekali dan hanya Fill mengubah cash/exposure,
so that partial/retry tidak menciptakan ghost Position atau P&L ganda.

## Acceptance Criteria

1. **Fill-Authoritative Accounting**:
   - Hanya Fill yang dapat mengubah cash, fee, tax, quantity, dan Position.
   - Acknowledgment submission tanpa Fill tidak pernah mengubah balance/position.
   - Venue Fill ID dideduplikasi secara eksplisit; duplicate/delayed fill tidak menghasilkan double accounting.
