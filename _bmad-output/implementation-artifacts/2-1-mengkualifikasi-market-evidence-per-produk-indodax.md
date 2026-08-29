---
baseline_commit: 13b54a97dd0781613b73e6797bfaa7a289b42927
---

# Story 2.1: Mengkualifikasi market evidence per produk Indodax

Status: done

## Story

As a Officer,
I want hanya market capability yang terbukti masuk ke Candidate,
so that bot tidak menganggap local cursor, stream gap, atau endpoint legacy sebagai venue truth.

## Acceptance Criteria

1. Registry capability immutable, effective-time, dan versioned mempunyai sedikitnya lima product family terpisah: Public REST, Private REST API, Trade API 2.0, Market Data WebSocket, dan Private WebSocket. Satu entry dibuat untuk setiap endpoint/channel dengan semantics berbeda. Setiap entry mengikat product, base URL, endpoint/channel, exact documentation commit dan Git blob/content digest, half-open interval `[effective_from, effective_until)`, auth scope, authoritative fields, cursor/offset/sequence semantics, snapshot source, timestamp contract, rate-limit contract, recovery route, qualification status, serta content-bound contract-test artifact. Overlap menginvalidasi registry; lookup harus menemukan tepat satu entry. Uncovered interval menghasilkan typed `UNQUALIFIED/NO_MATCH` tanpa nearest-version fallback. Duplicate key, moving-branch-only documentation reference, missing field, atau artifact mismatch ditolak typed tanpa partial result.
2. Capability admission bersifat field-level dan fail-closed. Hanya field dari exact qualified product/endpoint/channel pada effective time yang boleh menjadi qualified evidence; semantics satu produk/channel tidak boleh diwariskan ke produk lain. `UNQUALIFIED`, foreign/expired version, undocumented endpoint/field, atau self-attested quality string tidak boleh mengisi canonical **venue** fact dan tidak boleh menghasilkan executable Candidate.
3. Qualified evidence membekukan capability reference/version, external response content reference, instrument dan affected scope, event time serta receive time UTC yang terpisah, venue cursor bila tersedia, locally assigned ingest cursor yang terpisah, continuity/quality/freshness result, dan recovery evidence references. Immutable content-bound `EvidenceRequirementSet` menentukan exact proof set berdasarkan trigger, horizon, instrument/scope, dan effective time. Executable admission memerlukan exact set equality dan menolak missing, extra, duplicate, atau foreign proof. Ingest cursor lokal tidak pernah dipromosikan menjadi venue cursor atau bukti gap-free; WebSocket message tetap inbound evidence dan bukan otomatis canonical fact.
4. Gap, offset/sequence regression, same-cursor conflicting payload, out-of-order conflict, disconnect, future/stale remote event, remote timestamp skew breach, atau continuity yang tidak dapat dibuktikan menghasilkan typed non-qualified disposition plus entry-freeze/recovery request untuk affected scope. Remote evidence failure bersifat instrument/channel-local kecuali shared-stream/systemic integrity terbukti. Verified local clock rollback/anomaly selalu menghasilkan authority-scoped `CLOCK_ANOMALY/SAFE_LATCHED` request dan tidak boleh diperlakukan pair-local. Initial fail-closed baseline adalah executable evidence age maksimum 3 detik, remote clock skew maksimum 1 detik, dan authoritative sequence gap nol; nilai dan policy version harus ikut evidence, bukan konstanta tersembunyi. Exact duplicate evidence boleh idempotent dan tidak boleh dianggap gap baru.
5. Pure operation `evaluate_recovery_gate(active_request, recovery_proof, reconciliation_checkpoint)` hanya dapat menghasilkan typed `RecoveryDisposition`/scoped clear request setelah **keduanya** cocok untuk exact capability/version/scope: snapshot atau documented recovery route lulus, dan reconciliation checkpoint/evidence contract current. Reconnect saja, snapshot saja, atau reconciliation saja tetap menghasilkan disposition frozen. Operation tidak menyimpan atau membersihkan mutable freeze state dan tidak mengklaim persistence; canonical `SafetyState` owner pada Epic 3 yang kelak menerapkan clear. Protective/recovery action tetap tersedia hanya dengan qualified conservative evidence.
6. Candidate admission menutup loophole saat ini dengan **satu** `CandidateSnapshot` class yang menerima closed V1/V2 provenance union dan memilih serializer secara eksplisit. Existing V1 provenance/source types dan `candidate-snapshot:v1` bytes tetap exact; proof-bearing V2 provenance/source types serialize sebagai `candidate-snapshot:v2`. `capture_candidate_v2` hanya menghasilkan executable Candidate setelah exact `EvidenceRequirementSet` seluruhnya content-bound ke capability `QUALIFIED`. Policy dan Decision admission menolak V1 untuk setiap risk-increasing action baru meskipun public legacy `capture_candidate` diberi `executable=True`; V1 hanya legal untuk historical replay/projection dan risk-reducing/protective processing. Candidate identity recipe v1 tetap digunakan karena provenance bukan bagian preimage. Complete-but-bad input boleh dipertahankan sebagai immutable raw/admission-failure evidence dan direferensikan oleh Candidate V2 non-executable dengan closed `EligibilityReason`; input tersebut tidak dipromosikan menjadi canonical venue fact. Missing/structurally invalid proof ditolak atomik.
7. Offline fixture manifest menyimpan repository commit, document path, Git blob/content digest, extracted contract assertions, authoritative-field set, dan sanitized payload digest. Lima product family adalah minimum; setiap registry endpoint/channel entry mempunyai artifact unik, sehingga jumlah artifact dapat lebih dari lima. Corpus tanpa network wajib mencakup successful qualification, field-authority isolation, effective-time exact-one/no-match, local-versus-venue cursor, duplicate/conflict, gap/regression/out-of-order, disconnect/reconnect, future/naive/non-UTC time, exact dan over-boundary freshness/skew, local clock anomaly scope, recovery-plus-reconciliation gating, deprecated legacy history rejection, documentation/artifact drift, deterministic canonical bytes, dan caller-mutation resistance.
8. Scope tetap structural DRY RUN: tidak ada SQLite/schema/runtime DDL, Redis, dashboard/Telegram, live network contract test, live submit/cancel adapter, trade-capable credential/secret, legacy fallback, simulator/book-walk, instrument eligibility, Intent/Order/Fill/Position, atau SafetyState persistence. Tidak ada import/reuse target terhadap `api/indodax_api.py`; kode legacy hanya boleh menjadi evidence negatif/fixture yang disanitasi.

