---
title: "Spec Story 3.2 — Atomic Portfolio Allocation Kernel"
story: "3.2"
status: done
baseline_commit: "2907e3e"
date: "2026-08-30"
---

# SPEC Kernel

## Intent

Mengganti reservation notional-only yang scale-unsafe dengan frozen portfolio consistency cut, deterministic batch allocation, unique pair-to-Horizon ownership, dan conservation lima dimensi: notional, planned loss, fees, slippage/impact buffer, serta turnover.

## Scope

- Pure-domain `portfolio_allocation.py`, application/port boundary, fenced SQLite persistence, public exports, contracts, dan architecture allowlist.
- Common-scale exact arithmetic lokal; tidak mengedit atau bergantung pada dirty `numeric.py`/`accounting.py`.
- Multiple/partial Fill, UNKNOWN, terminal cancel/reject/expiry/fill, rounding residual, dan duplicate Fill identity.
- All-or-none rejection untuk stale constituent, duplicate ownership/decision, atau equity cap.
- Content-bound accepted batch event/outbox references yang scan-order independent.

## Out of Scope

- Production schema migration, VM, atau perubahan file user/Gemini.

## Invariants

1. Setiap bucket memenuhi exact common-scale `initial = consumed + active_remainder + released` dan seluruh nilai nonnegative.
2. Partial/UNKNOWN tidak pernah melepaskan active remainder; rounding residual tetap reserved sampai terminal outcome terbukti.
3. Duplicate Fill hanya idempotent bila seluruh consumption vector sama.
4. Frozen cut mengikat opportunity set, equity, market cutoff, journal high-water, positions, working orders, RiskState, dan constituent checkpoints.
5. Satu stale checkpoint menolak seluruh risk-increasing batch tanpa executable subset.
6. Satu pair hanya memiliki satu Horizon dalam batch; total initial notional tidak melebihi equity.
7. Accepted batch identity tidak bergantung pada urutan scan proposal.

## Completion Policy

Story selesai ketika event/outbox, reservations, RiskState, dan Decisions dipersist atomically melalui fenced expected-sequence CAS serta crash/retry/stale-fence contracts lulus. Policy ini terpenuhi pada senior review 2026-09-01.

## Execution Record

- RED: import collection gagal karena atomic allocation types belum ada.
- GREEN awal: 7/7 focused PASS; fixture mixed-scale yang semula salah dikoreksi sebelum dijadikan evidence.
- Review fixes: terminal remainder anti-forgery, content-ref regeneration, duplicate observed checkpoint rejection, observed cut binding, dan constructor-level stale/equity enforcement.
- Final: focused 8/8; allocation+identity 31/31; all contracts 404/404; Strategy2/dry-run 61/61; compile/diff gates PASS.
- Disposition 2026-08-30: pure-domain scope selesai tetapi Story masih `review/PARTIAL`; status historis ini diselesaikan oleh senior review berikutnya.
- Senior review 2026-09-01: typed application/port boundary dan atomic SQLite allocation persistence ditambahkan; 67 focused, 475 contracts, dan 63 regression tests PASS. Disposition final: `done`.
