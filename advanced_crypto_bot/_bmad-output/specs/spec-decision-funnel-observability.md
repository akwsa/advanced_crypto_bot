---
title: 'Autotrade Decision Funnel Observability'
type: 'feature'
created: '2026-08-24'
status: 'done'
review_loop_iteration: 0
baseline_commit: '2f86691bd9aa569eeaba23587f2d63f8f49549bb'
context:
  - docs/architecture/autotrade-profitability-2026-08-24/ARCHITECTURE-SPINE.md
  - docs/architecture/autotrade-profitability-2026-08-24/IMPLEMENTATION-ROADMAP.md
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Bot menyimpan ribuan keputusan sebagai `NO_ORDER_CREATED` atau `OTHER`, sehingga operator tidak dapat mengetahui gate mana yang menahan trade, berapa besar funnel konversinya, atau apakah perubahan berikutnya sebaiknya melonggarkan filter tertentu. Diagnostik in-memory pada status Telegram juga hilang ketika proses restart.

**Approach:** Jadikan setiap intent actionable berakhir pada terminal status dan reason code stabil, lalu sediakan laporan read-only yang mengagregasi funnel berdasarkan status, reason, pair, dan waktu. Slice ini membangun baseline observability yang diperlukan sebelum counterfactual outcome dan tuning strategi.

## Boundaries & Constraints

**Always:** Pertahankan `autotrade_intents` sebagai rekam keputusan durable; normalisasi pair lowercase; reason code harus berupa enum/taxonomy stabil dan detail dinamis tetap berada di kolom `reason`; classifier harus pure dan deterministik; laporan hanya membaca database; keputusan replay tidak boleh menghasilkan intent kedua; SELL/protective exit tidak boleh diblokir oleh perubahan ini.

**Ask First:** Perubahan threshold entry, penghapusan gate, mutasi/backfill histori VM, atau perubahan schema destruktif membutuhkan persetujuan pengguna.

**Never:** Mengaktifkan live trading, mengklaim profitability dari jumlah entry, mengubah keputusan historis, menyimpan exception/message dinamis sebagai reason code, atau menggunakan `OTHER`/`NO_ORDER_CREATED` untuk jalur kebijakan normal yang dikenali.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Gate menolak kandidat | Intent durable dan alasan gate dikenal | Intent menjadi `NO_ENTRY` dengan reason code taxonomy spesifik | Detail alasan tetap tersimpan untuk diagnosis |
| Runtime selesai tanpa fill | Runtime menyimpan block reason terakhir | Worker memakai taxonomy hasil classifier, bukan generic reason | Alasan tak dikenal menjadi `UNCLASSIFIED_INTERNAL_ERROR` dan terlihat sebagai integrity failure |
| Replay intent | Idempotency key sudah terminal | Keputusan terminal lama dikembalikan tanpa row baru | Tidak mengubah timestamp/reason lama |
| Laporan funnel | Rentang waktu valid dengan atau tanpa data | JSON deterministik berisi totals, conversion, status/reason/pair breakdown, dan generic-rate | Database/rentang invalid menghasilkan exit non-zero dan pesan aman |

</frozen-after-approval>

## Code Map

- `autotrade/runtime.py` -- classifier alasan gate dan seluruh jalur return/blocked entry champion.
- `bot.py` -- signal-queue worker yang menyelesaikan intent dan saat ini membuat fallback `NO_ORDER_CREATED`.
- `core/database.py` -- persistence `autotrade_intents` dan lokasi query agregat read-only.
- `scripts/report_autotrade_funnel.py` -- CLI laporan operasional baru, tanpa mutasi database.
- `tests/test_autotrade_dispatch_lifecycle.py` -- kontrak klasifikasi reason existing.
- `tests/test_autotrade_funnel.py` -- coverage terminal decision dan agregasi laporan.

## Tasks & Acceptance