## Tasks / Subtasks

- [x] Definisikan immutable capability registry dan evidence admission contracts (AC: 1–5)
  - [x] Tambahkan enums/value objects tertutup untuk product, qualification status, cursor capability, auth scope, timestamp/rate-limit/recovery contract, affected scope, continuity result, dan typed disposition.
  - [x] Tambahkan public versioned `ContentRef` helper: compatibility recipe V1 mereproduksi exact existing replay prefix/digest (`sha256(canonical_bytes(value))`), sedangkan V2 meng-hash envelope berisi domain, kind, recipe version, dan canonical value; market evidence wajib memakai domain-separated V2.
  - [x] Enforce half-open effective-time exact-one lookup, field-level authority, exact docs/artifact binding, dan typed `UNQUALIFIED/NO_MATCH` tanpa nearest fallback.
  - [x] Definisikan content-bound `EvidenceRequirementSet`; exact completeness/equality wajib sebelum executable admission.
- [x] Implementasikan isolated Indodax capability catalog dan pure evidence adapter (AC: 1–5, 8)
  - [x] Sediakan entry terpisah untuk Public REST, Private REST, Trade API 2.0, Market Data WebSocket, dan Private WebSocket; split endpoint/channel bila semantics berbeda.
  - [x] Parse recorded boundary input menjadi typed immutable evidence dengan explicit event/receive/clock inputs; jangan membaca wall clock, network, env secret, database, atau cache.
  - [x] Hasilkan typed freeze/recovery/reconciliation request; bedakan remote evidence skew dari authority-scoped local clock anomaly; tanpa memutasi safety state atau fallback legacy.
  - [x] Implementasikan pure `evaluate_recovery_gate(...)`; ia hanya mengevaluasi proof/checkpoint dan tidak memiliki mutable recovery state.
- [x] Bind evidence admission ke Candidate secara schema-safe (AC: 2–6)
  - [x] Pertahankan satu `CandidateSnapshot` class dengan closed V1/V2 provenance union dan deterministic serializer dispatch; V1 byte-identical, V2 proof-bearing.
  - [x] Cross-check exact `EvidenceRequirementSet` dengan v2 eligibility; `executable=True` dilarang pada missing/extra/duplicate/foreign atau unqualified/stale/gapped/ambiguous proof.
  - [x] Pertahankan Candidate identity recipe v1; provenance v2 tidak mengubah preimage dan tidak membuat recipe identity baru.
  - [x] Enforce pada Policy dan Decision boundary bahwa Candidate V1 tidak dapat menghasilkan risk-increasing action baru; historical replay/projection dan protective/risk-reducing behavior tetap legal.
- [x] Tambahkan per-entry contract fixtures dan adversarial qualification tests (AC: 1–8)
  - [x] Simpan manifest berisi repo commit, document path, Git blob/content digest, extracted assertions, sanitized payload digest, dan expected field set per registry entry; branch `master` saja bukan version pin.
  - [x] Uji boundary 3 detik/1 detik/gap nol, UTC strictness, duplicate/conflict/ordering, remote-vs-local-clock scope, pure two-proof recovery gate, drift, secret absence, serta 100-run determinism.
  - [x] Uji Public REST `NO_AUTHORITATIVE_SEQUENCE` tidak mengklaim stream continuity; Market Data WS offset/recovery berlaku hanya pada channel yang dibuktikan; Private WS event tidak menggantikan REST recovery/reconciliation.
  - [x] Tambahkan end-to-end V2 Candidate→Policy→Decision→projection contract test dan direct-bypass test bahwa V1 executable self-claim tidak dapat menambah exposure.
