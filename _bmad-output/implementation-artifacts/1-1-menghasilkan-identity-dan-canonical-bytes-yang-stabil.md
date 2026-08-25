---
baseline_commit: a317cac8dca9a03c9497fe40dcd6d3f76af0015e
---

# Story 1.1: Menghasilkan identity dan canonical bytes yang stabil

Status: done

## Story

As a Officer,
I want setiap entity dan event memiliki encoding serta identity deterministik,
so that producer, persistence, simulator, dan replay tidak dapat mengartikan fakta yang sama secara berbeda.

## Acceptance Criteria

1. Given canonical encoding profile AD-26 dan golden fixtures lintas numeric/time/Unicode/null, when Candidate, Decision, Intent, event envelope, dan client-order identity dibentuk berulang kali, then canonical bytes dan lowercase SHA-256 identity selalu identik.
2. Unsupported float/type, non-string mapping key, non-NFC/lone-surrogate string, scale ambiguity, naive/non-UTC timestamp, absent/null ambiguity, atau recipe-version mismatch ditolak dengan typed error dan tidak menghasilkan partial result.
3. Canonical profile adalah versioned custom profile `atr-json-v1`, bukan klaim kompatibilitas RFC 8785: UTF-8 tanpa BOM, Unicode NFC, map key ordinal sorting, compact JSON, explicit null, enum string, UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`, dan domain numeric berupa scaled integer representation.
4. Setiap deterministic identity memakai recipe registry yang mengunci domain separator, recipe version, field projection, canonical encoding version, SHA-256, dan lowercase hex. Perubahan recipe menambah version baru, tidak menulis ulang ID lama, dan baru diterima setelah compatibility suite serta seluruh golden vectors lulus.
5. Golden vectors shared oleh encoding dan identity tests mencakup equivalent map ordering, composed/decomposed Unicode, timestamp boundary, negative/zero scaled integer, list ordering, absent versus null, enum, unsupported binary float, NaN/Infinity, bool-versus-int, non-string key, lone surrogate, dan field/domain separator collision.
6. Existing `autotrade/contracts.py` dan `autotrade/strategy2/*` tidak dimodifikasi atau dijadikan dependency target; konsep/fixtures boleh dipakai sebagai brownfield regression evidence, sedangkan target baru hidup di namespace `autotrade_next`.

## Tasks / Subtasks

- [x] Buat strict canonical encoding kernel pada `autotrade_next/domain/encoding.py` (AC: 1–3, 5)
  - [x] Definisikan typed `CanonicalEncodingError` dengan stable `code` dan structural `path` untuk unsupported type, key, Unicode, numeric, timestamp, dan version error; exception tidak boleh mengembalikan partial bytes.
  - [x] Normalisasi recursively hanya value yang diizinkan: null, bool, int non-bool, NFC string, enum string, UTC datetime, explicit scaled value, list/tuple, dan mapping ber-key string.
  - [x] Serialisasi dengan `ensure_ascii=False`, `allow_nan=False`, `sort_keys=True`, `separators=(",", ":")`, UTF-8, tanpa `default=str`.
- [x] Buat explicit scaled-integer value contract tanpa binary float pada `autotrade_next/domain/numeric.py` (AC: 2–3, 5)
  - [x] Simpan `units` integer dan `scale` integer nonnegative; canonical JSON tidak menerima raw `Decimal` atau float yang scale-nya implisit.
  - [x] Tolak bool sebagai integer, scale invalid, dan konstruk yang kehilangan presisi.
- [x] Buat versioned identity recipe registry pada `autotrade_next/domain/identity.py` (AC: 1, 4–5)
  - [x] Implementasikan domain separation, exact preimage envelope, dan explicit ordered field projection per semantic ID kind sesuai kontrak v1 di bawah.
  - [x] Return structured identity yang memuat kind/recipe version/digest serta canonical key tanpa digest truncation.
- [x] Tambahkan public package exports minimal dan dependency-direction guard (AC: 6)
  - [x] `domain` hanya boleh import stdlib/domain; jangan import database, runtime, exchange, Redis, Telegram, atau legacy `autotrade`.
- [x] Tambahkan golden fixtures dan contract/property tests (AC: 1–6)
  - [x] `tests/autotrade_next/contract/test_canonical_encoding.py` menguji positive vectors dan exact bytes.
  - [x] `tests/autotrade_next/contract/test_identity_vectors.py` menguji determinism, domain/field separation, recipe mismatch, dan no legacy dependency.
  - [x] Positive exact-byte/digest vectors berada langsung di test; unsupported Python-only cases memakai parametrized tests sehingga tidak diperlukan custom fixture decoder.

### Review Findings

- [x] [Review][Patch] Validasi konstruksi publik `DeterministicIdentity` agar state invalid tidak dapat dibuat [advanced_crypto_bot/autotrade_next/domain/identity.py:24]
- [x] [Review][Patch] Paku domain separator, canonical version, dan hash algorithm di setiap recipe v1 immutable [advanced_crypto_bot/autotrade_next/domain/identity.py:18]
- [x] [Review][Patch] Tolak integer di luar batas canonical secara deterministik sebelum serializer runtime [advanced_crypto_bot/autotrade_next/domain/encoding.py:46]
- [x] [Review][Patch] Tolak subclass datetime dan format tahun empat digit secara eksplisit [advanced_crypto_bot/autotrade_next/domain/encoding.py:56]
- [x] [Review][Patch] Hilangkan `repr` terhadap input asing dan perketat type guard version/kind [advanced_crypto_bot/autotrade_next/domain/errors.py:12]
- [x] [Review][Patch] Deteksi cycle dan batas kedalaman value tree dengan stable typed error [advanced_crypto_bot/autotrade_next/domain/encoding.py:36]
- [x] [Review][Patch] Snapshot mapping secara aman serta tolak duplicate/torn mapping pada encoding dan identity projection [advanced_crypto_bot/autotrade_next/domain/encoding.py:65]
- [x] [Review][Patch] Perketat AST dependency guard untuk source rekursif, allowlist sempit, relative boundary, dan dynamic import [advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py:114]
- [x] [Review][Patch] Lengkapi golden corpus untuk semua identity kind dan collision/boundary vectors normatif [advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py:36]
- [x] [Review][Patch] Selaraskan typed domain errors dengan metadata error arsitektur [advanced_crypto_bot/autotrade_next/domain/errors.py:12]

## Dev Notes

### Developer Context

- Ini adalah story pertama target replacement. Deliverable hanya pure domain encoding/identity plus tests; jangan membuat schema, journal, Candidate entity, simulator, adapter, atau migration terlebih dahulu.
- Brownfield `_canonical()` pada `autotrade/contracts.py` memakai `default=str`, float, dan wall-clock fallback; `strategy2/contracts.py` serta repository memakai sorted JSON tetapi tetap menerima float. Keduanya sengaja tidak memenuhi AD-02/AD-26 dan tidak boleh diubah agar regression surface legacy tetap terisolasi.
- Exact bytes adalah public contract. Sediakan satu function yang menerima typed/domain values dan mengembalikan `bytes`; hashing selalu memakai bytes itu tanpa decode/re-encode.
- Python `json.dumps` default menerima NaN dan meng-escape non-ASCII; parameter strict wajib eksplisit. Mapping keys jangan dibiarkan dikonversi otomatis menjadi string.
- RFC 8785 relevan sebagai bukti perlunya deterministic property sorting dan rejection terhadap invalid Unicode/NaN, tetapi profile target berbeda: RFC 8785 tidak melakukan Unicode normalization dan memakai IEEE-754 number serialization; AD-26 mewajibkan NFC plus scaled integers. Jangan menamai implementasi `jcs` atau mengklaim RFC-8785 compliance.
- Validate NFC rather than silently normalizing input. Silent normalization akan membuat dua raw evidences menghasilkan ID sama tanpa record correction. Caller yang ingin normalize harus melakukannya sebelum canonical boundary dan menyimpan source evidence.
- JSON object tidak merepresentasikan absent field. Field projection recipe menentukan field wajib/optional; optional yang hadir sebagai null berbeda dari absent. Identity builder harus memvalidasi projection sebelum encoding.
- Datetime hanya timezone-aware UTC; canonical grammar selalu fixed six fractional digits dan `Z`. Duration/monotonic time bukan datetime payload.

### Normative `atr-json-v1` Contract

- Public boundary adalah `canonical_bytes(value, *, version="atr-json-v1") -> bytes`; version lain ditolak. Serializer memvalidasi seluruh tree sebelum mengembalikan hasil dan tidak menyediakan string-returning/hash shortcut kedua.
- Dispatch type harus eksplisit agar `bool`, `int`, `IntEnum`, dan string-like enum tidak tertukar. Value yang legal: `None`, `bool`, exact non-bool `int`, NFC `str`, `Enum` dengan `.value` berupa `str`, UTC-aware `datetime`, `ScaledInteger`, list/tuple, dan `Mapping[str, ...]`. Raw `float`, `Decimal`, `bytes`, `UUID`, set, naive/non-UTC datetime, non-string enum value, serta type lain ditolak.
- Setiap string, termasuk mapping key dan enum value, harus bebas code point surrogate dan sudah NFC. Jangan normalize diam-diam. Sorting key memakai ascending Unicode scalar ordinal setelah validasi.
- `ScaledInteger(units, scale)` menerima exact `int` non-bool untuk keduanya dan `scale >= 0`; canonical form tepat `{"scale":<scale>,"units":<units>}`. Tidak ada exponent, decimal string, implicit scale, atau zero trimming.
- Enum menjadi string `.value`. Datetime dengan UTC offset nol menjadi string `YYYY-MM-DDTHH:MM:SS.ffffffZ`; offset nonzero ditolak, bukan dikonversi. Tuple dan list sama-sama menjadi JSON array dan urutan dipertahankan.
- Normalized tree diserialisasi tepat dengan `json.dumps(..., ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))`, lalu `.encode("utf-8", errors="strict")`; output tidak membawa BOM atau trailing newline.
- Stable encoding error codes minimum: `UNSUPPORTED_ENCODING_VERSION`, `UNSUPPORTED_TYPE`, `NON_STRING_KEY`, `INVALID_UNICODE`, `UNSUPPORTED_NUMERIC`, `INVALID_SCALE`, `INVALID_TIMESTAMP`, dan `UNSUPPORTED_ENUM`. Error membawa tuple path key/index menuju value gagal tanpa melakukan `str()` pada offending value.
- Integer canonical dibatasi maksimal 2048 bit agar hasil tidak bergantung pada process-wide CPython integer-string limit. Tree dibatasi 64 level; cycle, excessive depth, duplicate/torn mapping, dan integer overflow ditolak dengan stable typed error sebelum JSON serialization.

### Normative Identity Recipe v1

- Identity hash preimage bukan raw string concatenation. Registry memproyeksikan input menjadi canonical envelope tepat `{"canonical_version":"atr-json-v1","domain":"autotrade-next.identity","fields":[[<field-name>,<value>],...],"kind":<kind>,"recipe_version":1}` dan menghitung SHA-256 langsung atas bytes envelope tersebut. `fields` adalah ordered array sesuai table berikut; caller tidak boleh memilih urutan.
- Builder menerima mapping field, menolak missing required field dan unexpected field, serta membedakan optional field absent dari field yang hadir dengan `null`. Stable identity error codes minimum: `UNKNOWN_IDENTITY_KIND`, `UNSUPPORTED_RECIPE_VERSION`, `MISSING_IDENTITY_FIELD`, dan `UNEXPECTED_IDENTITY_FIELD`.
- Registry v1 bersifat immutable dan memuat recipe berikut:

| `kind` | Required fields, in order | Optional field, in order | Rationale |
| --- | --- | --- | --- |
| `candidate` | `instrument_id`, `horizon_id`, `trigger_kind`, `trigger_at_utc`, `scan_trigger_version`, `data_revision` | `parent_position_id` | FR-1 duplicate trigger/revision identity; `trigger_kind` separates closed-bar and protective event triggers. |
| `decision` | `candidate_id`, `policy_version` | — | FR-2 permits exactly one Decision per Candidate and Policy version. |
| `intent` | `decision_id` | — | MVP derives at most one durable Intent from one executable Decision; retries retain the same ID. |
| `event` | `authority_scope_id`, `aggregate_id`, `aggregate_seq`, `event_type`, `schema_version` | — | Canonical generated event identity. Exogenous evidence without upstream ID remains the recorded UUIDv7 case from Architecture and is outside this hash recipe. |
| `client_order` | `authority_scope_id`, `intent_id`, `order_ordinal` | — | Retry of the same order retains identity; a deliberate replacement increments deterministic `order_ordinal`. Writer epoch is intentionally excluded so takeover cannot create a second semantic order. |

- Structured result fields are exact `kind`, integer `recipe_version`, dan 64-character lowercase `digest`. Canonical storage key is exactly `<kind>:v<recipe_version>:<digest>`; do not truncate. Venue-specific client-order length mapping is deferred to the qualified venue adapter and must retain a reversible/collision-checked link to this canonical key.
- Existing recipe entries are never mutated or rebound. Adding v2 means adding a new immutable registry entry and new vectors while v1 lookup and stored keys remain byte-for-byte valid.

### Architecture Compliance

- AD-01: file target hanya di `autotrade_next/domain`; import test mencegah dependency outward.
- AD-02: uang/quantity tidak boleh binary float atau SQLite REAL; story ini memperkenalkan scaled representation saja.
- AD-14: recipe/encoding version dan golden vectors menjadi bagian replay manifest pada story berikutnya.
- AD-26: canonical UTF-8 JSON, NFC, sorted keys, null semantics, enum, UTC grammar, scaled integer, domain-separated SHA-256, lowercase hex, dan version compatibility seluruhnya normatif.
- Structural seed: `autotrade_next/domain/` dan `tests/autotrade_next/contract/`; tidak ada runtime wiring.

### Library / Framework Requirements

- Gunakan Python stdlib saja: `dataclasses`, `datetime`, `enum`, `hashlib.sha256`, `json`, `unicodedata`, `typing`.
- Tidak menambah dependency serialization/hash baru pada story ini.
- Target runtime line CPython 3.12; implementation tidak boleh bergantung pada dict insertion order untuk canonical sorting.

### File Structure Requirements

- NEW `autotrade_next/__init__.py`
- NEW `autotrade_next/domain/__init__.py`
- NEW `autotrade_next/domain/encoding.py`
- NEW `autotrade_next/domain/numeric.py`
- NEW `autotrade_next/domain/identity.py`
- NEW `tests/autotrade_next/contract/test_canonical_encoding.py`
- NEW `tests/autotrade_next/contract/test_identity_vectors.py`
- Optional NEW `tests/autotrade_next/contract/fixtures/canonical-v1.json` bila fixture tetap readable tanpa custom decoder.
- Jangan update `autotrade/contracts.py`, `autotrade/strategy2/contracts.py`, `autotrade/strategy2/repository.py`, atau `core/database.py`.

### Testing Requirements

- Semua positive vector membandingkan exact bytes atau UTF-8 hex, bukan hanya parsed JSON equality. Fixture menyatakan profile/recipe version dan expected value literal; test-only fixture tags untuk datetime/scaled value tidak menjadi bagian profile production.
- Semua negative vector menegaskan exact typed error code dan path, termasuk raw `Decimal`, float finite/non-finite, bool pada `units/scale`, non-string/NFC-invalid key, lone surrogate, non-string enum, naive/non-UTC datetime, missing/unexpected identity field, serta version/kind mismatch.
- Semua identity vector membandingkan full 64-character SHA-256 hex, exact canonical key, dan preimage bytes. Tambahkan regression bahwa field-order input tidak berpengaruh, tetapi kind, field name, absent/null, recipe version, `order_ordinal`, atau domain separator yang berbeda selalu memisahkan identity.
- Run focused tests baru, existing `tests/test_strategy2_contracts.py`, dan repository-wide import/compile check yang relevan.
- Dependency-direction guard harus memeriksa `ast.Import`/`ast.ImportFrom` seluruh source di `autotrade_next/domain`, bukan substring source. Hanya stdlib dan relative import dalam `autotrade_next.domain` yang legal; `autotrade`, `core`, `api`, `cache`, `bot`, `sqlite3`, database/runtime/exchange/Redis/Telegram, dan third-party module ditolak.
- Test repeated runs dan semantically equivalent key-order inputs minimal 100 iterations tanpa randomness tersembunyi.

### Latest Technical Information

- Python 3.12 `json` hanya deterministic bila sorting/separators/Unicode/NaN policy diberikan eksplisit; non-string keys dapat dikoersi dan `allow_nan` default tidak strict.
- `hashlib.sha256()` tersedia wajib pada Python; gunakan full digest, bukan prefix, untuk canonical identity.
- RFC 8785 menunjukkan canonical JSON diperlukan untuk repeatable cryptographic hashes, tetapi incompatible dengan target NFC/scaled-integer profile; ambil security/interoperability lessons, bukan number/Unicode profile-nya.

### Project Structure Notes

- Repository saat ini belum memiliki `autotrade_next`; story membuat namespace terisolasi tanpa mengubah startup/import legacy.
- Existing tests menggunakan pytest dan beberapa unittest; gunakan pytest parametrization untuk vectors dan tidak membutuhkan database/network.
- Working tree mengandung planning artifacts untracked dari workflow ini; jangan menghapus atau mengubah artifacts di luar story/status/file list.

### References

- [SPEC](/home/officer/advanced_crypto_bot/_bmad-output/specs/spec-autotrade-replacement/SPEC.md)
- [Epic Story 1.1](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/epics.md)
- [Architecture AD-01, AD-02, AD-14, AD-26](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md)
- [Implementation Notes Brownfield Disposition](/home/officer/advanced_crypto_bot/_bmad-output/planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/IMPLEMENTATION-NOTES.md)
- [Python 3.12 json documentation](https://docs.python.org/3.12/library/json.html)
- [Python 3.12 hashlib documentation](https://docs.python.org/3.12/library/hashlib.html)
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- RED: `scripts/test.sh -q tests/autotrade_next/contract/test_canonical_encoding.py tests/autotrade_next/contract/test_identity_vectors.py` → 2 collection errors (`autotrade_next` belum ada), sesuai expected red phase.
- GREEN: focused contract suite → 26 passed; setelah refactor/type/version guard → 27 new tests passed.
- REVIEW GREEN: 10 temuan gabungan diperbaiki; focused canonical/identity contract suite → 46 passed.
- Regression target: new + Strategy 2 contracts/repository → 74 passed; `compileall` dan repository diff hygiene lulus.
- Full repository setelah review: 742 passed, 14 failed, 5 errors. Detached clean baseline `a317cac` sebelumnya mereproduksi exact 14 failures + 5 errors pada failure subset; seluruh failure tetap berasal dari legacy modules dan tidak mengimpor `autotrade_next`.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Implemented strict `atr-json-v1` byte encoding with NFC/surrogate, UTC timestamp, explicit scale, type, key, enum, and version validation.
- Implemented immutable v1 recipes for Candidate, Decision, Intent, Event, and client-order identities using collision-safe canonical envelopes and full lowercase SHA-256 keys.
- Added exact byte/digest vectors, typed negative-path coverage, 100-run determinism checks, absent/null and domain/projection separation, and AST dependency enforcement.
- Confirmed Story 1.1 introduces no legacy runtime imports or modifications. Existing full-suite debt is unchanged from clean baseline.
- Closed all 10 adversarial review patches: public-result validation, fully pinned recipe metadata, deterministic integer/depth bounds, exact datetime dispatch, safe diagnostics, cycle/mapping defenses, strict import guard, complete identity vectors, dan architecture error metadata.

### File List

- `_bmad-output/implementation-artifacts/1-1-menghasilkan-identity-dan-canonical-bytes-yang-stabil.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/autotrade_next/__init__.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/domain/encoding.py`
- `advanced_crypto_bot/autotrade_next/domain/errors.py`
- `advanced_crypto_bot/autotrade_next/domain/identity.py`
- `advanced_crypto_bot/autotrade_next/domain/numeric.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_canonical_encoding.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`

## Change Log

- 2026-08-26: Implemented and tested Story 1.1 canonical encoding and deterministic identity kernel; moved to review.
- 2026-08-26: Applied all adversarial code-review patches, expanded contract suite to 46 tests, and marked Story 1.1 done.
