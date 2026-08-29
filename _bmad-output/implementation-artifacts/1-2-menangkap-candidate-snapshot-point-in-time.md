---
baseline_commit: 13b54a97dd0781613b73e6797bfaa7a289b42927
---

# Story 1.2: Menangkap Candidate Snapshot point-in-time

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Officer,
I want setiap scan membekukan semua input sebelum gate pertama,
so that saya dapat membuktikan keputusan memakai data, clock, universe, dan configuration yang tersedia saat itu.

## Acceptance Criteria

1. Given satu closed-bar trigger atau protective-event trigger yang valid, when Candidate dibuat, then snapshot immutable menyimpan ordered input IDs; correlation dan causation reference; event dan receive time UTC yang terpisah; source cursors beserta capability, freshness, dan quality; universe serta instrument-rules version; scheduler trigger; seluruh clock read; RNG algorithm/state reference; runtime, numeric, environment, code, image, dan dependency-lock references; data, feature, model, configuration, serta external-response references; dan deterministic Candidate ID.
2. Candidate ID memakai recipe `candidate` v1 dari Story 1.1 tanpa perubahan field atau hash: `instrument_id`, `horizon_id`, `trigger_kind`, `trigger_at_utc`, `scan_trigger_version`, `data_revision`, serta optional `parent_position_id`. Receive time dan provenance lain tidak boleh diam-diam masuk identity recipe.
3. Given duplicate delivery dengan identity inputs serta `data_revision` yang sama, when capture diulang, then semantic Candidate ID dan canonical snapshot bytes identik. Urutan `ordered_input_ids`, clock reads, source cursors, dan external responses dipertahankan sebagai evidence; capture tidak melakukan sorting atau mengambil wall clock/RNG/runtime state sendiri.
4. Given late correction atas Candidate original, when revision dengan `data_revision` baru ditangkap, then Candidate ID baru menunjuk root original Candidate, berstatus non-executable/audit-only, dan original tetap byte-identical. Correction tanpa original, revision yang sama, identity scope yang tidak cocok, atau correction chain ambigu ditolak atomik.
5. Closed-bar Candidate tidak membawa `parent_position_id`; protective-event Candidate wajib membawa `parent_position_id`. Trigger kind lain, timestamp naive/non-UTC, blank/invalid stable reference, raw secret/config payload, binary float, atau provenance container yang mutable/unsupported ditolak dengan typed `CandidateCaptureError` dan tidak menghasilkan partial snapshot.
6. Missing required provenance adalah invalid capture dan ditolak atomik. Provenance lengkap yang menyatakan stale, gapped, unqualified, ambiguous, atau quality failure tetap disimpan sebagai immutable historical snapshot dengan `executable=False` dan structured eligibility reason; ia tidak boleh fail-open untuk entry.
7. Setelah dibentuk, atribut snapshot dan seluruh nested collection tidak dapat dimutasi. Perubahan pada list/dict input milik caller setelah capture tidak mengubah snapshot, canonical bytes, atau Candidate ID; overwrite in-memory ditolak oleh immutable value contract. Persistence overwrite/CAS, schema, journal, dan UnitOfWork tetap di luar Story 1.2 tetapi historical overwrite tetap merupakan invariant wajib untuk layer tersebut.
8. Implementasi tetap pure domain di namespace `autotrade_next`, menggunakan Python stdlib dan kernel canonical/identity Story 1.1. Tidak ada database, network, exchange, scheduler runtime, Redis, Telegram/dashboard, legacy import, live adapter, atau runtime wiring.

## Tasks / Subtasks

- [x] Definisikan contract Candidate dan provenance immutable pada `autotrade_next/domain/candidate.py` (AC: 1, 5–8)
  - [x] Buat enum/value object frozen dan slotted untuk trigger, quality/eligibility, source cursor, clock read, RNG reference, runtime manifest reference, serta versioned evidence references; seluruh collection tersimpan sebagai tuple dengan order asli.
  - [x] Buat `CandidateSnapshot` frozen/slotted yang membawa identity inputs, provenance lengkap, `candidate_id`, optional root `original_candidate_id`, `executable`, dan structured eligibility reason.
  - [x] Sediakan explicit canonical projection/value method yang hanya menghasilkan value legal `atr-json-v1`; jangan memakai `asdict`, `repr`, `default=str`, wall clock, fresh UUID, atau hidden default.
