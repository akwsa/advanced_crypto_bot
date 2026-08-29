---
baseline_commit: 13b54a97dd0781613b73e6797bfaa7a289b42927
---

# Story 1.3: Menghasilkan satu action yang legal dan beralasan

Status: done

## Story

As a Officer,
I want setiap Candidate berakhir pada tepat satu Canonical Decision yang legal terhadap Position state,
so that dashboard, journal, dan execution tidak dapat menunjukkan action berbeda.

## Acceptance Criteria

1. Candidate flat hanya menghasilkan `ENTER|ABSTAIN`; Candidate exposed hanya `HOLD|EXIT`. `EXIT` wajib target quantity explicit; action lain dilarang membawa target.
2. Setiap Decision immutable membawa deterministic Decision ID v1, Candidate snapshot/key reference, frozen Position context, policy version, action, structured reason, boundary reference, correlation/causation IDs, dan exact canonical bytes.
3. Entry veto mengubah proposed `ENTER` menjadi `ABSTAIN`. Protective EXIT pada exposed state selalu menang atas `HOLD`/entry veto dan tidak dapat diturunkan. Candidate non-executable tidak pernah `ENTER`; exposed Candidate tetap boleh protective `EXIT`.
4. Semantic key tepat `(candidate_id, policy_version)` dan reuse recipe `decision` Story 1.1 tanpa perubahan. Evaluasi identik byte-stable; forged identity/reference ditolak typed tanpa partial Decision.
5. Pure commit transition menerima existing Decision dari repository boundary: absent menghasilkan `CREATED`; exact duplicate menghasilkan `IDEMPOTENT`; payload berbeda pada semantic key sama menghasilkan `CONFLICT` plus immutable `IntegrityIncident`, mengembalikan original tanpa mutation.
6. Illegal action/target/position transition ditolak dengan typed `DecisionError` dan structured `IntegrityIncident` descriptor. Durable UNIQUE constraint, atomic event/outbox, dan incident persistence menjadi kewajiban adapter/UoW story berikutnya; Story 1.3 tidak membuat pseudo-database.
7. Story tetap pure domain: tanpa I/O, wall clock, random, UUID, database, runtime, exchange, Redis, dashboard, Telegram, legacy import, atau live wiring. Cost edge, hysteresis, confirmation, allocation, dan Policy State transition tetap Story 1.4+.

## Tasks / Subtasks

- [x] Definisikan immutable Decision contracts pada `autotrade_next/domain/decision.py` (AC: 1–4, 7)
  - [x] Buat exact enums/value objects untuk action, position state, reason code, boundary, position context, incident, dan commit status.
  - [x] Buat frozen/slotted `CanonicalDecision` dengan explicit canonical projection `canonical-decision:v1` dan constructor validation.
  - [x] Reuse `build_identity("decision", {candidate_id, policy_version})`; jangan mengubah recipe/golden digest Story 1.1.
- [x] Implementasikan pure DecisionService evaluation (AC: 1–4, 6–7)
  - [x] Enforce legal state/action matrix, no pyramiding, explicit EXIT target, dan absence target untuk non-EXIT.
  - [x] Terapkan entry veto, non-executable Candidate fail-closed, dan protective EXIT dominance.
  - [x] Return structured deterministic reason/boundary/snapshot refs; typed rejection membawa incident descriptor dan `partial_decision=None`.
- [x] Implementasikan pure uniqueness/overwrite transition (AC: 5–7)
  - [x] `commit_decision(existing, proposed)` menghasilkan CREATED/IDEMPOTENT/CONFLICT secara deterministic.
  - [x] Conflict mempertahankan original byte-identical dan menghasilkan immutable IntegrityIncident; tidak ada storage/network side effect.
- [x] Tambahkan errors, exports, dependency guard, dan contract tests (AC: 1–7)
  - [x] Tambahkan `DecisionError` sesuai typed metadata convention dan public exports minimal.
  - [x] Tambahkan `test_canonical_decision.py`: legal/illegal matrix, veto/protective, ineligible Candidate, identity/bytes, immutability, forged refs, exact target, idempotency/conflict/incident.
  - [x] Update narrow AST relative-module allowlist tanpa memperlonggar forbidden imports.
