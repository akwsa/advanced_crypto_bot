# Final Adversarial Review — AutoTrade Replacement PRD

Reviewed: current `prd.md` and `addendum.md`, 2026-08-25.

## Verdict

**Ready for architecture spine and epic decomposition, with four high-severity requirement contracts to close before their implementation stories or promotion acceptance tests are finalized.** No critical blocker remains. The latest revision materially closes writer fencing, decision identity, exit precedence, drawdown failure handling, horizon contention, `UNSCORABLE`, DRY RUN evidence labeling, and storage-retention blockers.

## Findings

1. FR-5 now defines precedence but still does not define the actual hysteresis transition contract: entry/maintain/exit boundary relationship, minimum dwell/debounce, gap-through behavior, and persisted boundary version are absent. The architecture can supply the policy interface, but implementation stories cannot prove that small input noise will not churn In Trade/Out Trade state without normative transition examples.

2. FR-26 freezes statistical methods per Experiment, yet §9 keeps all numeric promotion gates as assumptions and permits a newly approved Evidence Specification before each Experiment. A sequence of experiments can still shop across bootstrap rules, trial families, effective-sample rules, and confidence constructions while each run is individually preregistered. Gate-specification changes need their own immutable lineage, comparison family, and approval rule that prevents resetting failed evidence.

3. The promotion section retains two obsolete or contradictory metrics. “Realized execution cost” is not available for DRY RUN counterfactual fills, and “pair ≤35% total profit” conflicts with FR-26’s absolute-positive-contribution and exposure/risk concentration treatment when aggregate profit is non-positive. These lines need stage-specific replacement rather than parallel interpretations.

4. FR-32 migration is still not an acceptance contract. It lacks a source inventory, evidence hierarchy, ghost-position disposition, balance tolerance, quarantine ownership, cutover criteria, rollback window, and treatment of external balances without validated Fill history. Because migration is a Platform-ready gate, architecture/epics otherwise have no objective completion oracle.

5. FR-20’s fencing contract is now directionally sufficient, but lease authority availability, persistence, and disaster-recovery assumptions are unstated. Architecture must document whether losing the authority fail-closes all writes, how epochs survive restore, and how reconciliation establishes a safe post-recovery epoch.

6. FR-12 still creates a sizing/depth dependency loop: requested size determines required book depth while available depth, liquidity, stop distance, and uncertainty can reduce requested size. The architecture needs a deterministic bounded sizing algorithm, maximum depth policy, and no-convergence outcome.

7. FR-13 delegates stale-exit behavior to a “conservative execution policy” without a minimum fallback hierarchy or acceptance corpus. Halt, one-sided book, extreme spread, disconnected private channel, and repeated non-fill scenarios need explicit safety outcomes.

8. `UNKNOWN` has a 60-second deadline but no required state after the deadline. The PRD freezes entry and requires reconciliation, yet does not specify indefinite quarantine, escalation, venue/account lock scope, or whether protective orders on known exposure may proceed concurrently.

9. Incident promotion semantics remain ambiguous. “Zero Integrity Incident” suggests any detected incident fails the window, while SM-8 says corrected incidents remain counted; severity taxonomy, clean-window restart, and treatment of data-freshness versus conservation failures are undefined.

10. Absolute success metrics still lack metric contracts. “Zero unexplained mismatch,” “100% terminal,” “generic reason <0.5%,” and “zero terminal gap” need denominators, observation windows, allowed event lateness, exclusion rules, and measurement checkpoints.

11. Security remains outcome-oriented rather than test-oriented. Authentication strength, actor identity, key rotation, break-glass access, audit export/verification, secret-redaction tests, and role boundaries are not specified; these can be resolved in architecture but must become explicit acceptance criteria before implementation.

12. The Candidate ID includes `data revision`, while late correction creates a new revision linked to the original, but the PRD does not state whether corrected Candidates enter evaluation, remain audit-only, or can generate a new executable decision. Without that rule, replay correctness and live immutability can conflict.

13. Horizon IDs and retention periods are explicitly assumptions, yet §12 says no phase-blocking question remains. This is acceptable for architecture discovery only if architecture validation has a forced decision gate before schema capacity, partitioning, and scheduling commitments are finalized.

14. The dynamic universe lists eligibility factors but no numeric floors/ceilings or missing-correlation fallback. Experiments can freeze their chosen formula, but comparison across Experiments remains vulnerable to opportunity-set selection unless eligibility-policy changes enter the trial family and governance evidence.

15. The addendum remains method-rich but decision-light. A method-neutral interface is implied, not required; architecture should prevent any cited calibration/change-detection method from becoming coupled to canonical ledger, risk, or event schemas.

## Required Closure Before Relevant Implementation Stories

- Add a normative hysteresis transition table and persisted boundary/version rules.
- Govern Evidence Specification changes across experiments and replace the two obsolete Promotion Gate lines.
- Turn legacy migration into an inventory/disposition/cutover acceptance matrix.
- Define metric/incident contracts with denominators, windows, lateness, severity, and clean-window behavior.

## Severity Accounting

**0 critical, 4 high, 8 medium, 3 low.** High findings are hysteresis transition testability, cross-Experiment statistical method shopping, contradictory/unobservable promotion metrics, and migration acceptance incompleteness.
