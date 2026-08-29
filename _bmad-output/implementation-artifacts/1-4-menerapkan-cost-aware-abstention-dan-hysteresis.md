---
baseline_commit: 13b54a97dd0781613b73e6797bfaa7a289b42927
---

# Story 1.4: Menerapkan cost-aware abstention dan hysteresis

Status: done

## Story

As a Officer,
I want policy hanya menambah exposure ketika conservative net edge cukup kuat dan confirmation state terpenuhi,
so that bot tidak overtrade karena gross signal, biaya, atau noise kecil.

## Acceptance Criteria

1. Gross lower bound, size-specific shortfall upper bound, required margin, calibration, dan boundary memakai immutable exact-value contracts. Conservative edge tepat `gross_lower - shortfall_upper` dan ENTER hanya lolos bila edge strict `>` preregistered margin; equality/below menghasilkan ABSTAIN.
2. Shortfall evidence memuat requested size, distribution ref, serta fee, tax/clearing, spread, slippage, impact, latency adverse selection, dan opportunity-cost/non-fill evidence. Semua nilai memakai `ScaledInteger` berskala sama; float, komponen hilang/duplikat, size non-positive, atau version mismatch ditolak typed tanpa partial transition.
3. Missing/stale calibration selalu memblokir ENTER dengan structured reason/evidence. Pada exposed state ia tidak menambah exposure dan tidak menghalangi HOLD, alpha/protective EXIT; protective EXIT tetap mengalahkan cost, calibration, confirmation, gap, dan entry veto.
4. Immutable Policy State membekukan policy/boundary version, confirmation counters, last processed Candidate refs, baseline counts (ENTER=2, protective EXIT=1, alpha EXIT=2), gap behavior, serta opaque high-water/protection refs. Policy/boundary mismatch ditolak, bukan di-reset diam-diam.
5. Dua consecutive qualifying closed-bar Candidate diperlukan untuk ENTER: pass pertama ABSTAIN/pending, pass kedua ENTER. Duplicate Candidate idempotent tidak menambah count; fail atau explicit data gap mereset ENTER confirmation. Gap tidak mereset alpha EXIT count, high-water, atau protection refs.
6. Alpha EXIT memerlukan dua confirmation: pertama HOLD/pending, kedua EXIT. Protective EXIT menghasilkan EXIT pada event pertama dan tidak pernah diturunkan. Semua hasil tetap melalui legal Canonical Decision Story 1.3 dengan identity recipe `(candidate_id, policy_version)` yang tidak berubah.
7. Pure transition mengembalikan prior state, next state, conservative edge, dan Canonical Decision secara deterministic/canonical tanpa memutasi input. Durable expected-sequence commit Decision+PolicyState+event/outbox menjadi kewajiban future application/UoW; story ini tidak membuat persistence atau pseudo-store.
8. Tidak ada wall clock, random, UUID, network, database, exchange, Redis, dashboard, Telegram, legacy import, raw secret, auto-retrain, auto-promotion, risk allocation, simulator/TCA generation, atau replay harness.

## Tasks / Subtasks

- [x] Definisikan immutable cost, calibration, dan Policy State contracts pada `autotrade_next/domain/policy.py` (AC: 1–4, 7–8)
  - [x] Exact gross/shortfall/margin contracts, complete component taxonomy, scale/version/ref validation.
  - [x] Frozen PolicyState dan PolicyTransition dengan explicit canonical projection dan preservation refs.
  - [x] Tambahkan typed `PolicyEvaluationError` mengikuti metadata convention.
- [x] Implementasikan pure cost gate dan hysteresis transition (AC: 1–7)
  - [x] Strict edge boundary, missing/stale calibration reasons, and no double-subtracted uncertainty.
  - [x] ENTER 2-confirmation, alpha EXIT 2-confirmation, protective EXIT immediate.
  - [x] Duplicate/gap behavior dan exact preservation high-water/protection.
- [x] Integrasikan hasil policy ke Canonical Decision Story 1.3 (AC: 3, 6–8)
  - [x] Tambah minimal structured reason taxonomy/controlled reason override tanpa mengubah identity recipe atau existing golden vector.
  - [x] Pertahankan legality, explicit EXIT target, parent Position binding, evidence refs, dan protective precedence.
