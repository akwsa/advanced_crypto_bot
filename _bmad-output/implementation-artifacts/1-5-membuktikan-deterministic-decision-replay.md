---
baseline_commit: 13b54a97dd0781613b73e6797bfaa7a289b42927
---

# Story 1.5: Membuktikan deterministic decision replay

Status: done

## Story

As a Officer,
I want Candidate dan manifest yang sama menghasilkan transition dan decision yang sama dari clean store,
so that historical behavior dapat diverifikasi tanpa external side effect.

## Acceptance Criteria

1. Immutable `ReplayManifest:v1` membekukan ordered input IDs, MarketSnapshot/universe, initial portfolio/risk state, cursors, fee/instrument rules, strategy/model/calibrator/simulator/cost/config/schema, code/image/dependency/runtime numeric refs, RNG algorithm/state, recorded clock refs, dan recorded external-response refs. Required ref hilang, mutable/duplicate/unordered input, atau manifest version asing ditolak typed tanpa partial result.
2. Immutable `DecisionReplayBundle:v1` memuat manifest, exact Candidate Snapshot, initial Policy State, PositionContext, proposal, boundary, gross/shortfall/calibration inputs, gap/protection flags, dan EXIT target. Candidate ordered inputs/scope dan policy/boundary versions wajib konsisten; mismatch ditolak sebelum regeneration.
3. Mode bernama AD-14 tepat `CANONICAL_STATE_REHYDRATION`, `DECISION_LIFECYCLE_REGENERATION`, dan `PROJECTION_REBUILD`. Story 1.5 mengeksekusi decision/policy-state regeneration murni; dua mode yang memerlukan store/projection belum tersedia ditolak `UNSUPPORTED_REPLAY_MODE`, bukan disimulasikan dengan pseudo-store.
4. Regeneration memakai recorded bundle saja dan memanggil pure Story 1.4 transition. Seluruh Decision ID, canonical bytes, next Policy State, ordering, dan semantic hash diturunkan deterministic; 100 replay identik menghasilkan exact bytes/hash sama dan input tidak termutasi.
5. `ReplayResult:v1` memuat transition, manifest ref, mode, external-call counter tepat nol, dan recorded observability envelope. Fungsi replay tidak menerima port/network/clock/random/database callback sehingga external side effect tidak dapat dilakukan secara struktural.
6. `SemanticProjectionProfile:v1` memiliki version dan closed allowlist observability-only paths yang boleh dikecualikan. Candidate/Decision/Policy State/action/reason/evidence/version/correlation/causation tidak pernah boleh dikecualikan.
7. Comparison memakai canonical semantic projection/hash. Perbedaan semantic menghasilkan typed failed comparison dengan ordered exact path/expected/actual diff; tidak ada tolerance, silent ignore, `repr`, float, atau broad field dropping. Perbedaan hanya pada explicit allowed observability paths tetap match.
8. Story tetap pure domain: tanpa I/O, store mutation, wall clock, random, UUID, network, exchange, Redis, dashboard, Telegram, legacy import, lifecycle/order/fill invention, atau projection persistence. Full lifecycle regeneration berkembang setelah Epic 2 contracts tersedia; projection rebuild berkembang bersama Story 1.6+.

## Tasks / Subtasks

- [x] Definisikan immutable replay manifest/bundle contracts di `autotrade_next/domain/replay.py` (AC: 1–3, 8)
  - [x] Complete versioned manifest refs dan input freezing/uniqueness validation.
  - [x] Bundle consistency terhadap Candidate/Policy/Boundary/Position dan typed `ReplayError`.
  - [x] Closed replay mode taxonomy tanpa pseudo-store.
- [x] Implementasikan pure decision regeneration dan result contracts (AC: 3–5, 8)
  - [x] Reuse `evaluate_policy_transition`; jangan duplikasi decision/policy logic.
  - [x] Content-addressed manifest ref, exact transition bytes, dan external-call counter invariant zero.
  - [x] Preserve input immutability dan reject unsupported modes typed.
- [x] Implementasikan versioned semantic projection/comparison (AC: 6–8)
  - [x] Closed exclusion allowlist; semantic paths tidak dapat dikecualikan.
  - [x] Canonical semantic hash dan deterministic recursive exact diff.
  - [x] Match observability-only variance; fail exact pada semantic variance.
- [x] Tambahkan exports, dependency guard, dan comprehensive contract tests (AC: 1–8)
  - [x] Manifest/bundle completeness, mutable input freezing, version/scope mismatch, foreign types.
  - [x] 100-run byte/hash stability, external zero, unsupported modes, prior inputs unchanged.
  - [x] Exact diff paths, exclusion allowlist, correlation/reason/state variance, no silent tolerance.
- [x] Jalankan focused, all AutoTrade Next contracts, Strategy 2, compile/diff hygiene, dan full regression gates (AC: 1–8)

### Review Findings

