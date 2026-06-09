# 🔍 Audit Komprehensif — AutoTrade DRY RUN Profit/Loss Analysis
> **Tanggal Audit:** 7 Juni 2026
> **Auditor:** Hermes Agent (via session)
> **Status:** Investigasi selesai — **0 perubahan kode dilakukan**
> **Cakupan:** `bot.py` (10.314 baris), `autotrade/runtime.py` (1.715 baris), `core/config.py` (326 baris), log (13.545 baris), `analisys_autotradedrurun.md`, `ARCHITECTURE.md`, `GOALS.md`, `COMMANDS.md`

---

## 📊 Ringkasan Eksekutif

Dari audit menyeluruh ditemukan **12 temuan**:
- 🔴 **4 Critical** — bug yang membuat hasil DRY RUN **tidak bisa dipercaya**
- 🟠 **4 High** — bug yang mengurangi profitabilitas atau menghasilkan false signal
- 🟡 **3 Medium** — inefficiency atau noise
- 🟢 **1 Info** — observasi desain

**Kesimpulan utama: DRY RUN saat ini TIDAK menghasilkan data valid untuk evaluasi profitabilitas karena 4 bug critical yang mencemari data simulasi.**

---

## 🔴 CRITICAL #1: BTC Harga 100 IDR — Data Palsu Mencemari Simulasi

### Lokasi
`autotrade/runtime.py:889-899` — `check_trading_opportunity()` fresh price fetch

### Bukti dari Log (2026-06-07)
```
🔄 Fresh execution price for btcidr: 100.0
🧪 [DRY RUN SIZE] btcidr: using tier nominal 1,250,000 IDR at price 100 => amount=12500.0
🧪 [DRY RUN] Filled LIMIT BUY for btcidr: 12500.0 @ 100
🧪 [DRY RUN] Simulated SELL for btcidr: 12500.0 @ 109.89, P&L=+9.78%
```

### Analisis
- BTC seharusnya ~1.500.000.000 IDR, bukan 100 IDR
- **4 trade BTC** dieksekusi di harga 100, menghasilkan +9.78% P&L palsu
- Signal pipeline sebelumnya fetch BTCIDR @ 389 IDR — tapi runtime fetch ulang dan dapat 100
- `[ADAPTIVE] btcidr: win_rate=100.0%` — adaptive learning mengira BTC profitable 100%
- Ini mencemari ML V4 dan Adaptive Learning dengan data palsu

### Root Cause (hipotesis)
1. **Test data contamination** — fixture test `price=100` untuk `btcidr` bocor ke production DB/API cache
2. **API returning stale/wrong data** — `IndodaxAPI().get_ticker("btcidr")` return 100 bukannya harga real
3. **Race condition di price cache** — value dari test run tidak terhapus

### Dampak Profit/Loss
- 🔴 **Fatal** — simulated P&L +9.78% dari harga 100 tidak ada artinya
- Semua metrik win rate BTC (100%) adalah **palsu**

---

## 🔴 CRITICAL #2: Jumlah Koin Melonjak 2.5x–3x antara SIZE dan FILL

### Bukti dari Log
```
Pair         SIZE amount    FILL amount    Inflasi
xlmidr       330.69         988.40         3.0x ⚠️
xrpidr        63.40         196.65         3.1x ⚠️
adaidr       435.24        1138.39         2.6x ⚠️
bnbidr         0.119          0.301        2.5x ⚠️
```

### Analisis
- DRY RUN SIZE menghitung 1.250.000 IDR / `current_price`
- Setelah SIZE log, berbagai pengali diterapkan: exploration (×0.5), momentum (×0.7), V4 (×0.5), RL (×0.5), elite (×0.5) — semuanya **mengurangi**, bukan menambah
- Tapi di FILL, jumlah koin justru **3x lebih besar**
- Safety guard (`runtime.py:1073-1077`) reset ke 1.000.000 IDR jika amount ≤ 0, tapi ini tetap tidak menjelaskan 3x inflasi

