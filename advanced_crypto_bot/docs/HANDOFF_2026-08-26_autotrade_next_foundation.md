# Handoff — Fondasi Deterministik `autotrade_next`

Tanggal: 2026-08-26

Branch: `kiro/dryrun-activation-dashboard`

Commit lokal: `13b54a9` (`feat: establish deterministic autotrade domain foundation`)

Status remote: belum di-push; branch lokal berada 5 commit di depan origin saat sesi disimpan.

## Ringkasan perubahan

Commit `13b54a9` menambahkan 20 file baru dengan total 3.745 baris. Perubahan
ini membangun fondasi domain baru yang terisolasi dan belum disambungkan ke
runtime bot lama atau live trading.

### 1. Fondasi baru `autotrade_next`

- Namespace baru yang terisolasi dari bot lama.
- Canonical JSON encoding versi `atr-json-v1`.
- UTF-8 deterministik tanpa BOM atau newline tambahan.
- Sorting key deterministik dan validasi Unicode NFC.
- Timestamp UTC dengan format mikrodetik tetap.
- Penolakan float, `Decimal`, timestamp non-UTC, key non-string, cycle,
  mapping rusak, dan tipe ambigu.
- Batas integer 2048-bit dan kedalaman struktur 64 level.
- Representasi angka presisi menggunakan `ScaledInteger`.

### 2. Deterministic identity

Generator identity stabil ditambahkan untuk:

- Candidate
- Decision
- Intent
- Event
- Client order

Identity menggunakan recipe immutable dan versioned, domain separation, field
projection dengan urutan terkunci, canonical preimage, serta full lowercase
SHA-256. Format key adalah `<kind>:v1:<digest>`. Retry atau replay atas fakta
yang sama dengan demikian menghasilkan ID yang sama.

### 3. Typed error contract

Error domain membawa:

- `error_code`
- `severity`
- `retryable`
- `evidence_ref`
- `correlation_id`
- structural error path

Input asing tidak diproses dengan `repr()`, sehingga tidak membuka jalur
eksekusi kode atau error tak terkontrol dari representasi objek.

### 4. Pengujian

Ditambahkan 46 contract tests yang mencakup:

- exact canonical bytes;
- golden preimage dan digest untuk kelima identity;
- determinisme dalam 100 pengulangan;
- Unicode, timestamp, integer, bool-vs-int, dan absent-vs-null;
- cycle dan excessive nesting;
- mapping mutation dan duplicate keys;
- recipe/version mismatch;
- dependency boundary agar domain baru tidak mengimpor database, exchange,
  Telegram, atau runtime lama.

Hasil pengujian yang tercatat:

| Cakupan | Hasil |
|---|---:|
| Contract tests baru | 46 passed |
| Contract baru + regression Strategy 2 | 74 passed |
| Full repository | 742 passed |
| Kegagalan baseline lama | 14 failed + 5 errors |

Kegagalan baseline tersebut sudah ada sebelum `autotrade_next` dan bukan
regresi dari commit ini.

### 5. Dokumen pengembangan

Artefak yang tersedia:

- Architecture Spine dengan 29 architecture decisions;
- implementation notes;
- technical research;
- SPEC AutoTrade Replacement;
- 5 epic dan 32 story;
- sprint tracker;
- Story 1.1 lengkap beserta hasil review.

Status pekerjaan: Story 1.1 `done`; Story 1.2 belum dimulai.

## Batas perubahan dan keselamatan

- Runtime bot lama tidak dimodifikasi.
- Tidak ada perubahan database produksi.
- Tidak ada wiring ke exchange.
- Tidak ada deploy.
- Bot VM belum direstart.
- Commit belum di-push ke GitHub.
- Live trading tidak disentuh.

## Titik lanjut sesi berikutnya

Mulai dari Story 1.2 berdasarkan sprint tracker dan artefak Epic 1. Pertahankan
isolasi `autotrade_next` serta dependency boundary yang sudah dikunci oleh
contract tests. Sebelum implementasi, verifikasi kembali status branch,
worktree, dan baseline test; jangan melakukan wiring runtime, deploy, restart
VM, atau aktivasi live trading tanpa instruksi eksplisit.
