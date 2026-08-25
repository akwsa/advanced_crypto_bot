# Rekonsiliasi Input — Incident Investigation dan AutoTrade Replacement Handoff

## Scope

Rekonsiliasi ini membandingkan dua input sumber terhadap `prd.md` dan `addendum.md` saat ini. Dokumen ini hanya mengekstrak cakupan dan gap; dokumen PRD tidak diubah.

### Input yang diperiksa

1. `HANDOFF-2026-08-24-autotrade-replacement.md`
2. `investigations/in-out-trade-decision-stability-investigation.md`

## Ringkasan hasil

Substansi utama kedua input sudah terbawa dengan baik. PRD mengubah kegagalan konkret—split decision, dual ledger, state exit ephemeral, pending lifecycle rusak, dan bukti scan yang tidak lengkap—menjadi kontrak produk canonical decision, fill-based accounting, persisted Policy State, restart equivalence, reconciliation, dan evidence governance. Handoff juga konsisten dengan scope DRY RUN dan larangan aktivasi uang asli tanpa gate serta persetujuan Officer.

Empat gap tersisa terutama berada pada traceability dan acceptance evidence, bukan pada arah produk.

## Coverage Matrix

| Sinyal sumber | Cakupan saat ini | Lokasi | Penilaian |
|---|---|---|---|
| Protective exit hanya menutup legacy ledger; normalized Position menjadi ghost | Unified atomic exit, fill-based Position, reconciliation, migrasi ghost position dengan additive correction | FR-7–FR-11, FR-32–FR-34; Addendum D | Covered |
| ACE, BICO, HUMANITY menjadi ghost positions dan memengaruhi equity/drawdown | Canonical equity/risk envelope dan migrasi `PROVEN_CLOSED`/ghost corrections | FR-18, FR-32; SM-1 | Covered secara normatif; kasus bernama belum dijadikan acceptance fixture |
| Entry display/persistence berbeda dari execution karena `pre_sr_recommendation` | Tepat satu Canonical Decision untuk display, persistence, replay, shadow, dan execution; legacy override retired | FR-2; Brownfield Migration Boundary; Addendum D | Covered |
| Exit state trailing, partial TP, time-stop, high-water bersifat ephemeral | Persisted Policy State dan restart equivalence | FR-5, FR-8–FR-10 | Covered |
| Pending worker gagal karena `sqlite3.Row.get`; stale PENDING tersisa | Terminal Order lifecycle, bounded UNKNOWN recovery, queue/order health, zero unresolved pending gap, migration inventory | FR-6, FR-29, FR-32; SM-7; Addendum D | Covered pada outcome, tetapi regression evidence insiden belum eksplisit |
| Snapshot fitur/gate tidak cukup untuk mengukur flip-rate | Immutable Candidate Snapshot, deterministic replay, decision provenance, outcome completeness | FR-1–FR-3, FR-28; SM-2–SM-3 | Mostly covered; metric stabilitas sequential belum eksplisit |
| Multi-source price/freshness dan gap dapat memengaruhi keputusan | Point-in-time market state, freshness/gap control, unified simulator | FR-12–FR-16 | Covered |
| Concurrent exit paths dan split persistence path | Satu atomic exit path, single writer/fencing, no dual-write cutover | FR-8, FR-20, FR-33 | Covered |
| Strategy lama boleh dipertahankan hanya jika terbukti | Legacy strategy wajib canonical-conformant dan lulus evidence gate | Confirmed Product Decisions; FR-27 | Covered |
| Target bukan raw accuracy, melainkan net expectancy OOS setelah seluruh biaya | Calibrated abstention, common comparison, sealed evidence, promotion metrics/counter-metrics | Executive Contract; FR-4, FR-22–FR-27; SM-4 | Covered |
| Simulator sama untuk replay dan live dry-run | Unified simulator version | FR-15 | Covered |
| Real trading tetap nonaktif sampai gate dan approval eksplisit | MVP hanya DRY RUN/shadow; live dibahas pada PRD terpisah | Executive Contract; Stage Matrix; Safety | Covered |
| Operational checkpoint: branch/commit lokal berbeda dari VM; patch taxonomy belum deploy | Tidak dicatat sebagai migration/cutover baseline | — | Gap |

