# Change Log — AutoTrade Replacement PRD

## 2026-08-25

### Product decisions

- Replaced the legacy-patch direction with a full AutoTrade replacement.
- Confirmed dynamic eligibility across spot-IDR pairs and intraday-to-multi-day swing horizons.
- Allowed the legacy strategy to compete for Champion only after canonical conformance and equal evidence gates.
- Locked risk envelope: 10% maximum Position notional, 40% total exposure, 2% daily loss, 0.5% risk-at-stop, and 10% hard drawdown trigger.
- Kept real trading outside MVP and behind a separate live-readiness PRD.

### Requirements hardening

- Added one Canonical Decision and action-state legality.
- Added fill-based accounting, persisted Policy State, bounded Order recovery, and atomic exits.
- Added executable market snapshots, freshness/gap rules, simulator fidelity, and evidence classes.
- Added kill/degradation states, single-writer fencing, outbox/ack/dead-letter semantics, and notification isolation.
- Added frozen Experiment/Evidence Specification, anti-method-shopping controls, `UNSCORABLE` governance, and staged promotion.
- Added brownfield inventory, evidence hierarchy, ghost-position correction, cutover/rollback criteria, and incident regression fixtures.
- Added minimum invariants, operational SLOs, decision flip-rate diagnostics, and platform/strategy/live stage gates.

### Review and reconciliation

- Rubric gate improved from one critical/six high findings to zero critical/high findings.
- Adversarial gate improved from eight critical/fourteen high findings to zero critical; all final high contracts were resolved.
- Applied 14 approved structural recommendations and 29 minimal prose corrections.
- Reconciled the final PRD against the incident case, handoff, architecture spine, roadmap, and three technical research inputs.

### Verification

- Focused AutoTrade regression suite: **132 passed**, 1 warning, and 22 subtests passed in 6.63 seconds.
- Full repository suite: **696 passed**, 14 failed, 5 errors, 25 warnings, and 22 subtests passed in 38.00 seconds.
- The full-suite failures are retained as an explicit brownfield baseline rather than hidden by the PRD finalization. They cluster around removed legacy helpers, foreign-key test fixtures, stale runtime mocks, performance backfill, VaR gates, one signal-label expectation, and Telegram HTML sanitization.
- Document integrity checks and the BMad PRD completion hook are run after this log update.