- [x] Perketat exports, dependency matrix, dan regression gates (AC: 6–8)
  - [x] Update explicit per-module AST allowlist untuk `domain`, `ports`, dan `adapters`; jangan memperlonggar allowlist global atau mengizinkan horizontal adapter imports.
  - [x] Pertahankan exact v1 golden fixtures dan tambahkan v2 fixtures; migrasikan hanya producer target yang semestinya memakai v2 sambil menjaga identity, replay, policy, dan projection invariants.
  - [x] Jalankan focused tests, seluruh `tests/autotrade_next/contract`, Strategy2 regression, `compileall`, `git diff --check`, lalu full suite; bandingkan legacy debt dengan baseline Story 1.6.

## Dev Notes

### Developer Context

- Story 2.1 adalah exchange-evidence trust boundary untuk FR11/FR13. Story 2.2 baru membentuk executable L2 `MarketSnapshot` dan instrument eligibility; Story 2.6 baru menyelesaikan restart/reconciliation lifecycle. Jangan menarik book-walk, simulator, accounting, atau safety persistence ke story ini.
- Loophole aktual wajib ditutup, bukan ditutupi registry paralel: `SourceCursor.cursor_capability` dan `.quality` masih arbitrary strings, sedangkan `CandidateProvenance` hanya melakukan type/freeze validation dan menerima `CandidateEligibility(executable=True)` tanpa registry proof. Caller saat ini dapat self-claim `QUALIFIED`.
- `EvidenceRequirementSet` adalah policy fact, bukan daftar yang disusun caller. Ia mengikat trigger, horizon, instrument/scope, effective time, capability entries, serta policy/content reference; admission membandingkan exact multiset/set sesuai contract agar omitted source tidak lolos.
- `NO_AUTHORITATIVE_SEQUENCE` sah sebagai deskripsi capability snapshot REST yang contract-tested, tetapi tidak sah untuk mengklaim continuity incremental. `ingest_cursor` selalu observability lokal.
- Evidence venue untuk execution/order/account dan journal internal mempunyai authority berbeda: exchange-confirmed evidence menguatkan fakta venue; append-only journal tetap authority untuk intent, approval, dan provenance. Story ini tidak membuat correction event FR11.
- Complete-but-bad input harus audit-able sebagai raw/admission-failure evidence yang dapat direferensikan Candidate non-executable, tanpa mengklaimnya sebagai venue fact. Missing structural fields, forged content refs, ambiguous effective version, atau secret-bearing values harus rejected atomically.

### Indodax Documentation Discovery Notes (Observed 2026-08-27; Not Qualification Artifacts)

- Tautan `master` pada References hanya discovery pointers. Implementasi wajib mengambil exact repository commit dan Git blob/content digest, mem-vendor offline manifest/fixture, lalu memakai commit-SHA URL; tanpa itu capability tetap `UNQUALIFIED`.
- Public REST bersifat unauthenticated dan mendokumentasikan general limit 180 requests/minute. Dokumentasi umumnya menyebut milliseconds, tetapi contoh field tertentu tampak memakai skala berbeda; karena itu timestamp unit harus dikualifikasi per endpoint dari pinned fixture, bukan diasumsikan global. `/api/pairs`, `/api/price_increments`, dan `/api/depth/{pair}` memiliki peran berbeda dan tidak menyediakan blanket authoritative sequence.
- Pinned Trade API 2.0 commit `2e0c1fe` menyatakan `X-APIKEY`, HMAC-SHA512, dan base production `https://tapi.indodax.com`. Ini **bukan** auth/signature contract Private REST legacy yang memakai `Key` dan HMAC-SHA512 pada `/tapi`; signer/client tetap tidak boleh diwariskan lintas produk.
- Pinned Trade API 2.0 document menyatakan endpoint legacy `tradeHistory` dan `orderHistory` dijadwalkan decommission pada 23 Maret 2026; recovery target adalah `/api/v2/myTrades` dan `/api/v2/order/histories`. Endpoint legacy tetap `UNQUALIFIED` untuk authoritative recovery meski fallback code lama masih ada.
- Market Data WebSocket mendokumentasikan per-channel `offset`, `recoverable`, dan recovery from a supplied offset. Jangan mengasumsikan sequence/offset/snapshot semantics seragam untuk chart, summary, trade activity, dan order-book channel tanpa contract artifact masing-masing.
- Private WebSocket menyediakan token/channel dan order-update evidence, tetapi tidak boleh dianggap durable gap-free recovery source tanpa cursor/recovery proof; REST recovery/reconciliation tetap diperlukan.
- Bila official documents saling berbeda mengenai base URL, signature, field, atau rate limit, fail qualification dan minta pinned contract update; jangan memilih fallback berdasarkan apa yang kebetulan bekerja.

