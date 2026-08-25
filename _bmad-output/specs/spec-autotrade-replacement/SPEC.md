---
id: SPEC-autotrade-replacement
companions:
  - ../../planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md
  - ../../planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/IMPLEMENTATION-NOTES.md
  - ../../planning-artifacts/research/technical-impactful-modern-trading-architecture-research-2026-08-25.md
sources: []
---

> **Canonical contract.** SPEC ini dan seluruh file pada `companions:` adalah kontrak lengkap yang telah divalidasi preservasinya untuk build, test, dan validation.

# AutoTrade Replacement

## Why

Operator memerlukan pengganti AutoTrade yang hasil DRY RUN-nya dapat dipercaya setelah biaya, tidak memiliki ledger atau authority ganda, aman saat data/order ambigu, dan menghasilkan evidence yang cukup kuat sebelum strategi mendapat kewenangan. Sistem legacy mencampur decision, execution, accounting, projection, dan live capability sehingga profitabilitas maupun keselamatannya tidak dapat dibuktikan secara konsisten.

## Capabilities

- **CAP-1 — Canonical decision**
  - **intent:** Sistem menangkap Candidate point-in-time yang immutable dan menghasilkan tepat satu Decision canonical yang legal terhadap state untuk setiap policy version.
  - **success:** Replay input identik menghasilkan Decision/state identik dan setiap Candidate berakhir dengan action serta structured terminal reason.

- **CAP-2 — Costed portfolio policy**
  - **intent:** Sistem membandingkan proposal Champion dan Challenger dengan evidence, opportunity set, cost, dan allocation context yang sama tanpa memberi Challenger execution authority.
  - **success:** Entry hanya dibuat dari approved Champion ketika conservative net edge dan deterministic portfolio allocation lolos; loser menghasilkan `ABSTAIN` dan urutan pair tidak mengubah hasil.

- **CAP-3 — Fill-authoritative lifecycle**
  - **intent:** Sistem melacak Intent, Order, Fill, Position, dan Policy State melalui satu lifecycle append-only.
  - **success:** Cash, fee, quantity, reservation, dan exposure tetap conserved pada partial fill, duplicate, out-of-order, cancel/fill race, expiry, restart, dan UNKNOWN; hanya Fill tervalidasi mengubah accounting.

- **CAP-4 — Executable DRY RUN market and venue**
  - **intent:** Sistem membentuk market evidence spot-IDR point-in-time dan mensimulasikan execution yang executable tanpa jalur submit live.
  - **success:** Setiap capability Indodax yang dipakai lulus contract registry, pricing berjalan terhadap qualified L2/depth, simulator dapat direplay, dan artifact tidak dapat mengirim order uang nyata.

- **CAP-5 — Persisted risk and safety control**
  - **intent:** Sistem menerapkan risk envelope, reservation, safety cause, kill, hard-drawdown zeroing, dan reconciliation secara persisted dan fail-closed.
  - **success:** Risk-increasing entry ditolak ketika state/evidence tidak current; protective exit tetap tersedia secara aman; kill mengikuti state machine normatif; partial fill tidak melepaskan capacity sebelum terbukti terminal.

- **CAP-6 — Governed strategy evidence**
  - **intent:** Sistem merekam Experiment, semua Trial, matured outcome, benchmark, dan evidence promotion tanpa leakage atau selection-history deletion.
  - **success:** Promotion hanya dapat membaca sealed report dengan full trial family, closed `UNSCORABLE` taxonomy, frozen holdout, forward shadow, costed benchmark, DSR/PBO, dan approval manusia.

- **CAP-7 — Fenced canonical persistence**
  - **intent:** Sistem memproses semua mutation melalui satu fenced writer, canonical encoding, atomic command boundary, journal hash chain, dan outbox/inbox.
  - **success:** Stale writer dan duplicate effect ditolak, crash tidak menghilangkan committed event, tampering terdeteksi, dan golden identity/event vectors byte-stable.

- **CAP-8 — Safe operations and read surfaces**
  - **intent:** Operator mengobservasi invariant, risk, evidence, dan lifecycle serta menjalankan command sensitif melalui read projection dan audited command surface yang terpisah.
  - **success:** Dashboard/Telegram tidak menjadi truth source atau menahan trading commit; setiap approval/reset/correction mempunyai actor, reason, evidence, idempotency key, dan immutable audit event.

- **CAP-9 — Fenced legacy migration and cutover**
  - **intent:** Sistem memigrasikan fakta legacy yang terbukti dan memindahkan virtual portfolio authority tanpa dual settlement.
  - **success:** Shadow terisolasi, backup/restore/reconciliation lulus, tidak ada unexplained mismatch atau working UNKNOWN, cutover memakai epoch lebih tinggi, dan rollback tetap additive.

- **CAP-10 — Reproducible runtime and evidence lifecycle**
  - **intent:** Sistem dibangun, dimigrasikan, direstart, dibackup, dan membersihkan evidence melalui artifact serta policy yang versioned dan reproducible.
  - **success:** Exact runtime/build checks, offline migration, replay/restore drill, SLO gates, retention holds, dan deletion manifests lulus tanpa runtime DDL atau dependency resolution.

## Constraints

- MVP hanya DRY RUN/shadow; artifact dan process tidak membawa live submission adapter atau trade-capable credential.
- Seluruh detail normatif AD-01–AD-29 dalam Architecture Spine mengikat; companion bukan materi opsional.
- Hanya canonical Fill tervalidasi mengubah cash dan exposure; legacy tables, Redis, balances, UI, dan notification adalah projection atau external evidence.
- Tepat satu persistently fenced writer memiliki mutation authority; tidak ada dual writer/settlement, runtime DDL, atau network call di dalam canonical transaction.
- Safety invariant absolut: evidence missing, stale, ambiguous, unreconciled, atau unqualified menutup entry sebelum menutup recovery/protective exit.
- Money dan quantity memakai `Decimal`/scaled integer; identity/encoding deterministik; event time dan receive time UTC disimpan terpisah.
- Risk envelope versioned membatasi Position 10% equity, exposure portfolio 40%, daily-loss latch 2%, planned loss 0,5%, dan hard-drawdown zeroing trigger 10%.
- Tidak ada automatic retraining, promotion, kill clear, drawdown reset, outcome-aware relabel, atau legacy-authority reactivation.

## Non-goals

- Live trading atau penyimpanan credential dengan trade permission.
- Automatic model retraining/promotion dan deep-learning/RL-first strategy.
- Multi-host writer, microservices, PostgreSQL, atau distributed broker sebelum single-host evidence membuktikan kebutuhan.
- Menjamin profit atau realized loss cap; risk limit adalah trigger/control dan strategy harus membuktikan net-cost evidence.
- Menghapus atau merombak legacy writer sebelum cutover gate serta rollback window terpenuhi.

## Success signal

AutoTrade Replacement dapat menjalankan full DRY RUN Candidate→Decision→Intent→Order→Fill→Position serta recovery/cutover rehearsal dari clean store dengan outcome dan semantic hash identik, zero live side effect, zero accounting mismatch, zero unresolved working UNKNOWN, dan satu sealed Champion/Challenger Evidence Report yang dapat diputuskan manusia.

## Assumptions

- Horizon, confirmation, turnover, freshness, UNKNOWN recovery, retention, storage, backup, dan SLO initial baselines pada PRD/Architecture Spine bersifat fail-closed sampai telemetry dan versioned approval menggantikannya.
