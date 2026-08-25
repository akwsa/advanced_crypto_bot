# Good-Spine Rubric Review — AutoTrade Replacement

**Reviewer lens:** rubric walker  
**Artifact:** `ARCHITECTURE-SPINE.md`  
**Load-bearing input checked:** `../../prds/prd-advanced_crypto_bot-2026-08-25/prd.md`  
**Verdict:** **CHANGES REQUIRED** — the spine is unusually strong on canonical truth, replay, fencing, settlement, SQLite operations, and DRY RUN isolation, but it does not yet fix every load-bearing divergence inherited from the PRD. Three omissions can produce materially incompatible implementations of safety and lifecycle behavior.

## Rubric assessment

| Good-spine criterion | Result | Assessment |
| --- | --- | --- |
| Fixes the real divergence points one level down and misses none | **Fail** | Kill lifecycle, hard-drawdown liquidation behavior, retention, and several versioned product baselines remain under-specified or silent. |
| Every AD Rule is enforceable and prevents its stated divergence | **Partial** | Most Rules are testable. AD-01's dependency direction is not stated precisely enough for an import-rule check, while AD-11 does not encode the full hard-drawdown outcome it binds. |
| Nothing under Deferred permits incompatible units | **Partial** | Technology choices are appropriately deferred, but “Baseline refinement” references binding initial values that the spine does not actually state for confirmation counts and other PRD baselines. |
| Named technology is verified-current | **Pass with evidence caveat** | Versions are exactly pinned; SQLite includes source ID and runtime qualification. The companion notes point to the technical research for primary-source current-version checks. No contradictory version evidence was found. |
| Ratifies rather than contradicts brownfield reality | **Pass** | The target intentionally replaces known legacy conventions, quarantines reuse behind adapters, isolates namespace/database authority, and defines a fenced cutover rather than pretending the existing structure already conforms. |
| Covers capabilities from the driving spec | **Fail** | The capability map claims FR-1–FR-34 coverage, but important normative contracts from FR-5, FR-18–FR-19, FR-22, FR-24, FR-32, and Data Governance do not land in an AD, convention, baseline, Deferred item, or open question. |
| Parent spine inheritance is preserved | **N/A** | No inherited parent spine is declared. |
| Every owned dimension is decided, deferred, or open | **Partial** | Deployment, environment, infrastructure, backup/restore, schema migration, observability, and operational SLOs are covered. Data-retention/lifecycle policy is silent despite being normative in the PRD. |

## Findings

### HIGH — R-01: Hard-drawdown breach does not bind the required liquidation outcome

**Evidence:** PRD FR-18 requires a 10% hard-drawdown breach to cancel all unfilled entry orders, latch entry, and initiate the highest-precedence risk-reduction `EXIT` toward zero exposure. The spine records the 10% trigger in AD-11 and gives hard drawdown high precedence in AD-04, but AD-11 only says drawdown latches fail closed for entry. It never requires cancellation of working entry orders or a target of zero exposure. That stronger behavior appears only in `IMPLEMENTATION-NOTES.md`, which is not the consistency contract.

**Divergence:** one risk implementation can merely freeze new entries and retain current positions while another liquidates toward zero; both can claim compliance with the spine.

**Disposition:** **Autofix.** Amend AD-11 or AD-04 to state the complete breach command/result: cancel risk-increasing working orders, preserve reconciliation of `UNKNOWN`, generate highest-precedence risk-reduction decisions with explicit target zero, and keep the latch until approved recovery evidence.

### HIGH — R-02: Operator kill lifecycle is not fixed

**Evidence:** PRD FR-19 specifies `ARMED → TRIGGERED → CANCEL_PENDING → EXIT_PENDING → RECONCILING → LATCHED_SAFE`, including cancel deadlines/retries, query-before-resubmit for `UNKNOWN`, protective exit, reconciliation, and operator-only reset. AD-04 only establishes precedence; AD-11 says the RiskGovernor owns a persisted kill latch; AD-17 covers authenticated commands; AD-21 defines a different general degradation state machine. No Rule defines the kill transitions or their required effects.

**Divergence:** OrderCoordinator, RiskGovernor, and operator-command implementations can disagree about whether trigger cancels, exits, reconciles, when safety is terminal, and which evidence permits reset—precisely a cross-module safety seam.