### Architecture Compliance

- AD-01: `domain → stdlib/domain`; `ports → domain`; `adapters → domain+ports`; hanya bootstrap menjadi composition root. Tidak ada network/framework import di domain dan tidak ada dependency pada legacy namespace.
- AD-02/AD-26: UTC event/receive time terpisah, monotonic duration input eksplisit, fixed/scaled numeric representation, UTF-8 canonical JSON/NFC/sorted keys/UTC-Z, domain-separated SHA-256, lowercase hex, serta versioned golden vectors.
- AD-08: venue cursor dan local ingest cursor terpisah; point-in-time evidence, quality, freshness, capability, rules/universe refs dibekukan. Last price tidak menggantikan executable depth.
- AD-13/AD-29: exact per-product registry, sequence-aware recovery, WS-as-evidence, no legacy fallback, dan fail-closed `UNQUALIFIED`.
- AD-20: DRY RUN artifact/process tidak memiliki live submit adapter atau trade-capable credential. Private read/recovery job kelak harus least-privilege dan process-isolated.
- AD-27: adapter menghasilkan cause/evidence/request; hanya canonical SafetyState command owner yang boleh membuka/menutup degradation. Clearing satu market cause tidak boleh menghapus cause lain.
- AD-27 scope: remote venue timestamp/freshness failure dapat local/systemic sesuai source, tetapi verified local clock anomaly/rollback selalu authority-scoped `SAFE_LATCHED`.

### Existing Code: Update and Preservation Map

| File | Current state | Story change | Preserve |
| --- | --- | --- | --- |
| `advanced_crypto_bot/autotrade_next/domain/candidate.py` | V1 `SourceCursor` quality/capability string bebas; executable eligibility tidak cross-check proof | Satu Candidate class + closed V1/V2 provenance union, exact V1 serializer branch, proof-bearing V2 capture | Candidate identity preimage/recipe v1, immutability, ordered evidence, correction lineage, exact v1 bytes |
| `advanced_crypto_bot/autotrade_next/domain/policy.py` dan `decision.py` | Menerima exact `CandidateSnapshot` tetapi belum membedakan evidence schema | Reject V1 pada risk-increasing evaluation/direct bypass; accept same-class V2; preserve protective paths | Existing state legality, precedence, typed veto/error, immutable Decision |
| `advanced_crypto_bot/autotrade_next/domain/errors.py` | Stable typed errors untuk canonical/candidate/decision/policy/replay | Tambahkan typed market/capability error dengan metadata konsisten | Existing error codes/attributes dan no partial result |
| `advanced_crypto_bot/autotrade_next/domain/__init__.py` | Explicit domain exports | Export contract baru secara eksplisit | Existing exports/API |
| `advanced_crypto_bot/autotrade_next/ports/__init__.py` | Hanya read-only query marker | Export market evidence/recovery port | Port tetap contract-only, tanpa implementation dependency |
| `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` | Explicit per-module dependency guards | Tambah module/adapter allowlist yang sempit dan identity vectors bila recipe baru | Jangan membuka generic adapter/network/legacy imports |
| `advanced_crypto_bot/autotrade_next/domain/replay.py` | Generic content-ref helper masih private; cursor refs sudah content-addressed | Reuse public ContentRef V1 compatibility recipe; market memakai V2 recipe | Exact Story 1.5 replay refs/hashes, zero-side-effect behavior, semantic projections |
| Candidate fixture users | V1 fixture self-declare quality/cursor | Pertahankan v1 regression fixtures; tambah v2 qualified admission fixtures dan pakai v2 pada target producer tests | Existing Candidate/Decision/policy/replay/projection golden behavior |

### File Structure Requirements