### Hipotesis Root Cause
- **Bayesian Kelly Override** (`runtime.py:844-861`) bisa meng-inflate position size jika Kelly engine menilai setup sangat bagus — tapi tidak ada log Kelly untuk trade-trade ini
- **Kemungkinan bug di `amount` variable scope** — variable `amount` di-overwrite di tempat yang tidak terduga
- **Multiple exploration overrides bertabrakan** — `_exploration_factor_override` bisa di-set beberapa kali dengan nilai berbeda

### Dampak Profit/Loss
- 🔴 **Fatal** — P&L simulated tidak bisa dipercaya karena jumlah koin salah
- Risk exposure simulated 3x lebih besar dari yang seharusnya

---

## 🔴 CRITICAL #3: Asyncio Event Loop Mismatch — Trade Execution Gagal

### Bukti dari Log (`errors.log`)
```
❌ [SQ-WORKER] Trade execution failed: Task <Task pending name='Task-354' 
coro=<check_trading_opportunity()>> got Future <Task pending name='Task-353' 
coro=<generate_signal_for_pair()>> attached to a different loop
```

### Analisis
- Signal queue worker berjalan di event loop berbeda dengan signal pipeline
- `generate_signal_for_pair()` membuat Future di loop A, tapi `check_trading_opportunity()` menunggu di loop B
- Result: **trade execution gagal total** — sinyal sudah dihasilkan tapi tidak bisa dieksekusi
- Terjadi 2x dalam log terbaru (Task-354 + Task-358)

### Dampak Profit/Loss
- 🔴 **Fatal** — potensi trade yang valid tidak pernah tereksekusi
- Invisible failure: signal dihasilkan, dikirim ke Telegram, tapi trading logic crash diam-diam

---

## 🔴 CRITICAL #4: HTML Parse Error — Notifikasi Telegram Gagal

### Bukti dari Log (`errors.log`)
```
_send_message failed: Can't parse entities: can't find end of the entity 
starting at byte offset 584

_send_message failed: Can't parse entities: can't find end of the entity 
starting at byte offset 1453

_send_message failed: Can't parse entities: can't find end of the entity 
starting at byte offset 1609
```

### Analisis
- **29 error** dalam 1 jam (00:01–01:13)
- Pesan format HTML gagal diparse — unclosed tag, karakter khusus, atau nested entity
- User/admin **tidak menerima notifikasi** sinyal dan trade
- Offset byte berbeda (584, 1453, 1609) menunjukkan multiple message template bermasalah

### Dampak Profit/Loss
- 🔴 **Fatal untuk monitoring** — admin tidak tahu trade yang terjadi
- Jika ini terjadi di real trading, trader tidak bisa intervensi saat dibutuhkan

---

## 🟠 HIGH #5: Sinyal Duplikat — Resource Terbuang

### Bukti dari Log
```
00:18:44  STRONG_BUY BTCIDR ml_conf=83%
00:18:51  STRONG_BUY BTCIDR ml_conf=83%  (7 detik kemudian!)
00:18:52  STRONG_BUY BTCIDR ml_conf=83%  (1 detik lagi!)
00:18:53  BUY BTCIDR ml_conf=72%
00:18:53  BUY BTCIDR ml_conf=66%
```

### Analisis
- 5 sinyal untuk pair yang sama dalam **9 detik**
- Signal queue tidak punya deduplication yang efektif
- Decision layer mendeteksi duplikasi (`[DECISION DUPLICATE] BUY → HOLD`) tapi signal tetap diproses
- Resource CPU, API call, dan DB write terbuang percuma

### Dampak
- 🟠 Rate limit risk ke Indodax API
- False confidence: ML model memberikan sinyal berbeda (83%, 72%, 66%) dalam hitungan detik

---

## 🟠 HIGH #6: TA Strength Stuck di ±0.10 — Indikator Teknikal Tidak Berfungsi

### Bukti dari Log
```
renidr:    TA Strength: 0.10
tnsridr:   TA Strength: 0.10
pythidr:   TA Strength: -0.10
jellyjellyidr: TA Strength: 0.10
chillguyidr: TA Strength: -0.10
```

### Analisis
- **Setiap sinyal** memiliki TA Strength **0.10 atau -0.10** — tidak ada variasi
- Technical analysis seharusnya menghasilkan nilai kontinu, bukan binary ±0.10
- Kemungkinan: bug di normalisasi atau threshold yang terlalu simplistik
- Akibat: decision layer dan signal quality tidak bisa membedakan setup bagus vs buruk