- [x] Jalankan focused, contract, Strategy 2, compile/import, diff hygiene, dan full regression gates (AC: 1–7)

### Review Findings

- [x] [Review][Patch] Tegakkan matriks state/action dan kecocokan action/reason di constructor agar Decision ilegal tidak dapat dibuat langsung lalu di-commit [advanced_crypto_bot/autotrade_next/domain/decision.py:142]
- [x] [Review][Patch] Ikat Candidate protective/position event ke `PositionContext.position_id` yang sama agar EXIT tidak diarahkan ke posisi lain [advanced_crypto_bot/autotrade_next/domain/decision.py:217]
- [x] [Review][Patch] Tolak EXIT target negatif dan sertakan deterministic IntegrityIncident pada pelanggaran target [advanced_crypto_bot/autotrade_next/domain/decision.py:261]
- [x] [Review][Patch] Sertakan structured IntegrityIncident pada penolakan proposed action/transition yang terjadi di evaluator [advanced_crypto_bot/autotrade_next/domain/decision.py:203]
- [x] [Review][Patch] Sertakan IntegrityIncident ketika repository memberikan existing Decision dengan semantic key berbeda [advanced_crypto_bot/autotrade_next/domain/decision.py:248]
- [x] [Review][Patch] Pertahankan evidence penyebab Candidate ineligible serta sumber veto/protection pada structured DecisionReason [advanced_crypto_bot/autotrade_next/domain/decision.py:235]
- [x] [Review][Patch] Perketat invariant `DecisionCommitResult` agar conflict incident wajib berkode dan berkunci sesuai Decision original [advanced_crypto_bot/autotrade_next/domain/decision.py:188]
- [x] [Review][Patch] Ekspor `DecisionReason` melalui public package API agar kontrak Decision lengkap [advanced_crypto_bot/autotrade_next/domain/__init__.py:20]
- [x] [Review][Patch] Lengkapi contract tests dengan 100-run/golden bytes, constructor forgery, protective permutations, parent mismatch, incident path, input mutation, serta exact invalid-target type matrix [advanced_crypto_bot/tests/autotrade_next/contract/test_canonical_decision.py:55]

## Dev Notes

### Developer Context

- Story 1.1 menyediakan `atr-json-v1`, `ScaledInteger`, typed errors, dan immutable Decision identity recipe `(candidate_id, policy_version)`.
- Story 1.2 menyediakan `CandidateSnapshot`, candidate key/bytes, executability, correlation/causation provenance, dan audit-only correction lineage. Gunakan object tersebut langsung; jangan buat Candidate DTO kedua.
- `DecisionService` di story ini adalah pure function/domain service. Strategy proposal bukan Decision; evaluator melakukan legalization/veto sebelum membentuk canonical fact.
- Reason taxonomy v1: `ENTER_APPROVED`, `POLICY_ABSTAIN`, `ENTRY_VETO`, `CANDIDATE_INELIGIBLE`, `MAINTAIN_EXPOSURE`, `ALPHA_EXIT`, `PROTECTIVE_EXIT`. Detail cost/hysteresis belum boleh diimplementasikan.
- `DecisionBoundary` hanya versioned opaque ref/evidence refs. Ia bukan kalkulator threshold Story 1.4 dan tidak membawa float/raw secrets.
- `PositionContext` membekukan state dan stable snapshot/version reference; EXPOSED memerlukan position ID, FLAT melarangnya.
- Pure commit transition bukan canonical store. Future application/UoW wajib memanggil transition ini di dalam atomic UNIQUE/CAS transaction dan menyimpan incident/event/outbox bersama original state.

### Architecture Compliance

- AD-01 pure domain only; AD-03 one Decision per Candidate/policy; AD-04 action legality dan protective precedence; AD-06 future atomic command boundary; AD-26 existing identity/canonical profile.
- No binary float, wall clock, hidden default, `repr`, `default=str`, mutable mapping, or external call.
- Candidate-to-Decision pure work harus O(1); p99 commit deadline integration diuji kelak dengan storage.