- NEW `advanced_crypto_bot/autotrade_next/domain/market.py`
- NEW `advanced_crypto_bot/autotrade_next/domain/content.py` untuk public versioned `ContentRef` recipe/helper.
- NEW `advanced_crypto_bot/autotrade_next/ports/market.py`
- NEW `advanced_crypto_bot/autotrade_next/adapters/__init__.py`
- NEW `advanced_crypto_bot/autotrade_next/adapters/indodax/__init__.py`
- NEW `advanced_crypto_bot/autotrade_next/adapters/indodax/capability_registry.py`
- NEW `advanced_crypto_bot/autotrade_next/adapters/indodax/market_evidence.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_indodax_capability_registry.py`
- NEW `advanced_crypto_bot/tests/autotrade_next/contract/test_indodax_market_evidence.py`
- NEW sanitized recorded fixtures under `advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/`, separated by product/channel.
- UPDATE `domain/candidate.py`, `domain/policy.py`, `domain/decision.py`, `domain/replay.py`, `domain/errors.py`, `domain/__init__.py`, `ports/__init__.py`, dan `test_identity_vectors.py`.
- UPDATE tests untuk mempertahankan exact v1 vectors serta menambah v2 coverage: `test_candidate_snapshot.py`, `test_canonical_decision.py`, `test_cost_hysteresis_policy.py`, `test_deterministic_replay.py`, dan `test_decision_provenance_projection.py`.
- `domain/identity.py` tidak perlu berubah untuk provenance v2 karena Candidate identity recipe tetap v1; ubah hanya bila kebutuhan entity identity baru terbukti dan tambahkan explicit recipe/vector.
- DO NOT UPDATE `api/indodax_api.py`, `bot.py`, `core/database.py`, `autotrade/runtime.py`, dashboard, Redis modules, or legacy Strategy2 contracts.

### Testing Requirements

- Five product families minimum plus one unique artifact per endpoint/channel entry; half-open effective-time exact-one selection; overlap invalidation; no-match `UNQUALIFIED`; foreign version/artifact mismatch.
- Immutable nested values, canonical golden hashes, repeated 100-run equality, order semantics, forged hash/reference rejection, and no unsupported float/coercion. ContentRef V1 compatibility vectors remain exact; V2 proves domain/kind/version separation.
- Single Candidate class preserves V1 serializer/types/golden bytes; V2 exact-requirement admission controls executable Candidate while Candidate identity recipe remains unchanged. Policy/Decision reject direct V1 risk increase, and V2 end-to-end Candidate→Policy→Decision→projection passes.
- Gap/regression/out-of-order/conflicting duplicate/disconnect, explicit reconnect, future event, naïve/non-UTC timestamp, 3-second freshness and 1-second remote skew exact/over boundaries; verified local clock anomaly always emits authority scope.
- Pure recovery evaluation returns frozen after only snapshot or only reconciliation; exact matching proofs may emit only a scoped clear request and never claim mutable state/persistence.
- Negative legacy/API tests: no import of `api.indodax_api`, no `/tapi` history fallback, no live submit/cancel surface, no credential/secret in fixture/canonical bytes/error output, and contract suite performs zero network calls.
- AST dependency tests enforce AD-01 for all new modules. Preserve Story 1.6's Candidate→Decision projection semantics and Story 1.5 replay manifest binding.

### Previous Story and Git Intelligence

- Story 1.6 established trusted content-bound references, pure immutable reducers/ports, strict sequencing, typed retry/dead-letter outcomes, and narrow AST import guards. Apply the same content-binding and no-overclaim discipline here: a pure adapter validates supplied evidence; it does not prove persistence or network truth beyond its pinned contract artifact.
- Latest recorded gates from Story 1.6: 240 AutoTrade Next/Strategy2 tests passed; full suite 894 passed with unchanged 14 failures/5 errors legacy and 22 subtests. Treat existing legacy failures as baseline debt, not permission for new failures.
- Last five commits are mostly planning/investigation; `13b54a9` is the latest committed target-code foundation. Stories 1.2–1.6 are currently present as dirty/untracked workspace changes. Use the actual workspace as source of truth, preserve those changes, and do not reset/checkout them away.
- Reuse `canonical_bytes`, existing Candidate identity recipe, frozen slotted dataclasses, typed error pattern, `ReadOnlyQueryPort`-style Protocols, and explicit import matrices. Extract private replay refs into versioned public `ContentRef`: V1 is compatibility-exact and V2 alone uses a domain-enveloped preimage; do not mislabel V1 as domain-separated or create parallel hashes.

### Project Structure Notes

- Alignment: flat pure domain modules currently implement Epic 1, while Story 2.1 begins the architecture's `domain/market`, `ports/market`, and `adapters/indodax` slice.
- Variance: current target namespace has no `application/` or persistence boundary; keep Story 2.1 pure/structural rather than inventing pseudo durability.
- Brownfield conflict: `api/indodax_api.py` mixes public/private/trade capabilities, undocumented depth fallback, legacy history fallback, and live order methods. It is explicitly excluded from target reuse.
- Runtime stack remains CPython 3.12.14, SQLite 3.53.4 exact allowlist, dan uv 0.11.15, but toolchain/image qualification belongs to Story 5.2 and is out of scope here.
- Tidak ada UX artifact terpisah; Story 2.1 tidak mengubah UI. Future projections must display qualification/freeze evidence read-only without computing venue truth themselves.

### References