**Disposition:** **Autofix.** Add the normative kill state machine and transition effects to AD-11 (or a dedicated AD), explicitly relating it to AD-12 order recovery and AD-21 degradation states.

### HIGH — R-03: Required retention and evidence-lifecycle policy is silent

**Evidence:** the PRD Data Governance contract provides baseline retention of raw L2 for 30 days, Candidate snapshots/replay manifests for 2 years, and canonical/evidence/audit records for 7 years, with the invariant that expiry cannot remove evidence referenced by an active Experiment or promotion. The spine has no retention Rule, Operational Baseline row, Deferred item, or open question. The memlog acknowledges retention sizing as an assumption, but that did not survive distillation.

**Divergence:** storage, backup, cleanup, experiment, and audit units can implement incompatible deletion windows or delete still-referenced evidence. This also undermines AD-14 replay and AD-15 sealed evidence.

**Disposition:** **Autofix.** Add a data-lifecycle invariant with the PRD baselines marked `[ASSUMPTION]`, reference-aware/legal-hold behavior, deletion evidence, and a revisit condition based on observed capacity and approval. Capacity sizing can remain deferred; semantic retention cannot be silent.

### MEDIUM — R-04: “Baseline refinement” defers values that are absent from the initial baseline

**Evidence:** Deferred says freshness, UNKNOWN timeout, confirmation count, turnover, session boundary, and operational SLO baselines are binding until changed. The Operational Baseline contains freshness and UNKNOWN timeout; AD-11 contains turnover and session. But the PRD's FR-5 initial confirmation behavior—two consecutive closed bars for `ENTER`, one for protective `EXIT`, and two for alpha-only `EXIT`, plus gap-reset behavior—does not appear anywhere in the spine.

**Divergence:** strategy and Policy State implementations can choose different confirmation semantics while each treating its choice as the binding initial baseline.

**Disposition:** **Autofix or explicitly defer.** Either record the concrete `[ASSUMPTION]` baseline and gap behavior in AD-04/Operational Baseline, or say confirmation policy is experiment-versioned and non-executable until an approved baseline exists. Do not claim an unstated initial value binds.

### MEDIUM — R-05: Experiment horizon and unscorable governance contracts are not carried into the spine

**Evidence:** PRD FR-22 sets assumed MVP Horizon IDs `15M`, `1H`, `4H`, `1D`, label maturities 1h/4h/24h/72h, and effective-dated daily universe membership. AD-08/AD-24 mention `horizon_id` and effective-time eligibility but not the allowed MVP set, maturity mapping, or evaluation cadence. PRD FR-24 also fixes a closed `UNSCORABLE` taxonomy and a 5% promotion ceiling; AD-15 delegates evaluation rules to an Evidence Specification without requiring those product constraints.

**Divergence:** Candidate scheduling, label maturation, report eligibility, and outcome pipelines can use incompatible horizon mappings or post-hoc `UNSCORABLE` reasons.

**Disposition:** **Autofix.** Add the assumed horizon/maturity mapping to an explicit baseline and require the closed unscorable taxonomy/threshold in AD-15. Values can remain versioned assumptions, but all units need one initial contract.

### LOW — R-06: AD-01 dependency rule is semantically right but not fully machine-enforceable

**Evidence:** “domain dan application hanya bergantung ke dalam” is ambiguous because application is itself an outer layer relative to domain and must depend on ports/domain, while the diagram separately permits strategies/adapters to depend on domain and ports. There is no stated import matrix or enforcement mechanism.

**Divergence:** implementers can disagree over whether application may import ports, whether strategies may import application services, and whether projections are adapters or independent consumers.

**Disposition:** **Autofix.** Replace the phrase with an explicit allowed dependency matrix and require an architecture/import test. The structural tree may remain seed.

## Strengths worth preserving

- AD-03, AD-05–AD-08, and AD-12–AD-16 form a coherent truth/replay/execution contract with explicit authority, sequencing, idempotency, and failure behavior.
- AD-07's persistent fencing rule is concrete enough to reject stale writers inside the same transaction, not merely detect them operationally.
- AD-18–AD-23 cover the commonly omitted operational/environmental envelope: isolated shadow authority, artifact/runtime reproducibility, physical exclusion of live trading, SLO semantics, coordinated backup/restore, and offline migration.
- Deferred items mostly defer real choices at the correct altitude without weakening canonical truth or safety.
- The capability map and diagrams make the spine navigable; the issue is overclaiming complete coverage rather than a lack of overall structure.