**Execution:**
- [x] `autotrade/runtime.py` -- perluas taxonomy dan jadikan classification API eksplisit untuk seluruh gate normal yang ada.
- [x] `bot.py` -- pastikan fallback worker selalu menyelesaikan intent dengan reason spesifik; unknown menjadi integrity error yang dapat dihitung.
- [x] `core/database.py` -- tambahkan query funnel read-only dengan filter user/time dan denominator yang eksplisit.
- [x] `scripts/report_autotrade_funnel.py` -- keluarkan JSON machine-readable serta exit non-zero bila generic-rate melewati 0,5%.
- [x] `tests/test_autotrade_dispatch_lifecycle.py`, `tests/test_autotrade_funnel.py` -- uji taxonomy, idempotency, rentang kosong, filtering, conversion, dan integrity gate.

**Acceptance Criteria:**
- Given kandidat actionable yang melewati worker, when lifecycle selesai tanpa order, then row intent memiliki terminal status dan reason code non-generic.
- Given reason dari gate champion yang dikenal, when diklasifikasikan, then hasilnya stabil dan bukan `OTHER` atau `NO_ORDER_CREATED`.
- Given database intent dan rentang waktu, when laporan dijalankan, then total sama dengan jumlah breakdown, conversion denominator terdokumentasi, dan laporan tidak mengubah row.
- Given generic reason melebihi 0,5%, when CLI dijalankan dengan integrity gate, then laporan tetap tercetak dan proses keluar non-zero.

## Spec Change Log

## Design Notes

`actionable_total` adalah semua intent durable pada rentang laporan. `executed_total` adalah status `FILLED` atau `PENDING`; `terminal_total` adalah `FILLED`, `NO_ENTRY`, `REJECTED`, atau error terminal. Conversion dilaporkan sebagai `executed_total / actionable_total`; angka ini adalah kesehatan funnel, bukan metrik profit.

Taxonomy menyatakan lokasi keputusan (`ENTRY_QUALITY`, `LIQUIDITY`, `V4_FILTER`, `RISK_DRAWDOWN`, dan seterusnya). Pesan seperti pair, harga, threshold, atau exception tidak boleh menjadi identifier.

## Verification

**Commands:**
- `venv/bin/python -m pytest -q tests/test_autotrade_dispatch_lifecycle.py tests/test_autotrade_funnel.py tests/test_autotrade_dryrun_signal_cycle.py` -- seluruh kontrak funnel dan regresi lifecycle lulus.
- `venv/bin/python scripts/report_autotrade_funnel.py --db data/trading.db --hours 24 --json` -- JSON valid dan audit tidak mengubah database.
- `git diff --check` -- tidak ada whitespace error.

## Suggested Review Order

**Terminal attribution**

- Mulai dari taxonomy pure yang mengubah pesan dinamis menjadi reason code stabil.
  [`runtime.py:108`](../../autotrade/runtime.py#L108)

- Worker selalu menutup intent tanpa fallback generic yang tersembunyi.
  [`bot.py:1425`](../../bot.py#L1425)

**Durable funnel**

- Aggregator mendefinisikan denominator, integrity rate, dan histori tanpa atribusi.
  [`database.py:18`](../../core/database.py#L18)

- Migration additive menambahkan ownership dan indeks operasional tanpa backfill histori.
  [`database.py:464`](../../core/database.py#L464)

- Intent baru mengikat user ownership sambil mempertahankan idempotency key.
  [`database.py:1529`](../../core/database.py#L1529)

**Operator boundary**

- CLI memakai koneksi SQLite read-only dan integrity exit code fail-closed.
  [`report_autotrade_funnel.py:21`](../../scripts/report_autotrade_funnel.py#L21)

**Verification**

- Tes mencakup breakdown, replay, filtering, generic gate, dan histori unattributed.
  [`test_autotrade_funnel.py:13`](../../tests/test_autotrade_funnel.py#L13)

- Kontrak classifier mencakup seluruh alasan normal TradingEngine yang dikenal.
  [`test_autotrade_dispatch_lifecycle.py:8`](../../tests/test_autotrade_dispatch_lifecycle.py#L8)
