# Investigation: Stabilitas Keputusan In Trade dan Out Trade

## Hand-off Brief

1. **What happened.** User mencurigai keputusan entry/exit tidak stabil; bukti awal mengonfirmasi divergence projection pada tiga posisi canonical, tetapi belum membuktikan flip-flop policy.
2. **Where the case stands.** Perimeter bukti terpetakan; tiga exit legacy terbukti tidak pernah menutup normalized ledger, sementara entry memakai lebih dari satu representasi keputusan.
3. **What's needed next.** Uji kausalitas dan refutasi: hubungkan jalur PriceMonitor, source-of-truth posisi, dan pre-SR execution override dengan timeline VM.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-08-24 |
| Status | Active |
| System | Google Compute Engine `instance-20260609-044439`, branch `kiro/dryrun-activation-dashboard`, DRY RUN |
| Evidence sources | Database dan log VM, source code, tests, Git history, sumber teknis primer |

## Problem Statement

User melaporkan kecurigaan adanya ketidakstabilan pengambilan keputusan untuk In Trade dan Out Trade serta meminta kontrol menyeluruh dengan metode terbaru yang lebih terfokus. Pernyataan ini diperlakukan sebagai hipotesis sampai terdapat bukti flip-flop keputusan, exit yang hilang/terlambat, atau divergence state yang memengaruhi policy.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| Audit canonical equity VM | Available | 3 normalized OPEN, 0 legacy OPEN; ACE/BICO/HUMANITY |
| Trading DB VM | Available | Read-only; 352.538.624 byte; lifecycle intent/order/fill/trade/position dapat direkonstruksi |
| Runtime log VM | Available | `bot.log` 6,78 GB; exit legacy dan worker errors ditemukan |
| Journal systemd VM | Partial | Lifecycle service tersedia; application output berada di `bot.log` |
| Funnel keputusan 24 jam | Available | 1.230 terminal NO_ENTRY; 0 executed; taxonomy issue teridentifikasi |
| Decision snapshots target 72 jam | Missing | Tidak ada intent/signal/Strategy 2 target; flip-rate aktual belum dapat dihitung |
| Source entry path | Available | Dua produsen sinyal, pre-SR execution override, in-memory stabilization, multi-price fetch |
| Source exit path | Available | PriceMonitor menutup legacy saja; canonical positions tidak direbuild ke protective lifecycle |
| Targeted test suite | Available | 132 passed, 22 subtests passed; satu warning Redis deprecation |
| Counterfactual/outcome labels | Partial | Coverage dan kestabilan antar-horizon belum diperiksa |
| Literatur primer | Available | Online calibration, change detection, hysteresis/no-trade bands, transaction-cost-aware filtering |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --- | --- | --- | --- |
| 1 | Rekonstruksi timeline tiga posisi canonical dari intent/order/fill/position/log | High | Done | Ketiganya exit via PriceMonitor legacy; normalized SELL tidak ada |
| 2 | Ukur flip-rate keputusan per pair antar-scan dan perubahan input yang menyertainya | High | Blocked | Snapshot target 72 jam tidak tersedia |
| 3 | Trace seluruh caller entry dan exit/SL/TP/trailing/time-stop | High | Done | Entry dan exit perimeter lengkap dengan path:line |
| 4 | Audit freshness, price source, hysteresis, cooldown, dan state synchronization | High | In Progress | Multi-price source dan ephemeral state teridentifikasi; kausalitas belum diuji |
| 5 | Bandingkan desain dengan praktik primer terbaru | Medium | Done | Benchmark primer tersedia; penerapan belum dipilih |
| 6 | Refutation pass pada akar divergence exit dan entry canonical-decision split | High | Open | Outcome 3 |

## Timeline of Events

