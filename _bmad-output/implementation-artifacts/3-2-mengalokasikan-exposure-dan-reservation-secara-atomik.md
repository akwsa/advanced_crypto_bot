---
story_id: "3.2"
title: "Mengalokasikan exposure dan reservation secara atomik"
epic: "3"
status: "review"
baseline_commit: "379360c"
---

# Story 3.2: Mengalokasikan exposure dan reservation secara atomik

Status: review

## Story

As a Officer,
I want seluruh Candidate pada cutoff yang sama berbagi satu portfolio/risk consistency cut,
so that pair, Horizon, capacity, dan exposure tidak bergantung pada scan order atau stale Fill state.

## Acceptance Criteria

1. **Atomic Allocation & Reservation**:
   - `PortfolioAllocation` mengelola alokasi notional, reservasi risiko, dan alokasi modal secara atomik.
   - Persamaan reservasi `initial = consumed + active_remainder + released` wajib terpenuhi pada setiap pembaruan alokasi.

## Factual Reopen — 2026-08-30

- Baseline audit E15/R04: **PARTIAL**; conservation membandingkan raw units lintas scale dan tidak memodelkan batch consistency cut maupun lima risk dimensions.
- Remediasi pure-domain di file bersih; dirty `numeric.py` dan `accounting.py` tidak disentuh atau dijadikan dependency.
- Target verdict tetap **PARTIAL** sampai atomic persistence wiring ke Story 3.1 tersedia.

## Completion Evidence — 2026-08-30

- Review-ready implementation commit: `e8e3a39e77ca021fae0bf189d2d70fa0176bf298`.
- RED: import/collection gagal karena atomic allocation types belum ada.
- Focused allocation 8/8; allocation+identity/import 31/31 PASS.
- Seluruh AutoTrade Next contracts 404/404; canonical Strategy2/dry-run regression 61/61 PASS.
- `compileall` dan `git diff --check` exit 0.
- Reservation sekarang memiliki exact common-scale conservation untuk notional, planned loss, fees, slippage/impact, dan turnover. Multiple/partial Fill content-bound; UNKNOWN dan partial mempertahankan remainder/residual sampai terminal evidence.
- Frozen cut mengikat opportunity set, equity, market cutoff, journal high-water, positions, working orders, RiskState, dan observed constituent checkpoints.
- Batch deterministic/scan-order independent menolak stale checkpoint, duplicate decision/reservation/pair ownership, dan equity overflow tanpa executable subset. Accepted/rejected refs diregenerasi dari preimage sehingga caller tidak dapat self-attest event/outbox.
- Factual verdict tetap **PARTIAL**: belum ada application handler yang mem-persist final decisions, reservations, RiskState, event, dan outbox melalui satu fenced expected-sequence CAS.

## File List

- `advanced_crypto_bot/autotrade_next/domain/portfolio_allocation.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_portfolio_allocation.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-3-2-atomic-portfolio-allocation.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Atomic allocation semantic kernel review-ready; fenced persistence composition tetap terbuka.
