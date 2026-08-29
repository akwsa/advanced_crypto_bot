---
baseline_commit: 13b54a97dd0781613b73e6797bfaa7a289b42927
---

# Story 1.6: Menyajikan provenance decision read-only

Status: done

## Story

As a Officer,
I want melihat Candidate→Decision correlation trail dari projection read-only,
so that alasan action dapat dipahami tanpa membaca database canonical atau log mentah.

## Acceptance Criteria

1. Immutable versioned projection envelopes menerima Candidate dan Decision facts dari explicit trusted outbox boundary. Envelope membekukan content-bound `outbox_ref`, event ID/type, schema/projection version, authority scope, journal sequence, aggregate ID/sequence, correlation/causation IDs, payload hash, dan exact typed payload; identity/payload/linkage mismatch ditolak typed tanpa partial effect. Reducer memverifikasi binding envelope dari boundary tersebut, bukan membuktikan persistence commit.
2. Pure projection reducer menerima at-least-once delivery secara idempotent. Exact duplicate event adalah no-op; event ID atau aggregate sequence yang sama dengan payload berbeda adalah integrity conflict dan tidak mengubah state/view/checkpoint.
3. Delivery out-of-order disimpan sebagai immutable pending input dan hanya diterapkan menurut contiguous `journal_seq`. Projection high-water adalah sequence contiguous tertinggi yang berhasil diterapkan, tidak pernah `max(seen)`, tidak melewati gap/failure, dan duplicate lama tidak meregresinya.
4. Candidate dan Decision boleh tiba terbalik. View diterbitkan hanya setelah exact Candidate ID/snapshot reference/scope/instrument/horizon/correlation linkage tervalidasi; seluruh permutation delivery yang valid konvergen ke canonical bytes dan high-water identik.
5. Versioned `DecisionProvenanceView` menampilkan exact Candidate/Decision IDs, snapshot reference, action, structured reason/evidence, boundary, conservative cost edge dan cost/uncertainty evidence refs, Policy version serta previous/next Policy State, Position context, correlation/causation IDs, dan projection high-water. Projection tidak menghitung ulang atau mengganti Decision.
6. Read surface memakai typed query port saja: exact scope-bound lookup dan deterministic keyset page dengan bounded size, stable `as_of_high_water`, versioned opaque cursor yang mengikat scope/filter/order tuple, serta immutable result tuple. Cursor malformed/foreign-version/scope/filter ditolak typed; tidak ada OFFSET atau direct canonical-store access.
7. Consumer/reducer mempunyai no mutation/command/venue/network/clock/random/credential capability. Notification/dashboard failure direpresentasikan sebagai isolated retry lalu dead-letter disposition yang mempertahankan event/error/attempt evidence; canonical Candidate, Decision, dan outbox payload bytes tidak berubah dan commit path tidak memanggil consumer.
8. Story tetap structural/pure contract: tanpa SQLite schema/runtime DDL, pseudo durable store, Redis, Telegram/dashboard framework, live/private venue adapter, trade-capable secret, legacy import, atau Intent/Order/Fill/Position/outcome invention. Projection-local atomic inbox/checkpoint persistence dan transport ack diimplementasikan ketika application/adapter contracts tersedia; Story 1.6 membuktikan reducer/query semantics yang adapter tersebut wajib ikuti.

## Tasks / Subtasks

- [x] Definisikan immutable committed projection event contracts (AC: 1, 4–5, 8)
  - [x] Candidate/Decision event payloads reuse exact Story 1.2–1.4 contracts dan canonical hashes.
  - [x] Validate event/scope/sequence/correlation/causation/linkage dan reject foreign types/version.
  - [x] Freeze cost/uncertainty evidence tanpa parallel Decision evaluator.
- [x] Implementasikan pure idempotent/out-of-order provenance reducer (AC: 2–5, 8)
  - [x] Immutable projection state menyimpan applied fingerprints, staged Candidate/Decision, pending gaps, views, dan contiguous high-water.
  - [x] Exact duplicates no-op; conflicting duplicates fail closed tanpa partial state.
  - [x] Drain contiguous events deterministically dan publish view hanya setelah complete linkage.
- [x] Implementasikan read-only query contracts dan deterministic keyset semantics (AC: 5–6, 8)
  - [x] Scope-bound exact lookup dan stable-as-of immutable page.
  - [x] Versioned content-bound cursor, bounded page size, deterministic ordering/tie break.
  - [x] Query protocol tidak mengekspos mutation, repository, command, atau credential capability.
- [x] Implementasikan isolated delivery failure disposition (AC: 7–8)
  - [x] Typed retry/dead-letter outcomes preserve event/error/attempt evidence.
  - [x] Exhaustion deterministic; canonical facts/outbox bytes remain unchanged.
  - [x] Jangan mengklaim persistence/ack yang belum memiliki application/store boundary.