- [x] Implementasikan pure capture dan correction boundary (AC: 2–7)
  - [x] `capture_candidate(...)` memvalidasi seluruh input dahulu, mengambil defensive immutable snapshot, lalu memakai `build_identity("candidate", ...)` dari Story 1.1 tanpa mengubah recipe.
  - [x] Terapkan closed-bar versus protective-event parent contract, exact UTC datetime, stable nonblank references, explicit ordered provenance, dan typed rejection tanpa partial result.
  - [x] Bedakan missing/structurally invalid provenance (typed rejection) dari complete-but-bad evidence (historical non-executable snapshot dengan closed reason taxonomy).
  - [x] `revise_candidate(...)` memerlukan original Candidate, `data_revision` baru, scope/trigger identity yang sama selain revision, menghasilkan root-original lineage, dan selalu audit-only/non-executable.
- [x] Tambahkan typed error dan public exports minimal (AC: 5, 8)
  - [x] Tambahkan `CandidateCaptureError` dengan stable `error_code`, structural `path`, severity, retryable, evidence_ref, correlation_id, dan tanpa evaluasi `repr()` input asing.
  - [x] Export hanya contract publik Story 1.2 dari `autotrade_next/domain/__init__.py`; pertahankan dependency direction `domain → stdlib/domain`.
- [x] Tambahkan contract/property tests pada `tests/autotrade_next/contract/test_candidate_snapshot.py` (AC: 1–8)
  - [x] Uji closed-bar dan protective trigger, exact canonical bytes, recipe identity existing, 100-run determinism, duplicate delivery, ordered evidence, event/receive separation, dan absent-vs-present parent.
  - [x] Uji revision baru/root lineage, repeated correction determinism, correction invalid/ambiguous, original byte stability, audit-only status, serta bahwa recipe/digest Story 1.1 tidak berubah.
  - [x] Uji nested immutability dan defensive capture terhadap mutasi input caller; mapping/list asing atau torn mapping harus ditolak deterministik, bukan tersimpan dangkal.
  - [x] Parametrize setiap missing provenance, blank/invalid ref, trigger invalid, datetime naive/non-UTC, float/Decimal/secret payload, bad eligibility taxonomy, serta exact typed error code/path dan no partial snapshot.
  - [x] Perbarui AST dependency guard agar module `candidate` diizinkan sebagai relative domain module tanpa memperlonggar forbidden-import matrix.
- [x] Jalankan validation gates dan regression (AC: 1–8)
  - [x] Focused Story 1.2 contract tests lulus.
  - [x] Seluruh `tests/autotrade_next/contract` lulus dan golden vectors Story 1.1 tetap byte-identical.
  - [x] Regression Strategy 2 yang dipakai Story 1.1, compile/import check, dan full repository suite dijalankan; bedakan baseline legacy failures dari regresi baru dengan bukti.

### Review Findings

- [x] [Review][Patch] Dukung revision chain dengan complete immutable lineage; verifikasi seluruh ancestor, tolak reuse Candidate ID/data revision, dan ikat predecessor agar branch dengan ID sama tidak menghasilkan bytes berbeda [advanced_crypto_bot/autotrade_next/domain/candidate.py:359]
- [x] [Review][Patch] Simpan freshness dan quality per source cursor sesuai AC 1/6 [advanced_crypto_bot/autotrade_next/domain/candidate.py:43]
- [x] [Review][Patch] Ganti generic RNG ref dengan contract algorithm plus state/seed reference [advanced_crypto_bot/autotrade_next/domain/candidate.py:152]
- [x] [Review][Patch] Tolak whitespace/invalid Unicode dan terjemahkan canonical/identity failure menjadi CandidateCaptureError sebelum snapshot dipublikasikan [advanced_crypto_bot/autotrade_next/domain/candidate.py:315]
- [x] [Review][Patch] Batasi config provenance pada opaque version/hash reference agar raw secret/config payload tidak terserialisasi [advanced_crypto_bot/autotrade_next/domain/candidate.py:194]
- [x] [Review][Patch] Type-guard candidate_id sebelum equality agar foreign object tidak meloloskan typed error boundary [advanced_crypto_bot/autotrade_next/domain/candidate.py:269]
- [x] [Review][Patch] Perketat contract tests ke exact error code/path dan tambah collision/forged-lineage negative vectors [advanced_crypto_bot/tests/autotrade_next/contract/test_candidate_snapshot.py:255]