| Time | Event | Source | Confidence |
| --- | --- | --- | --- |
| 2026-08-24 12:15 +07 | Canonical equity dan drift auditor masuk di commit `2f86691` | Git history | Confirmed |
| 2026-08-24 19:28 +07 | Polling harga posisi canonical masuk di commit `cdcb9a4` | Git history | Confirmed |
| 2026-08-24 21:29 +07 | Audit VM menemukan 3 normalized OPEN tanpa legacy OPEN | `scripts/audit_autotrade_equity.py` output | Confirmed |
| 2026-08-24 21:44 +07 | Rekonstruksi DB/log membuktikan ACE exit via TP1+trailing, BICO/HUMANITY via stop loss, tanpa normalized SELL | VM `trading.db` + `bot.log` | Confirmed |

## Confirmed Findings

### Finding 1: Projection posisi entry/exit tidak konsisten

**Evidence:** Audit VM 2026-08-24 21:29 +07; `legacy_open_count=0`, `normalized_open_count=3`, mismatches ACE/BICO/HUMANITY.

**Detail:** Canonical ledger masih menanggung quantity dan cost basis Rp6.000.000, sedangkan legacy projection tidak memiliki posisi OPEN. Ini membuktikan divergence state, bukan dengan sendirinya instability policy.

### Finding 2: Tiga protective exit hanya menyelesaikan legacy ledger

**Evidence:** VM `trading.db` dan `bot.log`: ACE legacy trade 524 ditutup 2026-08-18 23:19:48 melalui `PARTIAL_TP_1` lalu `TRAILING_STOP`; BICO trade 522 ditutup melalui `STOP_LOSS`; HUMANITY trade 525 ditutup melalui `STOP_LOSS`. Tidak ada normalized SELL order/fill dan quantity normalized tetap penuh.

**Detail:** Insiden aktual cocok dengan perimeter source: `PriceMonitor` memanggil `close_trade`, sedangkan atomic canonical close tersedia di jalur SELL lain.

### Finding 3: Sumber keputusan entry tidak canonical

**Evidence:** `advanced_crypto_bot/signals/signal_pipeline.py:424`, `advanced_crypto_bot/autotrade/runtime.py:1145`, dan `advanced_crypto_bot/autotrade/runtime.py:1197`.

**Detail:** Recommendation sebelum quality/SR dipertahankan sebagai `pre_sr_recommendation` lalu digunakan kembali untuk execution. Display/persistence final dapat HOLD sementara execution tetap mengevaluasi BUY.

### Finding 4: Pending-order worker gagal berulang

**Evidence:** VM `bot.log`, 127 kejadian pada sampel 100.000 baris terbaru: `sqlite3.Row object has no attribute get`.

**Detail:** Dua pending order sejak 18 Agustus masih PENDING, termasuk ACE. Perimeter menunjukkan worker tersedia tetapi tidak operasional.

## Deduced Conclusions

### Deduction 1: Akar utama Out Trade adalah split persistence path

**Based on:** Finding 1 dan Finding 2; `advanced_crypto_bot/autotrade/price_monitor.py:499`; `advanced_crypto_bot/core/database.py:1852`.

**Reasoning:** Ketiga posisi ditutup oleh protective exits yang sama-sama berakhir di `PriceMonitor._execute_auto_sell`. Jalur itu hanya memanggil `close_trade`; database menunjukkan legacy CLOSED persis pada timestamp exit, normalized quantity tidak berubah, dan normalized SELL fill tidak pernah dibuat. Atomic close sudah tersedia sejak commit `4186615`, sebelum ketiga exit terjadi, tetapi tidak pernah dipanggil oleh PriceMonitor.

**Conclusion:** Divergence bukan noise pasar atau keterlambatan worker; ia merupakan hasil deterministik dari jalur persistence yang berbeda.

### Deduction 2: Ghost positions mengubah keputusan In Trade di seluruh portfolio

**Based on:** Finding 1, audit equity VM, dan startup log `missing_bid`.

**Reasoning:** Canonical equity secara benar membaca normalized OPEN. Karena protective exit gagal menutup normalized ledger, tiga ghost positions tetap dinilai sebagai exposure. Pada startup, tidak tersedianya bid mereka membuat circuit breaker fail-closed; setelah harga tersedia, nilai rugi mereka tetap memengaruhi drawdown dan menghasilkan rejection `DRAWDOWN`/`RISK_DRAWDOWN` pada pair lain.