- [x] Tambahkan exports, layer dependency guards, dan comprehensive contract tests (AC: 1–8)
  - [x] Duplicate/conflict, Decision-first, all ordering permutations, gap/high-water, multi-scope/link mismatch.
  - [x] Complete view fields, canonical/golden/100-run stability, immutable input/state.
  - [x] Lookup/pagination cursor bounds/as-of/filter/scope/error cases dan no mutation surface.
  - [x] Retry/dead-letter isolation serta unchanged canonical bytes.
- [x] Jalankan focused, seluruh AutoTrade Next contracts, Strategy2, compile/diff hygiene, dan full regression gates (AC: 1–8)

### Review Findings

- [x] [Review][Decision] Tentukan trust boundary untuk klaim “committed outbox facts only” — resolved: gunakan trusted content-bound `outbox_ref`, defer verifikasi commit/persistence aktual, dan nyatakan reducer memverifikasi envelope dari trust boundary alih-alih membuktikan commit sendiri.
- [x] [Review][Patch] Tambahkan trusted content-bound outbox reference dan hilangkan overclaim commit-proof dari reducer pure [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:158]
- [x] [Review][Patch] Bind calibration horizon, evidence refs/values/requested size, dan conservative edge ke exact PolicyTransition [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:99]
- [x] [Review][Patch] Jangan advance contiguous high-water melewati Decision yang belum dapat divalidasi terhadap Candidate [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:430]
- [x] [Review][Patch] Reject later aggregate sequence yang mengubah Candidate/Decision identity payload immutable [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:383]
- [x] [Review][Patch] Validasi seluruh ProjectionState indexes, uniqueness, scope, ordering, dan canonical consistency [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:344]
- [x] [Review][Patch] Harden cursor field/range/as-of/order-tuple validation dan bind ke state snapshot yang sah [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:543]
- [x] [Review][Patch] Hilangkan candidate lookup ambigu saat beberapa policy version menghasilkan Decision berbeda [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:525]
- [x] [Review][Patch] Pisahkan structured reason evidence dari cost/shortfall/calibration uncertainty evidence [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:482]
- [x] [Review][Patch] Perketat import guard untuk ast.Import, dynamic import, relative depth, dan explicit per-layer allowlist [advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py:327]
- [x] [Review][Patch] Tambahkan event/receive latency timestamps yang diwajibkan NFR-4 tanpa wall-clock synthesis [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:158]
- [x] [Review][Patch] Enforce contiguous per-aggregate sequence selain global journal sequence [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:383]
- [x] [Review][Patch] Pertahankan full immutable event, max-attempt, error, dan attempt evidence pada retry/dead-letter outcome [advanced_crypto_bot/autotrade_next/projections/decision_provenance.py:630]
- [x] [Review][Patch] Lengkapi adversarial tests untuk exact view fields, rehashed scope/linkage, valid journal orders, state conflicts, dan cursor variants [advanced_crypto_bot/tests/autotrade_next/contract/test_decision_provenance_projection.py:121]

## Dev Notes

### Developer Context

- Reuse `CandidateSnapshot`, `CanonicalDecision`, `PolicyTransition`, `PolicyState`, evidence objects, `canonical_bytes`, dan deterministic identities. Jangan membuat DTO yang menghitung ulang action/reason.
- Story 1.6 hanya Candidate→Decision/Policy slice. FR28 Intent→Order→Fill→Position→outcome berkembang setelah Epic 2 facts tersedia.
- `projection_high_water` berarti journal sequence contiguous, bukan event arrival maximum. Event di atas gap dibuffer immutable; event lama yang exact duplicate no-op.
- Complete view memerlukan `PolicyTransition` plus gross/shortfall/calibration evidence karena `CanonicalDecision` sendiri tidak membawa semua cost/uncertainty detail.
- Reducer adalah pure value transition yang memverifikasi trusted content-bound `outbox_ref`; verifikasi commit/persistence aktual, atomic inbox/view/checkpoint transaction, dan transport acknowledgement tetap requirement application/store adapter mendatang, bukan pseudo-store di story ini.
- Story 1.5 `PROJECTION_REBUILD` tetap unsupported: jangan mengaktifkannya sampai canonical event/store rebuild harness tersedia.

### Architecture Compliance

- AD-01 import matrix: `ports → domain`; `projections → domain+ports`; tidak ada reverse/horizontal adapter dependency.
- AD-03 projection menyalin exact immutable Decision; tidak mengubah action/reason/boundary/snapshot ref.
- AD-06 at-least-once, inbox/idempotence, contiguous checkpoint, retry/dead-letter isolation.
- AD-14/AD-26 canonical order/hash/golden determinism; projection rebuild belum diklaim.
- AD-16/AD-17 projection rebuildable dan read-only; dashboard/notification asynchronous dan non-authoritative.
- AD-19 future SQLite Read API harus `mode=ro` + `query_only=ON`; tidak ada SQLite pada story ini.