## Dev Notes

### Developer Context

- Deliverable Story 1.2 adalah pure domain Candidate capture. Story ini tidak membuat schema SQLite, repository, journal, application handler, scheduler, venue/MarketSnapshot adapter, Decision, projection, atau runtime wiring.
- `CandidateSnapshot` membekukan references/provenance sebelum gate pertama, bukan menyalin raw L2 book. Qualified executable L2 dan eligibility calculation adalah Story 2.1/2.2. Gunakan stable input/evidence IDs dan version/hash references agar capture bounded dan deterministic.
- Story 1.1 sudah menyediakan satu-satunya canonical byte boundary dan Candidate identity recipe. Jangan membuat serializer/hash baru dan jangan memperluas preimage Candidate dengan receive time atau provenance tambahan; perubahan semantic provenance wajib dinyatakan melalui `data_revision`.
- Candidate ID yang sama hanya sah untuk semantic duplicate. Bila non-identity provenance berubah, caller harus memakai correction path dan `data_revision` baru. Collision dengan payload berbeda tidak boleh dianggap idempotent overwrite.
- `frozen=True` tidak cukup bila field masih menunjuk list/dict mutable. Snapshot harus melakukan validation dan defensive conversion seluruh nested input menjadi immutable value objects/tuples sebelum object dipublikasikan.
- Missing structural provenance menghasilkan rejection tanpa Candidate parsial. Sebaliknya, evidence lengkap yang menyatakan kondisi buruk adalah fakta historis dan disimpan non-executable dengan reason tertutup; jangan membuang evidence buruk atau mengubahnya menjadi default sehat.
- Late correction tidak boleh menghasilkan executable Decision baru pada story ini. Ia audit-only, menunjuk root original, dan tidak mengubah Candidate/Decision historis. Governance untuk re-evaluation correction dapat dibuat oleh story terpisah setelah kontraknya disetujui.

### Normative Candidate Contract

- Trigger kind v1 hanya `CLOSED_BAR` dan `PROTECTIVE_EVENT`.
- Identity `trigger_at_utc` adalah canonical bar close atau protective event time. `event_at_utc` menyatakan source-event time yang dibekukan; `received_at_utc` menyatakan local receive time. Ketiganya exact timezone-aware UTC dan tidak diturunkan satu dari lainnya.
- `CLOSED_BAR` mensyaratkan `parent_position_id` absent. `PROTECTIVE_EVENT` mensyaratkan stable nonblank `parent_position_id`.
- `data_revision` adalah stable nonblank revision reference, bukan counter yang diambil dari mutable store atau current time.
- Candidate context membawa stable IDs/references yang relevan: authority scope, portfolio, experiment, strategy, horizon, instrument, correlation, causation/trigger, universe, instrument rules, scheduler, data, feature, model, configuration, serta external responses. Tidak ada secret value, credential, callable, client, adapter, atau environment dump.
- Source cursor entry memisahkan `venue_cursor` optional dari locally assigned `ingest_cursor` dan menyatakan `cursor_capability`; local cursor tidak pernah membuktikan venue continuity.
- Eligibility reason taxonomy minimum untuk complete-but-bad evidence: `STALE`, `GAPPED`, `UNQUALIFIED`, `AMBIGUOUS`, dan `QUALITY_FAILED`. Snapshot executable wajib memakai `ELIGIBLE` dan tidak membawa exclusion reason; state non-executable wajib membawa tepat satu reason serta evidence reference.
- Clock/RNG/runtime tidak dibaca oleh factory. Caller menyerahkan ordered clock reads, RNG algorithm dan state/seed reference, runtime/numeric/environment versions, code commit, image digest, serta dependency lock reference secara eksplisit.
- Canonical projection memasukkan seluruh semantic snapshot field dalam urutan/schema version yang dikunci. `candidate_id` direpresentasikan dengan canonical key; enum direpresentasikan dengan string value; tuple tetap ordered array; datetime melewati `canonical_bytes` Story 1.1.

