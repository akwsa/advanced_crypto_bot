---
title: 'Pulihkan AutoTrade Dry-Run Decision/Execution Spine'
type: 'refactor'
created: '2026-08-12'
status: 'done'
baseline_commit: 'cf97fceafda46df84fa1a92c70f46040a3a6df20'
review_loop_iteration: 4
context:
  - _bmad-output/planning-artifacts/research/technical-autotrade-crypto-indodax-market-execution-risk-research-2026-08-12.md
  - _bmad-output/implementation-artifacts/investigations/autotrade-tidak-membuka-posisi-investigation.md
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** AutoTrade dry-run tidak menghasilkan posisi secara andal karena payload sinyal hilang di queue, trigger/lifecycle tidak tunggal, keputusan tidak memiliki telemetry deterministik, dan ledger lama menghapus amount/total saat close sehingga posisi tidak dapat direkonstruksi.

**Approach:** Pulihkan satu jalur dry-run signal→intent→decision→order/fill→position secara incremental dan kompatibel dengan modul lama. Jika acceptance/replay menunjukkan jalur utama tetap bermasalah atau tidak optimal, hentikan rollout dan susun Strategi 2 berdasarkan riset GitHub serta sumber web primer sebelum penerapan.

## Boundaries & Constraints

**Always:** Dry-run only; payload sinyal lengkap dan immutable; setiap intent memiliki correlation/idempotency ID serta keputusan/rejection reason; ledger baru additive dan transaksi atomik; legacy `trades` tetap kompatibel; test tidak boleh network/private-order; dokumentasikan hasil dan Strategi 2 bila trigger kriterianya terpenuhi.

**Ask First:** Deployment/restart VM, migrasi/destructive cleanup data historis, perubahan threshold alpha/risk, aktivasi WebSocket production, atau tindakan real trading.