**Conclusion:** Defect Out Trade secara kausal menciptakan ketidakstabilan yang terlihat pada In Trade.

### Deduction 3: Entry memiliki split semantic decision, tetapi flip-rate belum terbukti

**Based on:** Finding 3 dan absennya decision snapshot target 72 jam.

**Reasoning:** Kode dan test secara sengaja memungkinkan final/display HOLD kembali dievaluasi sebagai BUY melalui `pre_sr_recommendation`. Ini membuktikan dua makna keputusan hidup bersamaan. Namun data VM tidak menyimpan snapshot fitur/gate yang cukup untuk menghitung apakah label berosilasi pada input identik.

**Conclusion:** Inconsistency semantic entry terkonfirmasi; stochastic flip-flop model tetap belum terukur.

## Hypothesized Paths

### Hypothesis 1: Keputusan In/Out Trade tidak stabil

**Status:** Confirmed

**Theory:** Gate entry dan exit berubah-ubah antar-scan tanpa perubahan input material atau state posisi yang sah.

**Supporting indicators:** User mengamati ketidakstabilan; terdapat divergence projection dan perbaikan polling posisi canonical yang baru.

**Would confirm:** Flip-flop berulang pada pair sama dengan fitur/regime/price nyaris identik, atau exit decision hilang akibat source-of-truth berbeda.

**Would refute:** Setiap perubahan keputusan dapat dijelaskan oleh perubahan input/state yang tercatat dan lifecycle exit tetap deterministik.

**Resolution:** Terkonfirmasi untuk state/lifecycle: tiga protective exit menutup legacy tetapi tidak normalized ledger, lalu ghost exposure mengubah entry risk decisions. Bagian stochastic flip-flop tidak terkonfirmasi dan dipisahkan ke Hypothesis 2.

### Hypothesis 2: Model/policy berosilasi pada input pasar yang sama

**Status:** Open

**Theory:** Threshold, model, atau regime classifier menghasilkan BUY/HOLD/SELL bolak-balik tanpa perubahan fitur material.

**Supporting indicators:** Multi-source price fetch, threshold diskrit, state stabilisasi in-memory, dan beberapa gate fail-open menyediakan mekanisme yang memungkinkan oscillation.

**Would confirm:** Snapshot berurutan dengan feature vector/config/version setara tetapi terminal decision berbeda di luar hysteresis yang didefinisikan.

**Would refute:** Replay snapshot identik deterministik dan seluruh perubahan keputusan dijelaskan oleh perubahan input/state tercatat.

**Resolution:** Belum dapat diuji pada target 72 jam karena snapshot lengkap tidak dipersist.

### Hypothesis 3: Restart adalah penyebab utama tiga ghost positions

**Status:** Refuted

**Theory:** Restart kehilangan state exit lalu membuat normalized ledger tertinggal.

**Supporting indicators:** PriceMonitor menyimpan trailing, partial flags, dan created_at di memori.

**Would confirm:** Normalized divergence baru muncul pada boundary restart tanpa protective exit legacy.

**Would refute:** Divergence muncul langsung ketika protective exit legacy dipersist melalui jalur yang tidak menulis normalized SELL.

**Resolution:** DB/log menunjukkan divergence dibentuk oleh TP/SL/trailing legacy-only. Restart memperburuk reproducibility dan protection, tetapi bukan penyebab persistence split.

### Hypothesis 4: Atomic canonical close belum tersedia saat insiden

**Status:** Refuted

**Theory:** Protective exit memakai legacy close karena API atomic belum dibuat.

**Supporting indicators:** Codebase brownfield berevolusi cepat.

**Would confirm:** Ketiga exit mendahului commit yang memperkenalkan atomic close.

**Would refute:** Atomic close sudah ada pada deployed commit sebelum tanggal exit.