### Revision Contract

- `revise_candidate(original, ..., data_revision=new_revision)` hanya mengubah data revision dan corrected provenance; identity scope/trigger fields lain harus cocok dengan original.
- `new_revision` harus berbeda dari original/current revision. Repeated correction atas original dengan revision dan provenance sama menghasilkan Candidate ID serta canonical bytes sama.
- `original_candidate_id` selalu menunjuk root original, bukan membuat lineage chain yang ambigu. Bila input correction berasal dari revision, factory menelusuri root reference yang sudah dibekukan dan menolak mismatch.
- Revision selalu `executable=False` dengan reason `LATE_CORRECTION`; original object/canonical bytes tidak berubah. Persistence layer masa depan wajib append-only dan menolak overwrite committed Candidate.

### Typed Error Contract

- Stable codes minimum: `INVALID_CANDIDATE_TRIGGER`, `MISSING_CANDIDATE_PROVENANCE`, `INVALID_CANDIDATE_REFERENCE`, `INVALID_CANDIDATE_TIMESTAMP`, `INVALID_CANDIDATE_VALUE`, `INVALID_CANDIDATE_ELIGIBILITY`, `INVALID_CANDIDATE_PARENT`, `INVALID_CANDIDATE_REVISION`, `CANDIDATE_SCOPE_MISMATCH`, dan `CANDIDATE_ALREADY_CAPTURED` untuk future append boundary.
- Error membawa tuple `path` ke field/index gagal, `partial_snapshot=None`, `severity="ERROR"`, `retryable=False`, optional evidence/correlation metadata, dan tidak memanggil `str()`/`repr()` pada offending object.
- Canonical/identity errors boleh dipertahankan sebagai `__cause__`, tetapi public capture boundary harus konsisten mengembalikan typed Candidate error tanpa snapshot parsial.

### Architecture Compliance

- AD-01: target tetap `autotrade_next/domain`; hanya stdlib dan relative domain imports.
- AD-02: IDs/version explicit, event/receive time UTC terpisah, no wall clock/fresh UUID, no binary float.
- AD-03: Candidate immutable; correction revision baru; downstream tidak dapat overwrite snapshot reference.
- AD-08: cursor capability, freshness, quality, instrument rules, dan universe point-in-time dibekukan; local cursor bukan venue truth.
- AD-14: ordered inputs, clocks, RNG, runtime/code/image/lock, model/data/config, dan external responses tersedia untuk replay bundle berikutnya.
- AD-26: reuse `atr-json-v1` dan Candidate identity recipe v1 byte-for-byte.

### Library / Framework Requirements

- Gunakan Python stdlib: `dataclasses`, `datetime`, `enum`, dan typing/collections abstractions yang diperlukan.
- Gunakan `@dataclass(frozen=True, slots=True)` untuk immutable records, ditambah defensive nested conversion/validation.
- Tidak menambah dependency. Jangan memakai Pydantic, ORM, UUID generator, random, system clock, serialization package, atau hashing package baru.
- Dokumentasi Python 3.12 menegaskan aware datetime mewakili instant yang tidak ambigu dan dataclass menyediakan `frozen`/`slots`; kontrak proyek tetap lebih ketat dengan exact UTC dan nested immutability.

### File Structure Requirements