- [x] [Review][Patch] Bind every overlapping manifest reference to Candidate provenance and complete clock/cursor contents [advanced_crypto_bot/autotrade_next/domain/replay.py:214]
- [x] [Review][Patch] Bind initial portfolio/risk manifest refs to the embedded PositionContext and PolicyState [advanced_crypto_bot/autotrade_next/domain/replay.py:214]
- [x] [Review][Patch] Reject evidence-version, protective-trigger, and exit-target mismatches during bundle construction [advanced_crypto_bot/autotrade_next/domain/replay.py:205]
- [x] [Review][Patch] Preserve a single typed ReplayError boundary when regeneration rejects recorded inputs [advanced_crypto_bot/autotrade_next/domain/replay.py:361]
- [x] [Review][Patch] Harden ReplayComparison and SemanticDiff invariants, including unambiguous missing-key evidence [advanced_crypto_bot/autotrade_next/domain/replay.py:321]
- [x] [Review][Patch] Add pinned cross-process replay golden vectors and complete negative mismatch coverage [advanced_crypto_bot/tests/autotrade_next/contract/test_deterministic_replay.py:143]
- [x] [Review][Patch] Replace the global relative-import allowlist with an explicit acyclic per-module dependency contract [advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py:281]

## Dev Notes

### Developer Context

- Reuse canonical bytes, CandidateSnapshot, PolicyState/PolicyTransition, and `evaluate_policy_transition`; no second evaluator.
- “Clean store” pada story ini berarti regeneration pure dari initial state dalam bundle. Durable SQLite clean-store harness belum boleh dipalsukan sebelum application/store contracts tersedia.
- AD-14 mendefinisikan tiga mode; hanya decision lifecycle subset yang dapat dieksekusi dari current Epic 1 domain. Unsupported mode harus eksplisit dan typed.
- Observability envelope hanya menerima recorded refs, bukan `datetime.now()` atau UUID.
- Exact diff bekerja pada canonical projections dan mengurutkan mapping key/path; list order semantic.

### Architecture Compliance

- AD-01 pure import matrix; AD-03 fixed Decision identity; AD-10 deterministic policy; AD-14 replay bundle; AD-26 canonical encoding.
- External-call count zero by construction: replay API tidak menerima port/callback.
- No lifecycle Order/Fill, SQLite, projection consumer, or external adapter scope.

### File Structure Requirements

- NEW `advanced_crypto_bot/autotrade_next/domain/replay.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/errors.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_deterministic_replay.py`
- UPDATE `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` narrow allowlist only.
- Preserve all uncommitted Stories 1.2–1.4 and user handoff.

### Testing Requirements

- Exact manifest completeness and content ref; duplicate refs/input IDs fail typed.
- Bundle rejects ordered input/scope/policy/boundary/protective mismatch before evaluation.
- Same bundle replay 100 times: identical Decision/transition bytes, semantic projection/hash, external count zero.
- Different recorded run/trace refs match only under explicit profile exclusions; unknown/semantic exclusion rejected.
- Semantic changes report stable exact paths and canonical expected/actual values; multiple diffs sorted.

### Previous Story Intelligence

- Story 1.4 is done after 12 adversarial fixes; Policy inputs are now version/size/scope bound and completed duplicates replay identical Decision bytes.
- Latest gates: 63 focused, 176 contract/Strategy 2, and 830 full-suite passes with unchanged 14/5 legacy baseline.
- Do not weaken content-addressed margin/evidence fingerprints or Story 1.3 Decision identity recipe.

### References

- [Epic Story 1.5](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/epics.md)
- [PRD FR-3/NFR-1/NFR-8](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md)
- [Architecture AD-14](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Story 1.4](/home/officer/advanced_crypto_bot/_bmad-output/implementation-artifacts/1-4-menerapkan-cost-aware-abstention-dan-hysteresis.md)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-08-27: 15 focused replay contract tests passed.
- 2026-08-27: 124 focused Stories 1.2–1.5/identity tests passed.
- 2026-08-27: 191 AutoTrade Next contract + Strategy2 tests passed; compileall and diff hygiene passed.
- 2026-08-27: Full suite 844 passed, 15 failed, 5 errors, 22 subtests; 14 failures/5 errors match known legacy baseline and the extra `future_mark` timing flake passed in isolation.
- 2026-08-27: Post-review gates: 61 review-focused and 216 AutoTrade Next/Strategy2 tests passed; full suite 870 passed with unchanged 14 failures/5 errors and 22 subtests.

### Implementation Plan

- Red-green-refactor complete immutable replay inputs before regeneration.
- Delegate all policy/decision behavior to Story 1.4 pure transition.
- Compare versioned canonical semantic projections with closed exclusions and exact diffs.

### Completion Notes List

- Added complete immutable replay manifest and decision bundle with typed, fail-closed consistency checks.
- Added pure recorded-input regeneration with zero external-call invariant and three explicit AD-14 replay modes.
- Added versioned semantic projection/hash and exact deterministic diffs with a closed observability-only exclusion allowlist.
- Preserved Story 1.2–1.4 behavior; all relevant focused and cross-system regression gates pass.

### File List

- `_bmad-output/implementation-artifacts/1-5-membuktikan-deterministic-decision-replay.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/domain/errors.py`
- `advanced_crypto_bot/autotrade_next/domain/replay.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_deterministic_replay.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`

## Change Log

- 2026-08-27: Created comprehensive Story 1.5 context and started implementation.
- 2026-08-27: Implemented deterministic decision replay and semantic comparison; moved to review.
- 2026-08-27: Applied all 7 adversarial review patches and marked Story 1.5 done.
