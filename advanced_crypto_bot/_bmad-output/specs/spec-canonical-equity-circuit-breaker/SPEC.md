---
id: SPEC-canonical-equity-circuit-breaker
companions:
  - ../../../docs/architecture/autotrade-profitability-2026-08-24/ARCHITECTURE-SPINE.md
  - ../../../docs/architecture/autotrade-profitability-2026-08-24/IMPLEMENTATION-ROADMAP.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete,
> preservation-validated contract for what to build, test, and validate.

# Canonical Equity and Circuit Breaker Repair

## Why

Dry-run risk decisions are currently untrustworthy: virtual cash is debited through
the normalized ledger while equity reads legacy positions that can already be marked
closed. The resulting false drawdown blocks new entries and prevents meaningful
profitability experiments.

## Capabilities

- **CAP-1**
  - **intent:** The system values dry-run equity from canonical virtual cash plus normalized open positions.
  - **success:** Given journal-consistent cash and positions, valuation deterministically equals cash plus executable mark-to-market position value without reading legacy trades.
- **CAP-2**
  - **intent:** The circuit breaker blocks new exposure after valid excessive drawdown while preserving risk-reducing operations.
  - **success:** Tests demonstrate that BUY is rejected above the drawdown limit while SELL, position monitoring, and reconciliation remain available.
- **CAP-3**
  - **intent:** The system fails new entries closed when canonical position marks are missing or stale.
  - **success:** Missing or stale marks return an unavailable valuation, reject BUY, and never initialize or update equity peak.
- **CAP-4**
  - **intent:** An operator can identify projection drift before any state reconciliation.
  - **success:** A read-only audit reports legacy/normalized open-state mismatches and the cash, position cost, valid equity, and stored peak used by risk evaluation.

## Constraints

- `users.balance`, normalized fills, and normalized positions are authoritative; legacy trades cannot drive equity or drawdown.
- Existing open positions must remain monitorable and sellable while new exposure is blocked.
- The implementation remains dry-run and cannot activate private exchange orders.
- No manual drawdown reset or historical VM ledger mutation belongs to this slice.
- VM reconciliation requires a separate checksummed backup, preflight, and migration report.

## Non-goals

- Tune entry thresholds or exit parameters.
- Redesign Strategy 1 or complete Strategy 2.
- Reconcile current VM rows or enable live trading.

## Success signal

Regression tests reproduce the current three-position drift without false drawdown,
prove that risk uses normalized equity, and prove exits remain available when entry is
blocked. The read-only VM audit can then report a valid reconciliation plan without
changing state.