- NEW `advanced_crypto_bot/autotrade_next/domain/candidate.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/errors.py`
- UPDATE `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_candidate_snapshot.py`
- UPDATE `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` hanya untuk narrow relative-module allowlist/dependency guard bila diperlukan.
- UPDATE story file dan sprint tracker hanya pada area yang diizinkan workflow.
- Jangan update legacy `autotrade/`, `strategy2/`, `core/database.py`, runtime/bootstrap, adapter, dashboard, atau deployment files.

### Testing Requirements

- Test exact canonical bytes/schema version, bukan hanya dataclass equality atau parsed JSON.
- Assert Candidate ID memakai existing `build_identity("candidate", fields)` dan existing golden identity corpus tetap lulus tanpa perubahan expected digest.
- Assert urutan evidence dipertahankan. Perubahan order mengubah snapshot canonical bytes; Candidate ID hanya berubah bila identity inputs/data revision berubah, sesuai recipe v1.
- Test source mutation sesudah capture dan direct nested mutation; snapshot bytes/ID harus tetap sama.
- Negative tests menegaskan exact error code/path, `partial_snapshot is None`, serta tidak ada database/network/random/time side effect.
- Jalankan focused tests, seluruh contract suite baru, regression Strategy 2, compile/import guard, dan full repository suite. Full-suite baseline Story 1.1 mencatat 742 passed, 14 failed, 5 errors dari legacy; tidak boleh muncul failure baru atau import `autotrade_next` pada baseline debt tersebut.

### Previous Story Intelligence

- Story 1.1 selesai pada commit `13b54a9`; 46 canonical/identity contract tests lulus.
- Reuse `advanced_crypto_bot/autotrade_next/domain/encoding.py`, `identity.py`, `numeric.py`, dan `errors.py`. Candidate identity recipe v1 sudah immutable dan memiliki golden digest untuk closed-bar/protective vectors.
- Existing dependency guard di `test_identity_vectors.py` memiliki narrow relative-module allowlist; tambahkan `candidate` tanpa memperlonggar forbidden imports.
- Story 1.1 menolak mapping torn/duplicate, cycle, excessive depth, unsupported types, non-NFC Unicode, raw Decimal/float, dan non-UTC timestamp. Jangan melewati boundary tersebut dengan `asdict` atau string coercion.

### Git Intelligence Summary

- HEAD saat story dibuat: `13b54a9` (`feat: establish deterministic autotrade domain foundation`). Commit ini hanya menambah namespace `autotrade_next`, pure domain foundation, tests, dan planning artifacts; runtime legacy tidak disentuh.
- Worktree memiliki handoff untracked milik user. Jangan menghapus, memindah, atau memasukkannya secara tidak sengaja dalam perubahan Story 1.2.
- Pola implementasi sebelumnya adalah red-green-refactor, exact typed errors, exact bytes/digests, AST dependency contract, focused regression, lalu full-suite baseline comparison.

### Latest Technical Information

- Python 3.12 `datetime` membedakan aware dan naive objects; project memperketatnya menjadi exact UTC-aware input untuk canonical boundary.
- Python 3.12 dataclass mendukung `frozen=True` dan `slots=True`, tetapi itu tidak membekukan nested mutable objects; defensive conversion tetap wajib.
- Tidak ada API/library eksternal yang perlu di-upgrade untuk story pure-domain ini; pin runtime/build Architecture Spine tidak diubah.

### Project Structure Notes

- Git root adalah `/home/officer/advanced_crypto_bot`; package/test root berada di subdirectory `advanced_crypto_bot/`.
- Tidak ada `project-context.md`; aturan normatif berasal dari SPEC, PRD, Architecture Spine, Implementation Notes, Epic, dan previous story.
- Story 1.2 membentuk domain object yang kelak dikonsumsi Story 1.3 (Decision), 1.5 (replay), 1.6 (projection), dan 2.1/2.2 (qualified market evidence). Jangan mengimplementasikan capability downstream sekarang.

### References