## Gate conclusion

The spine should not be finalized until R-01 through R-03 are incorporated because they affect loss containment, emergency handling, and preservation of replay/evidence authority. R-04 and R-05 should also be resolved before stories split across strategy, outcome, and experiment units. R-06 can be repaired mechanically with an import matrix/test requirement. No change to the named paradigm or main technology choices is indicated.

## Delta Verification — Updated Spine

**Delta verdict:** **FAIL — 3 of 6 prior findings are fully closed; 3 remain partially open.**

| Prior finding | Status | Verification |
| --- | --- | --- |
| R-01 Hard-drawdown liquidation | **Closed** | AD-11 now requires cancellation of unfilled risk-increasing entry, an entry latch, and highest-precedence protective `EXIT` toward zero exposure. |
| R-02 Operator kill lifecycle | **Partially open — blocking** | AD-27 now binds immediate entry cancellation, target-zero exposure, restart persistence, and authenticated reset with reconciliation evidence. It still omits the PRD's normative `ARMED → TRIGGERED → CANCEL_PENDING → EXIT_PENDING → RECONCILING → LATCHED_SAFE` transitions and the required cancel deadline/retry plus UNKNOWN query-before-resubmit behavior. Implementations can still disagree at the RiskGovernor/OrderCoordinator seam. Add the state machine and transition effects, or explicitly map every PRD kill state onto the canonical SafetyState/degradation model. |
| R-03 Retention/evidence lifecycle | **Closed** | AD-28 and Operational Baseline now bind all three retention windows, active-reference holds, controlled cleanup, and deletion evidence. |
| R-04 Confirmation baseline | **Partially open — blocking** | AD-04 now carries the numeric confirmation baseline, but says any data gap resets “confirmation” without preserving the PRD distinction: a gap resets `ENTER` confirmation but must not reset Position protection/high-water state. As written, an implementation could reset protective state or delay a protective exit. Narrow the reset rule and explicitly preserve Position protection/high-water state. |
| R-05 Horizon and UNSCORABLE governance | **Partially open — blocking** | AD-28 closes the Horizon/maturity mapping. AD-15 requires a closed versioned `UNSCORABLE` taxonomy and 5% ceiling, but does not bind the PRD's allowed taxonomy (`stale/gapped source`, `delisting/halt`, `missing required horizon data`, `invalid instrument metadata`) or the rule that reason assignment cannot use realized outcome. Different units can still invent incompatible reasons or post-hoc classification. |
| R-06 Enforceable dependency rule | **Closed** | AD-01 now supplies an explicit allowed import matrix and mandatory CI forbidden-import contract test. |

### Remaining blocking actions

1. Encode or explicitly map the complete FR-19 kill state machine and its cancel/UNKNOWN transition behavior.
2. Amend AD-04 so gaps reset only entry confirmation and never reset Position protection/high-water state.
3. Enumerate the PRD's closed `UNSCORABLE` reasons in AD-15 and prohibit outcome-aware/post-hoc reason assignment.

## Final Delta Verification

**Final verdict: PASS.** All remaining blockers are closed in the latest spine.

- **R-02 closed:** AD-27 now binds the complete FR-19 state sequence `ARMED → TRIGGERED → CANCEL_PENDING → EXIT_PENDING → RECONCILING → LATCHED_SAFE`, immediate entry rejection, cancel deadline/retry, UNKNOWN query-before-resubmit, target-zero protective exit, mandatory reconciliation, and evidence-backed operator-only reset.
- **R-04 closed:** AD-04 now limits gap/quality reset to `ENTER` confirmation and explicitly preserves Position protection/high-water state and protective-exit timeliness.
- **R-05 closed:** AD-15 now enumerates the exact four allowed `UNSCORABLE` reasons, requires point-in-time reason evidence without realized-outcome access, prohibits post-hoc relabeling, and retains the 5% matured-Candidate promotion ceiling.

No blocking finding remains from R-01 through R-06.
