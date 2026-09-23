# Investigation: AutoTrade Tidak Membuka Posisi

## Hand-off Brief

1. **Apa yang terjadi.** Pengguna melaporkan AutoTrade tidak memperoleh satu posisi pun; penyebab teknis belum disimpulkan.
2. **Posisi kasus.** Perimeter bukti selesai: engine lokal tidak aktif, startup terakhir shutdown akibat konflik Telegram, dan source memiliki trigger gap yang dapat mencegah sinyal mencapai eksekusi.
3. **Yang dibutuhkan berikutnya.** Lanjutkan causal trace/refutation untuk menetapkan paket perbaikan minimal yang memulihkan dry-run tanpa melonggarkan risk control secara buta.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-08-12 |
| Status | Active |
| System | Linux, Python crypto trading bot, Indodax, timezone Asia/Jakarta |
| Evidence sources | Dokumentasi, source code, tests, konfigurasi, version control, log/database runtime jika tersedia |

## Problem Statement

Pengguna melaporkan bahwa proses AutoTrade tidak mendapatkan satu posisi pun dan meminta audit menyeluruh, perbaikan bila diperlukan, testing, serta dokumentasi. Perubahan implementasi harus memperoleh persetujuan pengguna terlebih dahulu.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| `advanced_crypto_bot/README.md` | Available | Menyatakan AutoTrade terkunci ke DRY RUN dan hanya mencatat would-be entry. |
| `README.md` | Available | Menyatakan auto buy/sell merupakan fitur; bertentangan dengan README aplikasi. |
| Source code AutoTrade dan signal pipeline | Available | Entry point, queue, trigger, dan seluruh gate sudah dipetakan. |
| Test suite | Available | 86 passed, 2 failed karena drift `DRY_RUN_MAX_TOTAL_IDR`. |
| Runtime logs dan database | Available | Log 14.007 baris serta SQLite dibaca read-only. |
| Konfigurasi/secrets runtime | Available | Flag efektif diaudit; secret tidak dibaca/disalin. |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --- | --- | --- | --- |
| 1 | Petakan entry point dan lifecycle AutoTrade | High | Done | Trigger gap ditemukan. |
| 2 | Audit semua gate/rejection reason dari signal ke posisi | High | Done | Lebih dari 20 gate; reject dominan S/R dan Quality Engine. |
| 3 | Rekonstruksi bukti runtime dari log/database | High | Done | Engine tidak aktif; data berhenti Juni; funnel dihitung. |
| 4 | Jalankan test AutoTrade yang aman/read-only | High | Done | 86 passed, 2 failed; tidak ada order/network call. |
| 5 | Audit konfigurasi efektif dan feature flags | High | Done | AutoTrade dan dry-run aktif; hard gate berlapis aktif. |
| 6 | Telusuri perubahan git terbaru pada jalur terkait | Medium | Done | Quant hardening menambah hard gate setelah baseline. |
| 7 | Causal trace dan refutation pass | High | Open | Bedakan lifecycle, trigger, signal-quality, dan ledger defects. |

## Timeline of Events

| Time | Event | Source | Confidence |
| --- | --- | --- | --- |
| 2026-08-12 | Pengguna melaporkan AutoTrade tidak pernah membuka posisi | Permintaan pengguna | Confirmed |
| 2026-08-12 | Dokumentasi aplikasi ditemukan menyatakan AutoTrade locked DRY RUN | `advanced_crypto_bot/README.md:25`, `advanced_crypto_bot/README.md:94` | Confirmed |

## Confirmed Findings

### Finding 1: Dokumentasi aplikasi menyatakan AutoTrade tidak menempatkan order riil

**Evidence:** `advanced_crypto_bot/README.md:25`, `advanced_crypto_bot/README.md:77-79`, `advanced_crypto_bot/README.md:94-96`

**Detail:** Jalur AutoTrade didokumentasikan sebagai DRY RUN yang hanya mencatat calon entry; Scalper disebut sebagai satu-satunya jalur real-money.

### Finding 2: Dokumentasi tingkat root bertentangan dengan kebijakan tersebut

**Evidence:** `README.md:22-27`

**Detail:** README root mempromosikan auto buy/sell dan dry-run sebagai mode, bukan sebagai penguncian permanen.

### Finding 3: Engine AutoTrade lokal tidak sedang berjalan

**Evidence:** Tidak ada process bot; `crypto-bot.service` tidak terdaftar; SQLite signal/trade tidak berubah sejak 14 Juni 2026.

**Detail:** Tanpa engine aktif, tidak mungkin terbentuk posisi baru pada workspace yang diaudit.

### Finding 4: Startup penuh terakhir dihentikan konflik Telegram polling

**Evidence:** `advanced_crypto_bot/logs/trading_bot.log:13834`, `advanced_crypto_bot/logs/trading_bot.log:13869-13872`

**Detail:** Instance lain melakukan `getUpdates`; proses ini mulai shutdown sekitar satu menit setelah startup.

### Finding 5: Jalur trigger AutoTrade terputus

**Evidence:** `advanced_crypto_bot/bot.py:954-958`, `advanced_crypto_bot/workers/price_poller.py:347-358`, `advanced_crypto_bot/bot.py:1377-1384`, `advanced_crypto_bot/autotrade/runtime.py:995-1010`

**Detail:** WebSocket dinonaktifkan; REST poller hanya memonitor sinyal; queue worker memanggil AutoTrade dengan `signal=None`, sehingga auto-promotion tidak dapat terjadi ketika pair belum terdaftar.