### File Structure Requirements

- NEW `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- NEW `advanced_crypto_bot/autotrade_next/ports/query.py`
- NEW `advanced_crypto_bot/autotrade_next/projections/__init__.py`
- NEW `advanced_crypto_bot/autotrade_next/projections/decision_provenance.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_decision_provenance_projection.py`
- UPDATE `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` dengan explicit layer/module dependency matrix.
- Hindari perubahan pada identity recipe, Decision evaluator, policy evaluator, replay exclusions, legacy modules, adapters, dan database.

### Testing Requirements

- Pin golden projection/view/cursor hashes; ulangi reduction 100 kali dan dengan permutation valid.
- Test seq `2→1`, gap `1→3`, retry current/below high-water, conflicting event ID dan aggregate sequence, serta unrelated scopes.
- Verify Decision-first tidak menerbitkan partial view dan Candidate arrival menghasilkan view yang sama dengan in-order.
- Verify exact action/reason/evidence/boundary/state/correlation/causation content dan no float/repr/coercion.
- Pagination stable as-of ketika state baru tumbuh; no duplicate/skip; invalid page size/cursor version/scope/filter typed.
- Structural AST/import/API tests membuktikan projection/query tidak mengimpor application/adapters/legacy/network dan port tidak memiliki mutation method.

### Previous Story Intelligence

- Story 1.5 selesai setelah 7 adversarial patches: manifest/state binding lengkap, replay error boundary, hardened semantic diffs, cross-process golden vectors, dan per-module dependency graph.
- Reuse content-addressing helper/pattern dan closed version checks. Jangan melemahkan Story 1.2–1.5 invariants.
- Latest gates: 61 review-focused, 216 AutoTrade Next/Strategy2, full suite 870 passed dengan unchanged 14 failures/5 errors legacy dan 22 subtests.

### References

- [Epic Story 1.6](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/epics.md)
- [PRD FR-28/NFR-4](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md)
- [Architecture AD-01/03/06/14/16/17/19/26](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Story 1.5](/home/officer/advanced_crypto_bot/_bmad-output/implementation-artifacts/1-5-membuktikan-deterministic-decision-replay.md)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-08-27: RED confirmed missing `autotrade_next.projections` module.
- 2026-08-27: 37 focused projection/identity contract tests passed.
- 2026-08-27: 233 AutoTrade Next contract + Strategy2 tests passed; compileall and diff hygiene passed.
- 2026-08-27: Full suite 887 passed with unchanged 14 failures/5 errors legacy and 22 subtests.
- 2026-08-27: Post-review gates passed: 45 focused and 240 AutoTrade Next/Strategy2 tests; compileall and diff hygiene passed.
- 2026-08-27: Full suite 894 passed with unchanged 14 failures/5 errors legacy and 22 subtests.

### Implementation Plan

- Red-green-refactor event contracts, reducer, query/cursor, then delivery disposition.
- Keep all behavior pure/immutable and reuse prior canonical domain types.
- Prove convergence, contiguous high-water, and read-only structural boundaries before integration scope.

### Completion Notes List

- Added versioned committed Candidate/Decision projection envelopes with exact canonical identity and payload binding.
- Added pure immutable reducer with duplicate/conflict handling, out-of-order buffering, contiguous high-water, and complete provenance joins.
- Added scope-bound read-only lookup/keyset pagination plus stable-as-of opaque cursors.
- Added deterministic isolated retry/dead-letter disposition without persistence, network, command, or credential capability.
- Added golden vectors, 100-run convergence, linkage/gap/cursor/failure tests, and explicit layer-import enforcement.
- Applied all 13 review patches: trusted content binding, exact transition/evidence validation, link-safe global and per-aggregate sequencing, immutable entity/state invariants, snapshot-bound cursors, unambiguous multi-policy lookup, structured evidence, NFR-4 timestamps, full retry evidence, hardened import guards, and expanded adversarial coverage.
- Clarified that the pure reducer validates envelopes supplied by the trusted outbox boundary; actual persistence commit verification remains deferred to the canonical application/store boundary.

### File List

- `_bmad-output/implementation-artifacts/1-6-menyajikan-provenance-decision-read-only.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- `advanced_crypto_bot/autotrade_next/ports/query.py`
- `advanced_crypto_bot/autotrade_next/projections/__init__.py`
- `advanced_crypto_bot/autotrade_next/projections/decision_provenance.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_decision_provenance_projection.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`

## Change Log

- 2026-08-27: Created comprehensive Story 1.6 context; status ready-for-dev.
- 2026-08-27: Implemented read-only Decision provenance projection contracts; moved to review.
- 2026-08-27: Applied all 13 adversarial review patches, passed regression gates, and moved Story 1.6 to done.