### File Structure Requirements

- NEW `advanced_crypto_bot/autotrade_next/domain/decision.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/errors.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_canonical_decision.py`
- UPDATE `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` narrow allowlist only.
- Jangan mengubah identity recipe, Candidate schema, legacy/runtime/database/adapter/UI files.

### Testing Requirements

- Exhaustive legal/illegal state-action table; protective EXIT permutation dominance; exact error code/path/incident.
- Exact Decision identity and canonical bytes across 100 runs; input mutation cannot alter output.
- Same semantic key + same bytes idempotent; same key + different payload conflict/incident; original bytes unchanged.
- EXIT exact `ScaledInteger` target; non-EXIT target absent; bool/int/float/Decimal/foreign types fail closed.
- Run all `autotrade_next` contracts and preserve Story 1.1/1.2 vectors.

### Previous Story Intelligence

- Story 1.2 selesai dan 25 focused tests/71 contracts lulus setelah 7 review patches.
- Story 1.2 changes masih uncommitted di atas HEAD `13b54a9`; preserve seluruh file tersebut dan user handoff untracked.
- Existing AST guard narrow allowlist perlu menambah `decision` saja.

### References

- [Epic Story 1.3](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/epics.md)
- [PRD FR-2/NFR-2/NFR-3](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md)
- [Architecture AD-03/04/06/26](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Story 1.2 record](/home/officer/advanced_crypto_bot/_bmad-output/implementation-artifacts/1-2-menangkap-candidate-snapshot-point-in-time.md)
- [Python 3.12 enum documentation](https://docs.python.org/3.12/library/enum.html)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- RED: `test_canonical_decision.py` gagal import sebelum domain module tersedia.
- GREEN/refactor: 13 focused tests lulus.
- Contract + Strategy 2: 126 tests lulus; compileall dan `git diff --check` bersih.
- Full regression: 779 passed, 15 failed, 5 errors, 22 subtests passed. Baseline legacy efektif tetap 14 failed/5 errors; satu `future_mark` time-sensitive lulus saat rerun terisolasi (1 passed).
- Review patches: 35 focused dan 148 contract/Strategy 2 tests lulus; compileall dan diff hygiene bersih.
- Full regression pasca-review: 801 passed, 15 failed, 5 errors, 22 subtests passed; baseline efektif tetap 14 failed/5 errors karena `future_mark` time-sensitive lulus saat rerun terisolasi.

### Implementation Plan

- Red-green-refactor pure Decision contracts and exhaustive legality tests.
- Reuse existing Candidate/identity/canonical kernels; no persistence wiring.
- Model uniqueness as pure commit transition consumed by future atomic repository boundary.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Menambahkan pure immutable Canonical Decision kernel dengan legal action matrix, deterministic identity/bytes, structured reason, boundary, dan provenance refs.
- Entry veto dan Candidate non-executable fail closed ke ABSTAIN; protective EXIT mendominasi pada exposed position.
- Menambahkan pure CREATED/IDEMPOTENT/CONFLICT transition yang mempertahankan original dan menghasilkan immutable integrity incident.
- Tidak menambah persistence, runtime wiring, cost edge, hysteresis, atau scope story berikutnya.
- Menutup sembilan review findings: constructor invariants, cross-position protection, exact target, incidents, reason evidence, commit-result integrity, public export, dan expanded golden/edge contract coverage.

### File List

- `_bmad-output/implementation-artifacts/1-3-menghasilkan-satu-action-yang-legal-dan-beralasan.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/autotrade_next/domain/decision.py`
- `advanced_crypto_bot/autotrade_next/domain/errors.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_canonical_decision.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`

## Change Log

- 2026-08-26: Created comprehensive Story 1.3 context and started implementation.
- 2026-08-26: Implemented and verified Canonical Decision domain kernel; moved story to review.
- 2026-08-26: Applied all adversarial review patches, verified regression gates, and marked Story 1.3 done.