**Resolution:** `close_atomic_dryrun_position` masuk pada commit `4186615` tanggal 12 Agustus; exit terjadi 18–19 Agustus. Masalahnya adalah wiring, bukan ketiadaan API.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | --- | --- |
| Snapshot fitur/gate lengkap per scan | Menentukan apakah flip-flop policy rasional | Instrumentasi decision snapshot baru diperlukan |
| Event exit untuk tiga posisi | Menentukan apakah exit gagal atau belum terpicu | Rekonstruksi fills, position timestamps, price history, log monitor |
| Outcome rejected candidates | Mengukur stabilitas dan kualitas keputusan | Audit outcome worker dan label horizon |
| Persisted exit-policy state | Reproduksi deterministik pasca-restart tidak mungkin | Persist immutable SL/TP/time deadline/high-water/partial flags |
| Harga age/source/bid/last per exit | Bedakan policy instability dari input inconsistency | Tambahkan structured decision snapshot |

## Source Code Trace

| Element | Detail |
| --- | --- |
| Entry decision split | `advanced_crypto_bot/signals/signal_pipeline.py:424`; `advanced_crypto_bot/autotrade/runtime.py:1145` |
| Exit trigger | `advanced_crypto_bot/autotrade/price_monitor.py:443` |
| Legacy-only close | `advanced_crypto_bot/autotrade/price_monitor.py:499`; `advanced_crypto_bot/core/database.py:1088` |
| Canonical atomic close tersedia | `advanced_crypto_bot/core/database.py:1852`; dipakai signal SELL di `advanced_crypto_bot/autotrade/runtime.py:2488` |
| Canonical poll tanpa lifecycle restore | `advanced_crypto_bot/workers/price_poller.py:125`; rebuild hanya legacy di `advanced_crypto_bot/autotrade/price_monitor.py:82` |
| Concurrent exit paths | `advanced_crypto_bot/workers/price_poller.py:368`; `advanced_crypto_bot/bot.py:2142` |

## Conclusion

**Confidence:** High untuk akar Out Trade; Medium untuk keseluruhan In Trade

Akar Out Trade terkonfirmasi sebagai split persistence path: protective exits PriceMonitor hanya menutup legacy ledger. Dampaknya merambat ke In Trade melalui canonical equity/drawdown. Split semantic entry juga terkonfirmasi, tetapi oscillation model pada input identik belum dapat dinilai tanpa decision snapshots.

## Recommended Next Steps

### Diagnostic

Inventaris evidence VM/source, lalu rekonstruksi timeline dan ukur flip-rate sebelum mengubah threshold atau strategi.

## Reproduction Plan

Belum ditetapkan.

## Side Findings

- Patch taxonomy `PAIR_LOSS_STREAK` sudah ada lokal pada `de49a1d`, belum dipush/deploy.
- Service VM aktif pada `cdcb9a4`, `NRestarts=0`; empat stop/start operator/systemd terjadi 24 Agustus.
- Literatur primer mendukung online calibration pada non-IID data, explicit change detection, dan no-trade/hysteresis bands sebagai kontrol turnover; belum ada dasar untuk langsung memasangnya sebelum truth layer disatukan.

## Follow-up: 2026-08-24

### New Evidence

- User menetapkan perubahan arah: AutoTrade lama dianggap gagal menunjukkan performa yang baik dan akan diganti secara fundamental, bukan ditambal melalui tuning threshold.
- Target sistem baru adalah keputusan terkalibrasi dan net-profitable secara out-of-sample setelah seluruh biaya; tidak ada klaim metode yang pasti paling akurat pada pasar non-stasioner.

### Backlog Changes

- Investigasi diagnosis dibekukan sebagai input PRD replacement.
- Workflow `bmad-correct-course` belum dapat dijalankan karena PRD dan epics AutoTrade belum tersedia.
- Workflow `bmad-prd` Create sudah diaktifkan; belum ada workspace/draft karena menunggu brain dump produk dari user.
- Setelah PRD final: buat epics, architecture replacement, migration plan, lalu implementation readiness review.

### Updated Conclusion

Sistem lama tidak layak menjadi fondasi lifecycle baru karena entry tidak mempunyai satu canonical decision dan exit tidak mempunyai satu canonical persistence path. Besok pagi dilanjutkan dari brain dump PRD, dengan real trading tetap nonaktif.
