---
title: 'Integrasi runtime shadow Strategi 2 pada worker autotrade'
type: 'feature'
created: '2026-08-20'
status: 'done'
baseline_commit: '6cbd92d'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-patient-net-profit-swing-autotrade-research-2026-08-16.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-strategy2-phase1-foundation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Fondasi Strategi 2 sudah ada, tetapi worker autotrade belum memiliki hook shadow yang benar-benar memakai `TradeIntent` tervalidasi dari jalur produksi. Akibatnya Strategi 2 belum bisa mengamati input runtime yang sama dengan Strategi 1, belum bisa menulis keputusan counterfactual secara durable, dan belum bisa dibandingkan secara sah dalam dry-run/shadow tanpa risiko mengganggu execution baseline.

**Approach:** Tambahkan integrasi shadow-only yang additive pada seam worker sesudah `TradeIntent.validate()` dan sebelum Strategy 1 runtime berjalan. Strategi 2 hanya merekam evaluasi dan lifecycle virtual ke tabel `strategy2_*`, tetap default-off, tidak memblokir queue settlement, dan tidak mengubah keputusan, ledger, order, fill, atau pair lock Strategi 1.

## Boundaries & Constraints

**Always:** `AUTOTRADE_STRATEGY2_ENABLED=false` tetap default; hanya mode `shadow` yang boleh menyalakan hook; hook berjalan paling lambat satu kali per `TradeIntent.idempotency_key`; input shadow harus berasal dari `TradeIntent` tervalidasi dan snapshot signal immutable yang sama dengan Strategy 1; error Strategi 2 harus fail-closed ke log/no-op tanpa menggagalkan Strategy 1, queue ack, atau settlement; seluruh write tetap hanya ke `strategy2_*`; reason taxonomy harus eksplisit untuk `NO_ENTRY`, `ENTER_CANDIDATE`, `SHADOW_SKIPPED`, dan replay; test harus membuktikan Strategy 1 behavior identik saat flag off maupun saat shadow error.

**Ask First:** Aktivasi `.env` di VM; perubahan modal virtual default; private-order/live execution; perubahan semantics queue retry/ack; promosi Strategy 2 menjadi gate yang mempengaruhi keputusan Strategy 1.