**Never:** Mengirim order Indodax, mengaktifkan live trading, membaca/mencetak secret, menghapus database, menganggap order FILLED hanya karena hilang dari open orders, atau melonggarkan gate sekadar mengejar jumlah posisi.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid queued BUY | Full signal payload, fresh dry-run state | Payload utuh mencapai runtime; satu intent dan maksimal satu posisi | Structured decision persisted |
| Invalid/stale payload | Missing recommendation/expired snapshot | Tidak dieksekusi | `REJECTED` dengan reason; bukan silent drop |
| Duplicate/retry | Intent yang sama diproses ulang | Ledger/position tidak berubah dua kali | Return existing decision/order |
| Fill/restart | Immediate/deferred fill atau restart tengah transaksi | Order, fill, position konsisten dan dapat direplay | Rollback/reconcile; state UNKNOWN bila ambigu |
| Telegram conflict | Control plane gagal | Engine dry-run tetap hidup/degraded | Log health reason tanpa global shutdown |
| Acceptance tidak optimal | Invariant gagal atau funnel tetap tidak menghasilkan valid pass | Rollout utama dihentikan | Riset dan dokumentasikan Strategi 2 terlebih dahulu |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/bot.py` -- producer scan, queue worker, scheduler/lifecycle, pending-order reconciliation.
- `advanced_crypto_bot/signals/signal_queue.py` -- queue envelope, serialization, skipped/done telemetry.
- `advanced_crypto_bot/autotrade/runtime.py` -- canonical decision/execution path dan dry-run fill.
- `advanced_crypto_bot/autotrade/contracts.py` -- kontrak typed intent/gate/decision baru.
- `advanced_crypto_bot/core/database.py` -- schema additive, atomic intent/order/fill/position repository.
- `advanced_crypto_bot/core/config.py` -- cap dry-run yang testable; tanpa tuning threshold.
- `advanced_crypto_bot/tests/test_autotrade_dispatch_lifecycle.py` -- regression dispatch/lifecycle.
- `advanced_crypto_bot/tests/test_autotrade_ledger.py` -- migration, idempotency, atomicity, replay.
- `advanced_crypto_bot/tests/test_runtime_fill_reconciliation.py` -- perbaikan drift patch dan invariant fill.
- `advanced_crypto_bot/docs/autotrade-dryrun-decision-spine.md` -- desain, operasi, funnel, rollback, Strategi 2 bila diperlukan.

## Tasks & Acceptance

**Execution:**
- [x] `core/config.py`, `tests/test_runtime_fill_reconciliation.py` -- jadikan cap dry-run configurable dan perbaiki lifecycle patcher agar baseline hijau.
- [x] `autotrade/contracts.py`, `signals/signal_queue.py`, `bot.py` -- preserve full payload, validasi/version envelope, correlation/idempotency, worker/scheduler idempotent, dan singleton lifecycle.
- [x] `autotrade/runtime.py` -- konsumsi intent tanpa regenerasi/silent drop serta emit structured terminal/pending decision tanpa mengubah threshold.
- [x] `core/database.py` -- tambah schema intent/order/fill/position dan satu transaksi idempotent; dual-write legacy seperlunya.
- [x] Tests -- cover valid/invalid/duplicate, conflict isolation, migration rerun, rollback, immediate/deferred parity, restart/replay, dan larangan private API.
- [x] Documentation -- catat arsitektur, schema, reason codes, runbook, hasil test, serta fallback Strategy 2 jika acceptance gagal.

**Acceptance Criteria:**
- Given queued BUY valid, when worker memprosesnya, then exact semantic payload diteruskan dan tidak pernah diganti `signal=None`.
- Given setiap queued signal, when processing selesai/tertunda/gagal, then ada structured decision atau explicit skipped reason; silent drop nol.
- Given intent/fill identik direplay, when transaksi diulang, then hanya satu logical order/fill dan position tidak terduplikasi.
- Given immediate atau deferred dry-run fill, when ledger dibaca ulang, then quantity, price, total, fee, dan position dapat direkonstruksi serta memenuhi invariant.
- Given Telegram polling conflict, when control plane gagal, then dry-run engine tidak melakukan global shutdown.
- Given seluruh targeted suite, when dijalankan tanpa network, then lulus dan tidak ada private-order call.

## Spec Change Log

- Review 1: adversarial/edge review menemukan restart-loss pada queue destructive, version/finite validation yang tidak efektif, replay `NO_ENTRY` yang tidak terminal, serta dual-write dan lifecycle position yang belum atomik. Implementasi harus mempertahankan typed intent, singleton dry-run, structured reason, dan schema additive; amend patch agar queue memakai inflight/ack recovery, semua outcome durable/idempotent, legacy projection dan normalized ledger ditulis atomik, serta posisi dapat direbuild dari fills.
- Review 2: review final menemukan SELL normalized belum dipanggil, rebuild mencampur user, direct/concurrent replay repository belum idempotent, pending failure dapat diumumkan sukses, cooldown merusak retry, rejection invalid belum durable, dan queue recovery/ack belum sepenuhnya atomik. Patch harus mempertahankan transaksi gabungan dan crash recovery yang sudah benar sambil menutup seluruh lifecycle BUY/SELL per-user serta durable decision semantics.
- Review 3: final review menemukan deferred BUY menganggap intent RECEIVED sebagai replay meski order belum ada, retry transient masih dipotong cooldown, persistence failure dapat menyiarkan sukses, ownership multi-user belum dibawa oleh intent, dan decision/ack dapat menduplikasi telemetry saat crash. Patch harus menguji urutan runtime aktual, membawa user identity end-to-end, dan membuat terminal settlement queue idempotent.
- Review 4: closure review membuktikan persistence exception masih tertelan, typed retry dapat dipotong cooldown internal runtime, pending lookup belum scoped per user, dan scheduled scan belum menetapkan owner eksplisit. Patch harus menolak success broadcast tanpa durable order, menjaga retry nonterminal, dan mengikat setiap intent/order ke owner deterministik.

## Design Notes

Pertahankan modular monolith. Ledger baru menjadi source of truth secara bertahap; `trades` tetap projection kompatibilitas. Queue adalah satu-satunya execution owner agar REST/WebSocket/scan tidak mengeksekusi ganda. Strategi 2 bersifat evidence-triggered, bukan jalur paralel yang langsung diterapkan.

## Verification

**Commands:**
- `cd advanced_crypto_bot && venv/bin/python -m pytest -q tests/test_runtime_fill_reconciliation.py tests/test_autotrade_dispatch_lifecycle.py tests/test_autotrade_ledger.py tests/test_autotrade_dryrun_signal_cycle.py tests/test_dryrun_safety.py tests/test_open_position_sweep.py` -- expected: seluruh test lulus, no network/private order.
- `cd advanced_crypto_bot && venv/bin/python -m pytest -q` -- expected: full suite lulus atau setiap failure unrelated terdokumentasi dengan bukti.
- `git diff --check` -- expected: tidak ada whitespace error.

## Suggested Review Order

**Canonical dispatch dan settlement**

- Entry point mempertahankan payload, owner, retry, singleton, dan terminal settlement.
  [`bot.py:1340`](../../advanced_crypto_bot/bot.py#L1340)

- Queue claim/inflight/settle menjamin crash recovery dan decision deduplication.
  [`signal_queue.py:183`](../../advanced_crypto_bot/signals/signal_queue.py#L183)

**Atomic ledger lifecycle**

- Immediate BUY menulis legacy dan normalized ledger dalam satu transaksi.
  [`database.py:1353`](../../advanced_crypto_bot/core/database.py#L1353)

- Deferred order creation dan promotion tetap atomik serta idempotent.
  [`database.py:1384`](../../advanced_crypto_bot/core/database.py#L1384)

- Partial/full SELL menutup kedua ledger secara atomik.
  [`database.py:1493`](../../advanced_crypto_bot/core/database.py#L1493)

**Contracts dan safety**

- Typed intent memvalidasi version, freshness, finite values, immutability, dan ownership.
  [`contracts.py:46`](../../advanced_crypto_bot/autotrade/contracts.py#L46)

- Dry-run cap menjadi konfigurasi eksplisit tanpa mengubah threshold strategi.
  [`config.py:93`](../../advanced_crypto_bot/core/config.py#L93)

**Regression coverage**

- Dispatch tests mencakup singleton, malformed payload, ownership, dan retry settlement.
  [`test_autotrade_dispatch_lifecycle.py:7`](../../advanced_crypto_bot/tests/test_autotrade_dispatch_lifecycle.py#L7)

- Ledger tests mencakup rollback, concurrency, rebuild per-user, BUY/SELL, dan replay.
  [`test_autotrade_ledger.py:9`](../../advanced_crypto_bot/tests/test_autotrade_ledger.py#L9)