### Dampak
- 🟠 Semua BUY signal terlihat sama dari sisi TA — tidak ada diferenciasi kualitas

---

## 🟠 HIGH #7: Signal Alert Bocor ke Admin Test

### Bukti dari Log
```
📢 Signal alert sent to admin 42 for btcidr: BUY (70.0%)
📢 Signal alert sent to admin 123 for btcidr: STRONG_SELL (90.0%)
📢 Signal alert sent to admin 256024600 for vvvidr: SELL (83.3%)
```

### Analisis
- `admin 42` dan `admin 123` adalah **test user IDs** (dari log: `🔒 Telegram registration rejected user=42`, `Telegram access denied user=42`)
- Bot tetap mengirim signal alert ke user yang sudah ditolak aksesnya
- Bug di `_broadcast_to_subscribers` atau di signal notification path — tidak mengecek authorization sebelum kirim

### Dampak
- 🟠 Telegram API waste — kirim pesan ke user yang tidak ada/ditolak
- Potensi rate limit Telegram

---

## 🟠 HIGH #8: Trade Review Duplikat Masif

### Bukti dari Log
```
📝 Trade review created for trade 1 (btcidr): ✅ Trade profitable (+10.00%)  ← 8x!
📝 Trade review created for trade 9 (badpair): ❌ Trade loss (-10.00%)       ← 10x!
```

### Analisis
- Setiap trade review dibuat **4-8 kali** untuk trade yang sama
- Disebabkan oleh multiple code path yang memanggil review creation
- Trade 1-8 (btcidr) direview 8x, Trade 9-18 (badpair) direview 10x

### Dampak
- 🟠 DB bloat — redundant rows
- False signal untuk adaptive learning: trade yang sama dihitung berkali-kali

---

## 🟡 MEDIUM #9: Signal Counter Tidak Increment

### Bukti
```
💾 Signal #1 saved: BTCIDR - STRONG_BUY @ 389.0 IDR
💾 Signal #1 saved: BTCIDR - HOLD @ 388.0 IDR
💾 Signal #1 saved: BTCIDR - STRONG_BUY @ 389.0 IDR
💾 Signal #1 saved: BTCIDR - BUY @ 388.0 IDR
```

Semua signal tersimpan sebagai `Signal #1` — counter tidak naik.

---

## 🟡 MEDIUM #10: Entry Masih Diblokir 9x meski Parameter Sudah Dilonggarkan

### Bukti
```
🚫 Entry blocked for btcidr: skip-trade-execution-for-test
⚠️ Trading blocked for btcidr: blocked (3x)
🚫 Decision-layer blocked execution for btcidr: momentum belum konfirmasi
```

9 entry diblokir meskipun parameter filter sudah direlax (analisys 2026-06-06).

---

## 🟡 MEDIUM #11: `os._exit(3)` Tanpa Cleanup — Risiko SQLite Corrupt

### Lokasi
`bot.py:1109` — exit code path menggunakan `os._exit(3)`

Tanpa cleanup DB, bisa corrupt `trading.db` dan `signals.db`.

---

## 🟢 INFO #12: Arsitektur Gate Masih 10+ — Throughput Sangat Rendah

Setelah parameter relaxation (2026-06-06), flow masih:
```
Signal pipeline → Decision layer → MI filter → Regime → Position size →
Exploration → Kelly → Momentum → Chase prevention → Correlation → V4 →
SL/TP → S/R → RL → Elite signal → Fee-aware R/R → Profit optimizer →
Entry zone → Fill logic
```

**Statistik:** Hanya 11 fill dari 13.545 baris log. Ini setara dengan <0.1% throughput.

---

## 📋 Ringkasan Semua Temuan