- [x] Tambahkan exports, AST dependency guard, dan contract tests (AC: 1–8)
  - [x] Threshold below/equal/above, full shortfall composition, invalid numeric/type/scale/version cases.
  - [x] Confirmation tables, duplicate Candidate, gap permutations, protective precedence, immutable/canonical stability.
  - [x] Preserve seluruh Story 1.1–1.3 vectors dan narrow relative-import allowlist.
- [x] Jalankan focused, all AutoTrade Next contracts, Strategy 2, compile/diff hygiene, dan full regression gates (AC: 1–8)

### Review Findings

- [x] [Review][Patch] Bind exact required margin ke immutable versioned Policy State/boundary evidence; hapus free per-call margin yang dapat mengubah payload pada Decision ID sama [advanced_crypto_bot/autotrade_next/domain/policy.py:249]
- [x] [Review][Patch] Bind gross/shortfall evidence ke policy dan boundary version serta requested size yang sama, termasuk exact scale validation [advanced_crypto_bot/autotrade_next/domain/policy.py:71]
- [x] [Review][Patch] Kunci baseline confirmation policy tepat ENTER/protective/alpha `2/1/2` agar state tidak dapat mengubah perilaku normatif [advanced_crypto_bot/autotrade_next/domain/policy.py:176]
- [x] [Review][Patch] Tolak/reset Candidate non-executable sebelum ia dapat menambah ENTER confirmation [advanced_crypto_bot/autotrade_next/domain/policy.py:307]
- [x] [Review][Patch] Jadikan duplicate pending/completed ENTER dan alpha EXIT idempotent serta reject input drift pada Candidate ID sama [advanced_crypto_bot/autotrade_next/domain/policy.py:315]
- [x] [Review][Patch] Canonicalize complete shortfall component ordering agar permutation evidence tidak mengubah canonical bytes [advanced_crypto_bot/autotrade_next/domain/policy.py:111]
- [x] [Review][Patch] Bind confirmation state ke instrument dan Horizon agar bar lintas scope tidak memenuhi window yang sama [advanced_crypto_bot/autotrade_next/domain/policy.py:153]
- [x] [Review][Patch] Terjemahkan overflow edge/counter menjadi typed PolicyEvaluationError tanpa canonical partial output [advanced_crypto_bot/autotrade_next/domain/policy.py:172]
- [x] [Review][Patch] Tegakkan invariant lintas prior/next state, Decision policy, boundary, dan protection refs pada public PolicyTransition constructor [advanced_crypto_bot/autotrade_next/domain/policy.py:213]
- [x] [Review][Patch] Wajibkan PROTECTIVE_EVENT dengan matching parent Position sebelum protective precedence dapat diaktifkan [advanced_crypto_bot/autotrade_next/domain/policy.py:259]
- [x] [Review][Patch] Perketat controlled Story-1.4 reason override dengan mandatory reason-specific policy evidence [advanced_crypto_bot/autotrade_next/domain/decision.py:256]
- [x] [Review][Patch] Tambahkan regression matrix untuk completed duplicates, eligibility, baseline counts, scope/version/size drift, component permutation, overflow, protective trigger, dan exact typed errors [advanced_crypto_bot/tests/autotrade_next/contract/test_cost_hysteresis_policy.py:112]

## Dev Notes

### Developer Context

- Reuse `CandidateSnapshot`, `ScaledInteger`, `DecisionBoundary`, `PositionContext`, dan `evaluate_decision`; jangan membuat DTO Candidate/Decision kedua.
- Strategy menghasilkan gross evidence; frozen cost evidence memasok size-specific shortfall statistic. Decision policy menghitung net edge. Story ini tidak membuat CostModelPort/provider.
- Uncertainty sudah memilih lower/upper statistic; jangan menguranginya lagi sebagai nominal uang.
- Calibration freshness adalah explicit frozen status, bukan perhitungan `datetime.now()`.
- Transition wajib O(1); jangan scan empirical distribution di DecisionService.
- Duplicate detection memakai Candidate ID terakhir per counter. Explicit `data_gap` adalah continuity evidence dari caller; jangan menebak interval dari wall clock.
- Persistent secara domain berarti canonical state siap disimpan atomik. SQLite/UoW/CAS berada di story application/truth-store berikutnya.

### Architecture Compliance