**Never:** Mengubah hasil `check_trading_opportunity()` Strategy 1; menginjeksi order/fill/private API untuk Strategy 2; menulis ke `autotrade_intents`, `autotrade_orders`, `autotrade_fills`, `trades`, atau `users.balance` atas nama Strategy 2; menambahkan thread/worker kedua yang berebut lock runtime; menyamarkan error shadow sebagai decision Strategy 1.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Shadow off | Flag false / mode off | Worker tidak memanggil Strategi 2 dan Strategy 1 berjalan normal | Tidak ada row `strategy2_*` baru |
| Shadow on valid intent | `TradeIntent` valid BUY/SELL dan signal immutable | Strategi 2 merekam satu keputusan shadow idempotent lalu Strategy 1 tetap berjalan | Replay key sama mengembalikan row sama |
| Strategy 1 veto / NO_ENTRY | Signal tervalidasi tetapi baseline memutuskan tidak entry | Strategi 2 tetap dapat merekam reason shadow yang spesifik tanpa mengubah veto baseline | Error shadow tidak mengubah NO_ENTRY Strategy 1 |
| Shadow failure | Repository/evaluator Strategy 2 raise exception | Worker log warning, lanjut ke Strategy 1, queue settlement tetap terjadi | Tidak ada crash/poison queue |
| Duplicate replay | Intent sama diproses ulang | Shadow write tidak gandakan decision/event/cash | Idempotent no-op |
| Invalid config | mode invalid / cash invalid | Hook efektif off walau env enabled=true | Fail-closed tanpa side effect |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/bot.py` -- queue worker seam: `TradeIntent.validate()` lalu panggil runtime baseline.
- `advanced_crypto_bot/autotrade/runtime.py` -- existing Strategy 1 entry point dan idempotency path yang tidak boleh berubah hasilnya.
- `advanced_crypto_bot/autotrade/strategy2/repository.py` -- persistence decisions/events/virtual ledger Strategy 2.
- `advanced_crypto_bot/autotrade/strategy2/` -- tempat evaluator/hook shadow runtime additive baru.
- `advanced_crypto_bot/core/config.py` -- feature flag shadow default-off yang harus tetap fail-closed.
- `advanced_crypto_bot/tests/test_autotrade_dryrun_signal_cycle.py` -- harness runtime untuk default-off, veto, replay, dan no-op baseline.
- `advanced_crypto_bot/tests/test_strategy2_isolation.py` -- bukti Strategy 2 tidak menyentuh ledger Strategy 1.

## Tasks & Acceptance

**Execution:**
- [x] `advanced_crypto_bot/autotrade/strategy2/` -- tambah evaluator/hook shadow runtime yang menerima `TradeIntent` + signal immutable, menghasilkan decision envelope typed/idempotent, dan no-op aman saat disabled/error.
- [x] `advanced_crypto_bot/bot.py` -- panggil hook shadow tepat sesudah validasi intent dan sebelum runtime Strategy 1, tanpa mengubah control flow, ack, atau hasil baseline.
- [x] `advanced_crypto_bot/tests/test_autotrade_dryrun_signal_cycle.py`, `advanced_crypto_bot/tests/test_strategy2_isolation.py` -- tambah regression untuk off-mode, shadow-on valid path, replay, veto semantics, dan shadow failure fallback.
- [x] `advanced_crypto_bot/docs/autotrade-strategy2.md` -- dokumentasikan seam runtime baru, behavior fail-closed, semantics veto, dan batas bahwa shadow belum mempengaruhi execution.

**Acceptance Criteria:**
- Given konfigurasi lama atau config Strategy 2 invalid, when worker memproses signal, then tidak ada perilaku Strategy 1 yang berubah dan tidak ada write shadow baru.
- Given `TradeIntent` valid dan Strategy 2 shadow enabled, when signal yang sama diproses ulang, then keputusan shadow tetap satu kali secara idempotent dan Strategy 1 tetap hanya mengikuti jalurnya sendiri.
- Given baseline menghasilkan `NO_ENTRY` atau veto execution, when hook shadow aktif, then reason shadow terekam spesifik tanpa mengubah keputusan/telemetry baseline.
- Given Strategy 2 evaluator atau repository gagal, when worker melanjutkan proses, then Strategy 1 tetap selesai dan queue settlement tidak crash atau poison-loop.
- Given seluruh suite targeted dijalankan, when hasil diverifikasi, then test Strategy 2 dan regression runtime terkait lulus tanpa akses private API/network tambahan.

## Spec Change Log

## Design Notes

Hook utama ditempatkan di worker, bukan di dalam cabang dalam Strategy 1 runtime, agar coupling minimum. Worker sudah memiliki `TradeIntent` tervalidasi, `runtime_signal` immutable-ish, dan titik fallback `NO_ENTRY` yang jelas. Shadow runtime cukup mengembalikan envelope observasi untuk logging/persistence internal; ia tidak mengembalikan veto ke caller.

Contoh shape internal yang diharapkan:

```python
shadow_result = strategy2_shadow.observe_intent(intent=intent, signal=runtime_signal)
# best effort only; any exception becomes warning + continue
```

## Verification

**Commands:**
- `venv/bin/python -m pytest -q tests/test_autotrade_dryrun_signal_cycle.py tests/test_strategy2_isolation.py`
- `venv/bin/python -m pytest -q tests/test_strategy2_contracts.py tests/test_strategy2_repository.py tests/test_autotrade_dispatch_lifecycle.py`
- `venv/bin/python -m compileall -q autotrade/strategy2 bot.py`

## Suggested Review Order

**Worker Seam**

- Entry seam now preserves source signal identity before baseline runtime starts.
  [`bot.py:1422`](../../advanced_crypto_bot/bot.py#L1422)

- Best-effort shadow import/error path cannot poison Strategy 1 queue flow.
  [`bot.py:1475`](../../advanced_crypto_bot/bot.py#L1475)

**Shadow Observer**

- Shadow payload builder keeps immutable intent plus original snapshot identifier.
  [`shadow_runtime.py:25`](../../advanced_crypto_bot/autotrade/strategy2/shadow_runtime.py#L25)

- Observer writes one decision, one candidate event, and stable replay audit only.
  [`shadow_runtime.py:44`](../../advanced_crypto_bot/autotrade/strategy2/shadow_runtime.py#L44)

- Replay audit persists in `strategy2_*` without mutating Strategy 1 or live projection state.
  [`repository.py:222`](../../advanced_crypto_bot/autotrade/strategy2/repository.py#L222)

**Taxonomy and Evidence**

- Additive shadow-only reason codes stay explicit and typed.
  [`taxonomy.py:23`](../../advanced_crypto_bot/autotrade/strategy2/taxonomy.py#L23)

- Operator contract now states fail-closed shadow semantics and runtime boundary.
  [`autotrade-strategy2.md:1`](../../advanced_crypto_bot/docs/autotrade-strategy2.md#L1)

**Regression Coverage**

- Runtime tests now cover idempotent shadow replay, post-advance replay, and source-id preservation.
  [`test_autotrade_dryrun_signal_cycle.py:906`](../../advanced_crypto_bot/tests/test_autotrade_dryrun_signal_cycle.py#L906)

- Isolation tests prove off-mode no-op and shadow failure fallback to baseline safety.
  [`test_strategy2_isolation.py:112`](../../advanced_crypto_bot/tests/test_strategy2_isolation.py#L112)