| # | Severity | Temuan | Lokasi | Dampak Profit/Loss |
|---|----------|--------|--------|-------------------|
| 1 | 🔴 CRITICAL | BTC @ 100 IDR — data palsu | `runtime.py:889-899` | Win rate BTC 100% palsu, adaptive learning terkontaminasi |
| 2 | 🔴 CRITICAL | Amount 3x inflasi SIZE→FILL | `runtime.py:807 vs 1180` | P&L simulated tidak valid |
| 3 | 🔴 CRITICAL | Asyncio event loop mismatch | `runtime.py:551,573` | Trade execution gagal total |
| 4 | 🔴 CRITICAL | HTML parse error 29x/jam | `bot.py:2819-2857` | Notifikasi Telegram tidak terkirim |
| 5 | 🟠 HIGH | Sinyal duplikat 5x/9detik | `signal_pipeline.py` | Resource waste, rate limit risk |
| 6 | 🟠 HIGH | TA Strength stuck ±0.10 | `signal_pipeline.py` | Semua sinyal terlihat sama |
| 7 | 🟠 HIGH | Signal alert ke test user | `runtime.py:668-678` | Telegram API waste |
| 8 | 🟠 HIGH | Trade review duplikat 8x | `database.py:1091` | DB bloat, learning terkontaminasi |
| 9 | 🟡 MEDIUM | Signal counter tidak naik | `signal_pipeline.py:984` | Tracking tidak akurat |
| 10 | 🟡 MEDIUM | 9 entry diblokir pasca-relax | `runtime.py` | Throughput tetap rendah |
| 11 | 🟡 MEDIUM | `os._exit(3)` no cleanup | `bot.py:1109` | SQLite corruption risk |
| 12 | 🟢 INFO | 10+ gate serial = 0.1% throughput | `runtime.py:523-1272` | Hampir tidak ada trade |

---

## ⚠️ Apakah Ada Profit di DRY RUN?

**Jawaban: Tidak relevan untuk dinilai saat ini.**

DRY RUN menghasilkan:
- 11 BUY simulated (beberapa dengan harga/data palsu)
- 2 SELL simulated (1 profit palsu +9.78%, 1 loss -1.23%)
- **P&L tidak bisa dipercaya** karena bug #1 dan #2

Bahkan jika tidak ada bug, secara desain DRY RUN adalah **simulasi tanpa uang asli** — "profit" di sini hanya metrik evaluasi, bukan uang riil. GOALS.md Phase 3 menargetkan validasi DRY RUN 14 hari dengan win rate ≥55% — tapi dengan bug yang ada, data validasi **tidak bisa diandalkan**.

---

## 📁 File yang Perlu Diperbaiki (Jika Disetujui)

| Priority | File | Bug | Estimasi |
|----------|------|-----|----------|
| 1 | `autotrade/runtime.py:889-899` | Fix BTC price=100 (investigasi sumber data palsu) | 1-2 jam |
| 2 | `autotrade/runtime.py:807-1180` | Debug amount inflasi (trace variable mutation) | 2-4 jam |
| 3 | `autotrade/runtime.py:551` | Fix asyncio event loop (gunakan loop yang sama) | 2-3 jam |
| 4 | `bot.py:2819` | Fix HTML parse entities (sanitize output) | 1 jam |
| 5 | `signals/signal_pipeline.py` | Fix TA Strength (debug stuck value) | 1-2 jam |
| 6 | `signals/signal_pipeline.py` | Fix deduplication (cooldown/tracking) | 1 jam |
| 7 | `bot.py:1109` | Replace `os._exit(3)` dengan graceful shutdown | 30 min |

**Total estimasi: 9-14 jam engineering time.**

---

## ⚡ Rekomendasi Sebelum Perbaikan

1. **Jangan analisis profit DRY RUN sampai bug #1-#4 diperbaiki** — data saat ini tidak valid
2. **Bersihkan database** dari data palsu (BTC @ 100, trade duplikat) sebelum melanjutkan
3. **Pisahkan test database dari production database** — pastikan test fixture tidak bocor
4. **Jalankan ulang DRY RUN bersih** minimal 7 hari setelah perbaikan untuk dapat data valid
5. **Pertimbangkan simplification** — 10+ gate serial mungkin perlu direduksi untuk dapat throughput yang bermakna

---

*Laporan ini **tidak melakukan perubahan kode apapun**. Semua temuan berdasarkan inspeksi statis source code dan analisis log aktual.*