## Gap yang perlu dipertimbangkan saat finalisasi atau architecture

### G-1 — Baseline brownfield/cutover belum diikat pada artifact yang dapat diverifikasi

Handoff menyebut branch `kiro/dryrun-activation-dashboard`, local commit `de49a1d`, VM commit `cdcb9a4`, status belum push/deploy, dan patch taxonomy yang hanya lokal. PRD menetapkan validated migration, tetapi belum mensyaratkan capture baseline berupa code revision, database snapshot/checksum, runtime/config manifest, dan deployment state yang menjadi sumber migrasi. Tanpa baseline itu, tim dapat menjalankan rekonsiliasi terhadap state yang berbeda dari state insiden.

### G-2 — Insiden ACE/BICO/HUMANITY belum menjadi named regression/acceptance corpus

FR-32 sudah mengatur proven ghost positions dan additive correction, tetapi belum mengharuskan tiga lifecycle aktual—ACE TP1+trailing, BICO stop loss, HUMANITY stop loss—menjadi fixture migrasi/replay yang membuktikan legacy CLOSED, normalized exposure zero, cash/P&L conserved, dan tidak ada dampak drawdown phantom. Kasus-kasus ini adalah evidence bernilai tinggi karena sudah memiliki timeline dan hasil terkonfirmasi.

### G-3 — Regression corpus untuk kegagalan pending-order worker belum eksplisit

Outcome yang diinginkan sudah tercakup oleh FR-6, FR-10, FR-11, FR-32, dan SM-7. Namun sumber mencatat defect konkret `sqlite3.Row.get`, 127 kejadian dalam sampel log, dan dua Order PENDING sejak 18 Agustus. Tidak ada acceptance requirement yang secara eksplisit meminta corpus recovery untuk stale PENDING, row-shape compatibility, duplicate/out-of-order recovery, dan restart selama recovery. Detail implementasi tidak perlu masuk FR, tetapi evidence case ini perlu ditautkan ke test/migration plan.

### G-4 — Stabilitas keputusan antar-scan belum memiliki metrik diagnostik eksplisit

PRD menjamin replay deterministik untuk snapshot identik dan memakai hysteresis, tetapi investigasi awal meminta pengukuran flip-rate per pair serta perubahan input yang menyertainya. Belum ada metric/report field yang membedakan perubahan action yang dijelaskan oleh perubahan material input/state dari churn di sekitar boundary. Akibatnya, sistem bisa lulus replay determinism namun tetap menghasilkan ENTER/HOLD/EXIT churn berlebihan pada rangkaian snapshot yang nyaris sama. Metrik ini sebaiknya bersifat diagnostik/counter-metric dan dibekukan per Horizon, bukan target profit mandiri.

## Catatan konsistensi

- Tidak ada konflik antara keputusan handoff dengan current PRD mengenai replacement total, canonical truth layer, atau promotion berbasis evidence.
- Pernyataan investigasi bahwa stochastic model flip-flop belum terbukti dipertahankan dengan benar: PRD tidak mengklaim model lama berosilasi; ia membangun observability untuk membuktikan atau membantahnya.
- Detail metode terbaru di handoff—online calibration, change detection, dan hysteresis/no-trade region sebagai kandidat—dipertahankan sebagai kandidat/evidence, bukan dijadikan klaim bahwa metode tersebut pasti unggul.
- Status runtime/commit dalam handoff adalah fakta operasional bertanggal, bukan requirement produk; relevansinya adalah sebagai provenance baseline migrasi.

## Verdict

**Reconciled with four residual gaps.** Tidak ada keputusan produk utama dari kedua input yang hilang. Gap yang tersisa dapat ditangani sebagai acceptance evidence dan migration/architecture handoff tanpa mengubah tujuan inti PRD.