- [Epic 1 dan Story 1.2](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/epics.md)
- [PRD FR-1, NFR-4, dan Data Governance](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md)
- [Architecture AD-01, AD-02, AD-03, AD-08, AD-14, AD-26](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Architecture Implementation Notes](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/IMPLEMENTATION-NOTES.md)
- [AutoTrade Replacement SPEC](/home/officer/advanced_crypto_bot/_bmad-output/specs/spec-autotrade-replacement/SPEC.md)
- [Story 1.1 implementation record](/home/officer/advanced_crypto_bot/_bmad-output/implementation-artifacts/1-1-menghasilkan-identity-dan-canonical-bytes-yang-stabil.md)
- [Python 3.12 datetime documentation](https://docs.python.org/3.12/library/datetime.html)
- [Python 3.12 dataclasses documentation](https://docs.python.org/3.12/library/dataclasses.html)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- RED: `python -m pytest tests/autotrade_next/contract/test_candidate_snapshot.py -q` → collection error karena `autotrade_next.domain.candidate` belum ada.
- GREEN: focused Story 1.2 suite → 17 passed.
- Contract regression: seluruh `tests/autotrade_next/contract` → 63 passed.
- Candidate + Strategy 2 regression → 105 passed; `compileall` dan `git diff --check` lulus.
- Full repository via `scripts/test.sh -q` → 759 passed, 14 failed, 5 errors. Failure/error set identik dengan baseline Story 1.1 (742 passed, 14 failed, 5 errors); kenaikan 17 pass berasal dari Story 1.2 dan tidak ada failure yang mengimpor `autotrade_next`.
- REVIEW focused: 25 Story 1.2 tests, 71 seluruh `autotrade_next` contracts, dan 113 contract+Strategy 2 tests passed.
- REVIEW full repository: 766 passed, 15 failed, 5 errors dalam 7,5 menit. Satu tambahan `future_mark` adalah time-sensitive fixture `now + 1 minute` yang kedaluwarsa akibat suite lambat; rerun seluruh tiga parameter `test_canonical_equity_fails_closed_without_fresh_bid` lulus. Effective baseline tetap 14 failed + 5 errors legacy.

### Implementation Plan

- Bangun value object frozen/slotted dan explicit canonical projection di pure domain.
- Validasi seluruh provenance dan identity sebelum object dipublikasikan; snapshot input collections menjadi tuple.
- Reuse Candidate identity recipe v1; pisahkan semantic ID dari complete provenance bytes.
- Modelkan correction sebagai append-only audit fact dengan root lineage dan fail-closed eligibility.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Story scope dikunci pada pure domain Candidate capture; persistence, market qualification, Decision, dan runtime wiring tetap deferred.
- Checklist quality review diterapkan: identity recipe reuse, nested immutability, correction lineage, fail-closed provenance, secret exclusion, dependency boundary, dan regression gates dibuat eksplisit.
- Implemented immutable Candidate/provenance value objects, exact canonical projection, defensive nested capture, and typed fail-closed validation.
- Implemented deterministic duplicate capture and audit-only late correction with root lineage while preserving the Story 1.1 identity recipe.
- Added 17 contract tests covering trigger legality, exact identity/canonical determinism, corrections, immutability, bad evidence, timestamps, unsupported values, and forged identity/lineage rejection.
- Verified no regression: 63 autotrade-next contracts and 105 focused+Strategy 2 tests pass; repository legacy baseline remains exactly 14 failures + 5 errors.
- Resolved all 7 adversarial review findings: content-addressed complete revision lineage, per-source freshness/quality, explicit RNG algorithm/state, strict canonical reference validation, opaque config refs, candidate type guard, and expanded collision/forgery tests.

### File List

- `_bmad-output/implementation-artifacts/1-2-menangkap-candidate-snapshot-point-in-time.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/domain/candidate.py`
- `advanced_crypto_bot/autotrade_next/domain/errors.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_candidate_snapshot.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`

## Change Log

- 2026-08-26: Created comprehensive Story 1.2 developer context and marked ready-for-dev.
- 2026-08-26: Implemented and validated immutable point-in-time Candidate capture; moved story to review.
- 2026-08-26: Applied all adversarial review patches, expanded Story 1.2 to 25 tests, and marked done.