- AD-01 pure domain/import matrix; AD-03 one Decision; AD-04 fixed exit precedence; AD-09 Strategy isolation; AD-10 cost-aware abstention; AD-26 canonical exact values.
- No pyramiding: exposed state tetap HOLD/EXIT. Policy State versi berbeda tidak berbagi counter.
- Protective/high-water refs hanya dibawa byte-identical; Story 1.4 tidak menghitung trailing/high-water baru.

### File Structure Requirements

- NEW `advanced_crypto_bot/autotrade_next/domain/policy.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/decision.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/errors.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_cost_hysteresis_policy.py`
- UPDATE `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` narrow allowlist only.
- Preserve seluruh uncommitted Story 1.2/1.3 files dan user handoff.

### Testing Requirements

- Exact threshold strictness, fixed scale, negative/foreign values, missing component/ref, immutable input freezing.
- ENTER pass/pass, pass/fail/pass, duplicate/pass, gap/pass/pass; alpha EXIT first/second; protective EXIT under every gate failure.
- Assert next state canonical bytes stable over 100 runs, prior state unchanged, high-water/protection preserved.
- Validate policy/boundary mismatch typed, error path, `partial_transition=None`, and no forbidden imports.

### Previous Story Intelligence

- Story 1.3 selesai setelah 9 adversarial patches; 35 focused dan 148 contract/Strategy 2 tests lulus.
- Constructor Decision sekarang menegakkan legal action/reason, position binding, exact target, incident, dan commit invariants. Jangan melewatinya.
- Full suite baseline efektif 14 legacy failures/5 errors; `future_mark` dapat time-sensitive selama suite panjang.

### References

- [Epic Story 1.4](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/epics.md)
- [PRD FR-4/FR-5](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md)
- [Architecture AD-09/AD-10](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Story 1.3](/home/officer/advanced_crypto_bot/_bmad-output/implementation-artifacts/1-3-menghasilkan-satu-action-yang-legal-dan-beralasan.md)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- RED: focused suite gagal collection dengan `ModuleNotFoundError: autotrade_next.domain.policy`.
- GREEN/refactor: 47 focused Decision+Policy tests lulus.
- Contract + Strategy 2: 160 tests lulus; compileall dan `git diff --check` bersih.
- Full regression: 813 passed, 15 failed, 5 errors, 22 subtests passed. Baseline efektif tetap 14 failed/5 errors; satu `future_mark` time-sensitive lulus saat rerun terisolasi.
- Review patches: 63 focused dan 176 contract/Strategy 2 tests lulus; compileall dan diff hygiene bersih.
- Full regression pasca-review: 830 passed, 14 baseline legacy failures, 5 baseline legacy errors, dan 22 subtests passed.

### Implementation Plan

- Red-green-refactor immutable policy contracts and exact transition tables.
- Reuse Story 1.3 canonical decision legalization; preserve identity/canonical golden vectors.
- Keep storage/UoW outside pure domain while making state transition canonical and persistable.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Menambahkan immutable exact gross/shortfall/calibration contracts dengan complete shortfall evidence taxonomy.
- Menambahkan canonical PolicyState/PolicyTransition dan pure strict cost gate tanpa I/O atau implicit clock.
- ENTER dan alpha EXIT memakai consecutive confirmation/idempotent Candidate refs; gap hanya mereset ENTER sementara protective state tetap byte-identical.
- Protective EXIT tetap immediate dan seluruh hasil dilegalkan melalui Canonical Decision Story 1.3 tanpa perubahan identity recipe.
- Menutup 12 adversarial findings: preregistered margin binding, evidence version/size/scope, baseline confirmation, replay idempotency, canonical ordering, typed overflow, transition invariants, dan protective provenance.

### File List

- `_bmad-output/implementation-artifacts/1-4-menerapkan-cost-aware-abstention-dan-hysteresis.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/autotrade_next/domain/policy.py`
- `advanced_crypto_bot/autotrade_next/domain/decision.py`
- `advanced_crypto_bot/autotrade_next/domain/errors.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_cost_hysteresis_policy.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`

## Change Log

- 2026-08-26: Created comprehensive Story 1.4 context and started implementation.
- 2026-08-26: Implemented and verified cost-aware abstention/hysteresis; moved Story 1.4 to review.
- 2026-08-26: Applied all adversarial review patches, verified regression gates, and marked Story 1.4 done.