### Finding 6: Funnel sinyal sangat ketat

**Evidence:** `data/signals.db` berisi 6.388 sinyal: 6.090 HOLD (95,34%), hanya 43 BUY dan 2 STRONG_BUY. Log memuat 415 HOLD trace, terutama S/R (208) dan Quality Engine (195).

**Detail:** Bahkan setelah lifecycle/trigger pulih, throughput akan tetap rendah tanpa observability dan validasi interaksi gate.

### Finding 7: Ledger posisi tidak konsisten

**Evidence:** `data/trading.db` memiliki 24 trade CLOSED bertanda DRY RUN, tetapi `amount=0`, `total=0`, portfolio kosong, sementara notes menyebut kuantitas nonzero.

**Detail:** UI/query posisi dapat terlihat kosong meski simulasi pernah terjadi.

### Finding 8: Test terkait mayoritas lulus tetapi dua invariant tidak lagi diuji benar

**Evidence:** 86 passed, 2 failed pada `tests/test_runtime_fill_reconciliation.py`; test mem-patch `Config.DRY_RUN_MAX_TOTAL_IDR` yang tidak ada sementara runtime memakai konstanta lokal.

**Detail:** Drift test/implementasi meninggalkan cap dan rekonsiliasi amount-total tanpa coverage efektif.

## Deduced Conclusions

### Deduction 1: Zero-position bukan disebabkan satu threshold

**Based on:** Finding 3-7.

**Reasoning:** Engine mati menghentikan seluruh produksi; saat hidup trigger gap dapat menghentikan dispatch; kandidat yang sampai pipeline hampir seluruhnya menjadi HOLD; posisi yang pernah ada tidak dimaterialisasi konsisten.

**Conclusion:** Perbaikan harus berurutan: lifecycle → dispatch contract → observability/gate validation → ledger integrity.

## Hypothesized Paths

### Hypothesis 1: Semua kandidat posisi dihentikan sebelum pencatatan posisi oleh konfigurasi atau rejection gate

**Status:** Open

**Theory:** Feature flag, DRY RUN semantics, signal threshold, quant/risk gate, cooldown, balance, atau circuit breaker memblokir seluruh entry.

**Supporting indicators:** Tidak ada posisi menurut laporan pengguna dan jalur memiliki banyak lapisan seleksi.

**Would confirm:** Funnel runtime menunjukkan kandidat masuk tetapi seluruhnya ditolak dengan alasan deterministik yang sama atau kombinasi gate.

**Would refute:** Bukti database/log menunjukkan posisi dry-run pernah terbentuk atau loop AutoTrade tidak pernah menerima kandidat.

**Resolution:** Pending.

### Hypothesis 2: Trigger gap adalah regresi utama zero-entry setelah restart

**Status:** Open

**Theory:** Kombinasi WebSocket off, REST poller tanpa execution call, dan queue worker `signal=None` membuat kandidat tidak mencapai eksekusi secara andal.

**Would confirm:** Test integrasi realistis membuktikan queued BUY gagal sebelum patch dan membuka satu posisi dry-run sesudah contract diperbaiki.

**Would refute:** Runtime trace membuktikan full signal object secara rutin mencapai `_check_trading_opportunity_locked` melalui jalur aktif lain.

**Resolution:** Pending refutation pass.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | --- | --- |
| Deployment produksi/VM aktual | Menentukan apakah source lokal sama dengan runtime target | Verifikasi read-only commit, service, dan log VM memerlukan akses runtime terkait. |
| Rejection counters terstruktur per scan | Menentukan blocker dominan setelah trigger pulih | Tambahkan telemetry pada tahap implementasi setelah approval. |
| Snapshot market realistis end-to-end | Membuktikan interaksi seluruh gate | Fixture/replay yang tidak memanggil exchange. |

## Source Code Trace

| Element | Detail |
| --- | --- |
| Error origin | `advanced_crypto_bot/bot.py:1377-1384` membuang queued signal; `workers/price_poller.py:347-358` tidak dispatch AutoTrade |
| Trigger | Scheduled scan → SignalQueue; REST price poller; WebSocket path nonaktif |
| Condition | Engine mati atau signal object/pair eligibility tidak mencapai runtime; kandidat berikutnya menghadapi hard gate berlapis |
| Related files | `advanced_crypto_bot/bot.py`, `workers/price_poller.py`, `autotrade/runtime.py`, `autotrade/trading_engine.py`, `core/config.py` |

## Conclusion

**Confidence:** Medium

Perimeter bukti menunjukkan empat mekanisme gabungan: engine tidak aktif, startup terakhir shutdown karena konflik Telegram, dispatch AutoTrade memiliki trigger gap, dan 95,34% sinyal menjadi HOLD. Ledger dry-run juga inkonsisten. Root cause final menunggu causal/refutation pass dan reproduksi terisolasi.

## Recommended Next Steps

### Fix direction

Belum ditetapkan sebelum causal trace selesai.

### Diagnostic

Inventaris bukti runtime, petakan funnel keputusan, jalankan test aman, lalu klasifikasikan setiap rejection gate berdasarkan frekuensi dan validitas trading/risk.

## Reproduction Plan

Reproduksi awal akan memakai dry-run/test doubles agar tidak mengirim order riil: masukkan signal yang memenuhi syarat, telusuri hasil setiap gate, dan pastikan tepat satu posisi simulasi tercatat atau rejection reason yang eksplisit dihasilkan.

## Side Findings

- Dokumentasi root dan README aplikasi tidak konsisten mengenai kemampuan real AutoTrade.