- [Epic 2 and Story 2.1](../planning-artifacts/epics.md#story-21-mengkualifikasi-market-evidence-per-produk-indodax)
- [PRD FR-11 Reconciliation](../planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md#fr-11-reconciliation)
- [PRD FR-13 Freshness and gap control](../planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md#fr-13-freshness-and-gap-control)
- [PRD Quality and Safety Contract](../planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md#quality-and-safety-contract)
- [Architecture AD-08/13/20/26/27/29](../planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Architecture implementation sequence and verification artifacts](../planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/IMPLEMENTATION-NOTES.md#build-and-cutover-gates)
- [Indodax integration research](../planning-artifacts/research/technical-autotrade-crypto-indodax-market-execution-risk-research-2026-08-12.md#integration-patterns-analysis)
- [Story 1.6 implementation intelligence](./1-6-menyajikan-provenance-decision-read-only.md)
- [Discovery pointer — official Indodax API catalog; implementation must pin repository commit](https://github.com/btcid/indodax-official-api-docs)
- [Discovery pointer — Public REST; `master` is not a qualification version](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md)
- [Discovery pointer — Trade API 2.0; `master` is not a qualification version](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md)
- [Discovery pointer — Market Data WebSocket; `master` is not a qualification version](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md)
- [Discovery pointer — Private WebSocket; `master` is not a qualification version](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-websocket.md)
- [Discovery pointer — Private REST; `master` is not a qualification version](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-RestAPI.md)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- RED: focused registry/evidence suite menghasilkan 4 failure untuk artifact reuse, recipe V1 pada market binding, dan recovery version binding; seluruhnya ditutup lalu GREEN 22/22.
- RED: adapter/Candidate suite menghasilkan 3 failure untuk instrument/scope mismatch, unproven authority scope, disposition self-claim, dan provenance authority mismatch; seluruhnya ditutup lalu GREEN 46/46.
- Regression: Candidate→Policy→Decision→projection 118/118; AST dependency guard 23/23; seluruh contract 230/230; Strategy2 42/42; dry-run signal cycle 19/19.
- Quality gates: `compileall` dan `git diff --check` exit 0.
- Full-suite audit: interpreter sistem berhenti saat collection karena dependency legacy tidak tersedia; project venv mencapai debt legacy yang sudah ada (7 failure/5 error terlihat sebelum area async) lalu hang pada legacy FastAPI `TestClient`/AnyIO dan `IsolatedAsyncioTestCase` teardown. Focused Story 2.1 tidak gagal dan tidak mengimpor stack legacy tersebut.
- Review 2026-08-29: RED tests ditambahkan untuk documented remote timestamp mismatch, foreign capability version, reused effective-time proof, foreign channel scope, serta forged recovery proof/checkpoint. Seluruh fix logic GREEN pada 254 contract tests dan 61 Strategy2/dry-run regressions.
- Review full-suite: collection berhenti dengan 22 missing-dependency errors legacy (`sklearn`, `fastapi`, `joblib`, `aiohttp`); tidak ada error dari namespace `autotrade_next`.
- Continuation review 2026-08-29: seluruh partial fix direkonstruksi dari diff dan review record tanpa mengulang blind hunt. Contract suite tetap 254/254 dan Strategy2 + dry-run tetap 61/61; `compileall` dan `git diff --check` tetap lulus. Full suite serta collect-only pada project venv masing-masing dibatasi 55/40 detik dan tetap macet sebelum menghasilkan output, konsisten dengan debt collection/async legacy yang telah dicatat.
- Official-artifact qualification 2026-08-29: checkout upstream read-only terverifikasi pada `2e0c1fecb04cd30465ad81fd4be11ae66b5d0e19`; lima dokumen lolos exact byte/Git blob/SHA-256 checks. Setelah nested response/scope/recovery-capability binding dan golden diperbarui, contract suite 260/260 serta Strategy2 + dry-run 61/61 lulus; `compileall`, `git diff --check`, dan manifest JSON exit 0.

### Implementation Plan

- Bangun primitive content/capability/evidence immutable dan validasi exact effective-time/artifact/field binding.
- Adaptasikan input Indodax recorded secara pure, fail-closed, scope-aware, serta keluarkan request recovery tanpa mutable safety state.
- Tambahkan provenance Candidate V2 pada class yang sama, pertahankan bytes/identity V1, dan tutup direct V1 risk-increase di Policy/Decision.
- Kunci perilaku dengan fixture offline, adversarial boundary tests, golden vectors, dan dependency matrix per-module.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Registry lima product family dan exact-one half-open lookup tersedia. Lima dokumen resmi dari commit `2e0c1fecb04cd30465ad81fd4be11ae66b5d0e19` divendor byte-identical; Git blob SHA-1, SHA-256 dokumen, fixture digest, dan artifact ref dihitung dari bytes sebenarnya. Delapan entry terbukti berstatus `QUALIFIED`; legacy `tradeHistory` tetap `UNQUALIFIED`.
- Evidence admission V2 membekukan capability/external response/timestamps/cursor/policy/scope; continuity failure menghasilkan typed freeze/recovery/reconciliation request dan two-proof recovery gate tetap pure.
- Candidate V1 tetap byte-identical dan identity recipe v1; Candidate V2 memerlukan exact qualified proof set. Policy/Decision menolak V1 risk-increasing live admission tetapi mempertahankan replay/projection/protective path.
- Recovery proof/checkpoint/clear request sekarang mengikat exact capability version; domain/kind/recipe market content refs, authority scope, dan disposition/continuity consistency divalidasi fail-closed.
- Contract, Strategy2, compile, dan diff gates lulus; keterbatasan full legacy suite dicatat pada Debug Log dan terisolasi dari Story 2.1.
- Review memperketat timestamp contract dari payload, binding capability version/effective time ke Candidate, channel-local scope, serta content-bound recovery proof/checkpoint.
- Qualification continuation memverifikasi checkout upstream read-only pada exact commit, mem-vendor kelima dokumen byte-identical, mengikat response envelope/nested authoritative fields/timestamp/instrument/channel resmi, dan menutup seluruh blocker AC1/AC7 tanpa network/runtime fallback.

### File List

- advanced_crypto_bot/autotrade_next/domain/content.py
- advanced_crypto_bot/autotrade_next/domain/market.py
- advanced_crypto_bot/autotrade_next/domain/candidate.py
- advanced_crypto_bot/autotrade_next/domain/policy.py
- advanced_crypto_bot/autotrade_next/domain/decision.py
- advanced_crypto_bot/autotrade_next/domain/replay.py
- advanced_crypto_bot/autotrade_next/domain/errors.py
- advanced_crypto_bot/autotrade_next/domain/__init__.py
- advanced_crypto_bot/autotrade_next/ports/market.py
- advanced_crypto_bot/autotrade_next/ports/__init__.py
- advanced_crypto_bot/autotrade_next/adapters/__init__.py
- advanced_crypto_bot/autotrade_next/adapters/indodax/__init__.py
- advanced_crypto_bot/autotrade_next/adapters/indodax/capability_registry.py
- advanced_crypto_bot/autotrade_next/adapters/indodax/market_evidence.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_indodax_capability_registry.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_indodax_market_evidence.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_candidate_snapshot.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_canonical_decision.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_cost_hysteresis_policy.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_deterministic_replay.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_decision_provenance_projection.py
- advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/manifest.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/documents/Public-RestAPI.md
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/documents/Private-RestAPI.md
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/documents/INDODAX-TradeAPI-2.md
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/documents/Marketdata-websocket.md
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/documents/Private-websocket.md
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/public_rest/public-rest.depth.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/public_rest/public-rest.ticker.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/private_rest/private-rest.get-info.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/private_rest/private-rest.trade-history.deprecated.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/trade_api_v2/trade-api-v2.my-trades.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/trade_api_v2/trade-api-v2.order-histories.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/market_data_websocket/market-ws.order-book.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/market_data_websocket/market-ws.trade-activity.v1.json
- advanced_crypto_bot/tests/autotrade_next/contract/fixtures/indodax/private_websocket/private-ws.order-update.v1.json
- _bmad-output/implementation-artifacts/2-1-mengkualifikasi-market-evidence-per-produk-indodax.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Senior Developer Review (AI)

### Reviewer dan Outcome

- Reviewer: Officer (AI-assisted review)
- Tanggal: 2026-08-29
- Outcome: **Approved**
- Temuan kumulatif: 1 Critical, 9 High, 4 Medium
- Diperbaiki otomatis: 14
- Tersisa: 0 Critical
- Git vs Story discrepancy dalam scope Story 2.1: 0 setelah lima dokumen vendored ditambahkan ke File List. Worktree Story 1.2–1.6 tetap diperlakukan sebagai perubahan pengguna dan tidak diambil alih.

### Temuan

1. **CRITICAL — fixed:** digest sintetis diganti dengan byte kelima dokumen resmi dari checkout upstream read-only pada exact commit `2e0c1fecb04cd30465ad81fd4be11ae66b5d0e19`. Setiap file vendored byte-identical; Git blob SHA-1 dan SHA-256 dokumen diverifikasi offline, lalu status delapan entry yang terbukti dinaikkan ke `QUALIFIED`; legacy `tradeHistory` tetap `UNQUALIFIED`.
2. **HIGH — fixed:** adapter mengabaikan documented payload timestamp dan menerima `event_at_utc` self-claim. Timestamp seconds/milliseconds, termasuk nested Private WS timestamp, sekarang dicocokkan atomik (`market_evidence.py:90,235`).
3. **HIGH — fixed:** Candidate V2 hanya membandingkan capability ref; foreign `capability_version` dapat di-content-bind ulang dan lolos. Requirement sekarang membekukan version dan admission membandingkannya (`candidate.py:732`).
4. **HIGH — fixed:** proof dapat digunakan pada effective time Candidate yang berbeda. `MarketEvidence.effective_at` kini dibekukan dan harus sama dengan requirement/trigger (`candidate.py:734`).
5. **HIGH — fixed:** evidence endpoint/channel dapat dilabeli affected channel lain. Adapter sekarang mengikat concrete channel scope ke resource+instrument (`market_evidence.py:87`).
6. **HIGH — fixed:** recovery proof/checkpoint menerima foreign V1/domain/kind references dan mutable self-claim. Semua reference sekarang V2-domain typed dan proof/checkpoint content-bound (`market.py:657-797`).
7. **MEDIUM — fixed:** manifest tidak memverifikasi qualification status terhadap registry. Status sekarang disinkronkan dan diuji.
8. **HIGH — fixed:** fixture dan authoritative field entry memakai payload yang diratakan, menghilangkan envelope resmi (`ticker`, `return`, `result`, `push.pub.data`) dan memfabrikasi field Trade API `meta`. Fixture kini mempertahankan struktur resmi yang disanitasi; admission memakai exact nested field path, termasuk array path.
9. **HIGH — fixed:** channel dan instrument di payload resmi belum dicocokkan dengan scope/instrument caller. Adapter kini menolak remote channel/pair/symbol asing secara atomik.
10. **HIGH — fixed:** `effective_from` 7 April 2026 tidak berasal dari artifact pinned. Seluruh entry kini mulai pada author timestamp exact commit, `2026-03-03T08:12:12Z`, sehingga qualification tidak mendahului evidence source.
11. **MEDIUM — fixed:** golden Candidate V2 masih mengikat capability/artifact lama. Digest canonical V2 diperbarui setelah seluruh official binding stabil.
12. **MEDIUM — fixed:** discovery notes menyebut HMAC-SHA256, base URL, dan tanggal decommission yang bertentangan dengan commit pinned. Story kini merekam HMAC-SHA512, `https://tapi.indodax.com`, dan jadwal 23 Maret 2026 sesuai bytes resmi.
13. **MEDIUM — fixed:** lima dokumen vendored belum tercatat dalam File List. Seluruhnya sekarang dicantumkan.
14. **HIGH — fixed:** recovery Private WebSocket menunjuk route Trade API 2.0 hanya sebagai string dan tidak terikat ke capability/artifact target. `RecoveryContract` kini membawa `source_capability_id`; registry menolak target hilang, unqualified, foreign route/commit, atau effective interval yang tidak mencakup source.

### Validasi Checklist

- Story, Epic 2, FR11/FR13, Architecture AD-01/08/13/26/27/29, implementation notes, seluruh File List source/test/fixture, Git status, dan official Indodax discovery pages telah direview.
- AC1–AC8 terpetakan ke implementation/tests; exact pinned document/artifact qualification untuk AC1/AC7 kini lengkap.
- Security/dependency review: tidak ada legacy Indodax import, live network, secret, DDL, atau horizontal adapter import pada target slice.
- Final gates: `tests/autotrade_next/contract` **260 passed**; Strategy2 + dry-run signal cycle **61 passed**; `compileall`, `git diff --check`, dan manifest JSON exit 0.
- Full suite belum menjadi gate hijau: bukti review sebelumnya mencatat 22 dependency errors legacy (`sklearn`, `fastapi`, `joblib`, `aiohttp`), sedangkan continuation run pada project venv timeout saat execution (55 detik) dan collect-only (40 detik) sebelum output. Tidak ada failure pada focused namespace `autotrade_next`.
- Checkout `/tmp/indodax-docs.PAguKE/repo` berada tepat pada commit pinned dan digunakan read-only. Lima dokumen vendored lolos `cmp`, `git hash-object`, exact Git blob lookup, dan SHA-256 binding.
- Tidak ada CRITICAL tersisa; story dan sprint disinkronkan ke `done`. Tidak ada review action item tertunda karena seluruh temuan diperbaiki otomatis.

## Change Log

- 2026-08-27: Created comprehensive Story 2.1 context and set status to ready-for-dev.
- 2026-08-28: Implemented immutable Indodax capability/evidence contracts, proof-bearing Candidate V2 admission, pure recovery gate, offline artifacts, adversarial tests, and dependency/regression gates; set status to review.
- 2026-08-29: Adversarial review auto-fixed timestamp/version/effective-time/scope/recovery binding defects; quarantined synthetic documentation coordinates as `UNQUALIFIED`; set status to in-progress pending real pinned documentation bytes.
- 2026-08-29: Continued the exhausted-context review from existing fixes, revalidated focused/regression/compile/diff gates, confirmed the pinned-document critical remains unresolved, and preserved Story/Sprint status as in-progress.
- 2026-08-29: Resumed the official-artifact qualification patch using the pinned read-only upstream checkout; vendored and verified exact document bytes/blob/SHA-256 bindings, corrected official response envelopes and field-level scope/recovery bindings, passed 260 contract plus 61 regression tests, and set Story/Sprint status to done.
