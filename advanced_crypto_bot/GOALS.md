# 🎯 GOALS — Advanced Crypto Trading Bot

**Dibuat:** 2026-05-24
**Versi Bot:** v6.6.0
**Status:** DRY RUN (belum siap real trading)

---

## 🏆 GOAL IT BESAR

**Menjadi sistem trading crypto otomatis yang profitable dan reliable di Indodax, dengan risiko terkontrol dan minimal intervensi manusia.**

Target akhir: Bot bisa menghasilkan profit konsisten 5-15%/bulan di real trading dengan max drawdown ≤10%.

---

## 📍 POSISI SAAT INI vs TARGET

| Aspek | Saat Ini | Target | Gap |
|-------|----------|--------|-----|
| **Mode Trading** | DRY RUN (simulasi) | Real Trading (Scalper + AutoTrade) | Belum siap |
| **Distribusi Sinyal** | BUY 6.9%, SELL 23%, HOLD 70% | BUY 12-18%, SELL 12-18%, HOLD 64-76% | ML bias bearish |
| **Win Rate** | Belum terukur (DRY RUN) | ≥55% | Perlu data real |
| **Risk/Reward** | Belum terukur | ≥1.5:1 per trade | Perlu MTF + BTC filter |
| **Max Drawdown** | 10% (config fraction `0.10`) | ≤10% | Sudah sesuai target; perlu validasi live/DRY RUN |
| **Uptime** | ~95% (memory restart) | ≥99% | Memory leak fix |
| **False Signal Rate** | ~30-50% (estimasi tanpa MTF) | ≤15% | MTF + BTC Correlation |
| **Latency** | REST polling 60s | ≤10s (WebSocket) | Indodax WS unstable |

---

## 🗺️ ROADMAP MENUJU REAL TRADING

### PHASE 1: STABILISASI & KUALITAS SINYAL (Minggu Ini)
> Goal: Sinyal seimbang dan error-free selama 5 hari berturut-turut

- [x] Fix `set_auto_trade_mode()` AttributeError ✅ (verified 2026-06-09 — method ada di `database.py:1449`, log 0 error)
- [x] Retrain ML model dengan `class_weight='balanced'` ✅ (done 2026-06-09 — V2 corrupt scaler 47 vs features 58, retrain ulang acc 62.6%)
- [x] Database indexes + WAL checkpoint ✅ (verified 2026-06-09 — indexes lengkap di `database.py:442-447` + `signal_db.py:137-149`, WAL+checkpoint method tersedia)
- [x] Threading lock di notification ✅ (verified 2026-06-09 — `signal_queue` cooldown dedup di `bot.py:1316-1319`, log 0 duplikasi)
- [ ] Monitor distribusi sinyal 5 hari — validasi keseimbangan (perlu observasi setelah ML restored)
- [x] Fix Auto-sync `'str' object has no attribute 'get'` ✅ (done 2026-05-24)
- [x] Fix balance verification key `funds` → `balance` ✅ (done 2026-05-24)

#### Backlog dari Audit 2026-06-07 (Critical → harus fix sebelum DRY RUN data dianggap valid)

> Sumber: [`docs/archive/audit-autotrade-dryrun-profit-2026-06-07.md`](docs/archive/audit-autotrade-dryrun-profit-2026-06-07.md)

| # | Severity | Bug | File | Estimasi |
|---|----------|-----|------|----------|
| 1 | ✅ FIXED | ~~BTC price=100 IDR (data palsu dari API/cache)~~ — absolute price floor guard di `_is_price_sane_for_pair()` (BTC ≥100M, ETH ≥1M, BNB ≥100K, SOL ≥50K) | `runtime.py:189-219` | done 2026-06-08 |
| 2 | ✅ FIXED | ~~Amount inflasi 3x (SIZE→FILL mismatch)~~ — FILL reconciliation guard: DRY RUN cap (`DRY_RUN_MAX_TOTAL_IDR=2M`) + recompute `amount = total / entry_zone_price` di FILL boundary | `runtime.py:1016-1056` | done 2026-06-08 |
| 3 | ✅ FIXED | ~~Asyncio event loop mismatch~~ — cross-loop guard di `_get_cached_signal()` cek `task.get_loop() is asyncio.get_running_loop()` | `runtime.py:213-256` | done 2026-06-08 |
| 4 | ✅ FIXED | ~~HTML parse error 29x/jam — dynamic text tidak di-escape~~ — `core/telegram_html.py` sanitizer whitelist tag + proactive sanitize di `_send_message()` & `runtime.py` | `bot.py:2898+`, `autotrade/runtime.py:543+`, `core/telegram_html.py` | done 2026-06-08 |
| 5 | ✅ FIXED | ~~Trade review duplikat 4-8x per trade~~ — idempotency guard `SELECT 1 FROM trade_reviews WHERE trade_id = ?` di `create_trade_review()` skip kalau review existing | `database.py:1031-1049` | done 2026-06-08 |
| 6 | ✅ FIXED | ~~`os._exit(3)` tanpa cleanup~~ — `_shutdown(timeout=5)` + WAL `checkpoint_wal(TRUNCATE)` pada trading.db & signals.db sebelum hard exit | `bot.py:1199-1221` | done 2026-06-08 |
| 7 | ✅ FIXED | ~~TA Strength bias ke ±0.10 (67% sample)~~ — continuous tilt: RSI map [30..70]→[+0.5..-0.5], MACD base±0.3+histogram-tilt±0.4, MA distance-from-SMA20 tilt, BB %B-position tilt, Volume pct-change tilt | `analysis/technical_analysis.py:320-435` | done 2026-06-08 |
| 8 | ✅ FIXED | ~~Signal alert bocor ke test user ID (42, 123)~~ — `_filter_admin_ids()` di `core/config.py` reject hardcoded test IDs + log warning | `core/config.py:79-117` | done 2026-06-08 |
| 9 | ✅ FIXED | ~~Signal counter tidak increment (#1 terus)~~ — `cursor.lastrowid` dari `INSERT INTO signals` jalan, log saat ini menunjukkan ID berurutan #73646→#74326 (457 unique IDs) | `signal_db.py:170-217` | done 2026-06-08 |
| 10 | ✅ FIXED | ~~`_quant_cache` module-level dict tidak pernah di-clear~~ — diganti `_OrderedDict` LRU dengan `QUANT_CACHE_MAX_PAIRS` cap, eviction otomatis via `popitem(last=False)` | `signal_pipeline.py:32-66` | done 2026-06-08 |

**Catatan:**
- Bug #5-#10 sebagian dari **test data contamination** (user ID 42/123 = test fixture, bukan production). Perlu verifikasi ulang di log production murni.
- Bug #6 (TA Strength ±0.10) kemungkinan **normal untuk market sideways** — perlu validasi saat market trending.
- Total estimasi fix: **~6-9 jam** untuk semua item.
- **Prioritas:** Fix #1 (price guard) dan #3 (asyncio loop) dulu karena paling fatal dan paling cepat.

**Status:** Temuan dicatat, belum diperbaiki. Data DRY RUN saat ini memiliki noise dari bug #1 dan #2 — perlu cleanup DB sebelum evaluasi final.

#### Test Suite Status (2026-06-07)
```
Full suite: 411 passed, 46 failed (pre-existing), 10 warnings
- Core autotrade tests: ✅ ALL PASS (10+61 = 71 tests)
- 46 failures: test_scalper_auto_tpsl.py (28) + test_scalping_indicator_features.py (17) + test_performance_backfill.py (1)
  → Semua pre-existing (fitur scalper/indikator yang belum implemented), bukan regresi dari perubahan Kiro/Deepseek
```

**Kriteria Lulus Phase 1:**
- Zero critical error di log selama 48 jam
- Distribusi sinyal: BUY 10-20%, SELL 10-20%, HOLD 60-80%
- Semua 356+ tests passing

---

### PHASE 2: FILTER LANJUTAN (Minggu Depan)
> Goal: Eliminasi 50%+ false signals

- [ ] **Multi-Timeframe Analysis (MTF)** — cek trend di 4H/1D sebelum BUY di 1H
- [ ] **BTC Correlation Filter** — block BUY altcoin saat BTC downtrend
- [ ] **Wire microstructure.py** ke pipeline — order book depth sebagai konfirmasi
- [ ] **Session-Aware Filter** — kurangi sinyal di jam low-volume (00:00-06:00 WIB)
- [ ] **LRU cache historical_data** — cegah memory leak (max 50 pairs)

**Kriteria Lulus Phase 2:**
- False signal rate turun ≤20% (diukur dari DRY RUN outcomes)
- Memory stabil <1.5 GB selama 7 hari
- BUY signals di BTC downtrend = 0

---

### PHASE 3: VALIDASI DRY RUN (2 Minggu)
> Goal: Bukti statistik bahwa bot profitable di simulasi

- [ ] Jalankan AutoTrade DRY RUN penuh 14 hari tanpa intervensi
- [ ] Track semua trade outcomes (BUY→SELL cycle)
- [ ] Hitung: Win Rate, Avg Profit/Loss, Max Drawdown, Sharpe Ratio
- [ ] Bandingkan vs buy-and-hold BTC/ETH di periode yang sama
- [ ] Tune TP/SL berdasarkan data aktual (bukan asumsi)

**Kriteria Lulus Phase 3:**
- Win Rate ≥55% dari minimal 50 trades
- Net profit DRY RUN ≥3% dalam 14 hari
- Max drawdown ≤8%
- Sharpe Ratio ≥1.0

---

### PHASE 4: REAL TRADING BERTAHAP (Setelah Phase 3 Lulus)
> Goal: Transisi aman dari simulasi ke uang asli

- [ ] **Stage 1:** Scalper real dengan modal kecil (Rp 500K) — 1 pair saja, 7 hari
- [ ] **Stage 2:** Scalper real 3-5 pairs, modal Rp 2-5 juta — 14 hari
- [ ] **Stage 3:** Evaluasi: buka AutoTrade real JIKA Stage 2 profitable
- [ ] **Stage 4:** Full auto (AutoTrade + Hunter + Scalper) dengan modal terkontrol

**Kriteria per Stage:**
- Stage 1→2: Profit ≥1%, zero critical error
- Stage 2→3: Profit ≥3%, max drawdown ≤5%
- Stage 3→4: Profit ≥5%/bulan selama 2 bulan, max drawdown ≤8%

---

### PHASE 5: OPTIMASI & SCALE (Bulan 2-3)
> Goal: Maximize profit, minimize risk, scale up

- [ ] Walk-Forward Optimization — cegah ML overfitting
- [ ] Dynamic position sizing (Kelly Criterion dari data real)
- [ ] Multi-exchange support (Binance/Tokocrypto sebagai hedge)
- [ ] VPS deployment (Biznet/DigitalOcean) — uptime 99.9%
- [ ] Dashboard web real-time untuk monitoring
- [ ] Automated daily/weekly P&L report ke Telegram

---

## 🔑 KEY METRICS TO TRACK

### Trading Performance
| Metric | Target | Cara Ukur |
|--------|--------|-----------|
| Win Rate | ≥55% | Trades profit / total trades |
| Avg R:R | ≥1.5:1 | Avg profit per win / avg loss per loss |
| Max Drawdown | ≤10% | Peak-to-trough equity |
| Sharpe Ratio | ≥1.0 | (Return - Rf) / StdDev |
| Profit Factor | ≥1.5 | Gross profit / gross loss |
| Monthly Return | 5-15% | Net P&L / starting capital |

### System Health
| Metric | Target | Cara Ukur |
|--------|--------|-----------|
| Uptime | ≥99% | Total uptime / total time |
| Error Rate | ≤5/hari | Critical errors in log |
| Signal Latency | ≤5 detik | Time from price change to signal |
| Memory Usage | ≤1.5 GB | Peak RSS |
| API Success Rate | ≥99% | Successful API calls / total |

### Signal Quality
| Metric | Target | Cara Ukur |
|--------|--------|-----------|
| BUY Accuracy | ≥60% | BUY signals yang profit / total BUY |
| SELL Accuracy | ≥60% | SELL signals yang benar / total SELL |
| False Signal Rate | ≤15% | Signals yang langsung reversal |
| Signal Balance | BUY 12-18% | Distribusi per 24 jam |

---

## ⚠️ RISIKO & MITIGASI

| Risiko | Probabilitas | Mitigasi |
|--------|-------------|----------|
| ML overfit → sinyal bagus di backtest, buruk di live | TINGGI | Walk-forward validation, out-of-sample test |
| Flash crash → SL tidak tereksekusi tepat waktu | MEDIUM | Polling 10s (bukan 60s), circuit breaker |
| Indodax API down | MEDIUM | Graceful degradation, pause trading |
| Bot crash saat posisi terbuka | MEDIUM | Redis state persistence, auto-recovery |
| Regulatory change (crypto ban) | LOW | Diversifikasi exchange, monitor berita |

---

## 🚫 ANTI-GOALS (Yang TIDAK Akan Dilakukan)

- ❌ High-frequency trading (HFT) — Indodax tidak support, latency terlalu tinggi
- ❌ Leverage/margin trading — terlalu berisiko untuk bot otomatis
- ❌ Trading >20 pairs sekaligus — fokus quality over quantity
- ❌ 100% hands-off tanpa monitoring — selalu ada human oversight
- ❌ Mengejar return >30%/bulan — unrealistic, mengarah ke over-leverage

---

## 📊 DECISION LOG

| Tanggal | Keputusan | Alasan |
|---------|-----------|--------|
| 2026-05-24 | Tetap DRY RUN sampai Phase 3 lulus | ML bias belum fix, belum ada MTF |
| 2026-05-24 | Scalper = satu-satunya jalur real money | Safety-first, human confirmation |
| 2026-05-24 | Target 5-15%/bulan (bukan 30%+) | Realistic, sustainable, low risk |
| 2026-05-24 | Prioritas fix ML sebelum tambah fitur | Garbage in = garbage out |

---

## 📅 TIMELINE ESTIMASI

```
Minggu 1 (24-31 Mei):     Phase 1 — Stabilisasi + ML retrain
Minggu 2 (1-7 Juni):      Phase 2 — MTF + BTC filter
Minggu 3-4 (8-21 Juni):   Phase 3 — Validasi DRY RUN 14 hari
Minggu 5-6 (22 Juni-5 Juli): Phase 4 Stage 1-2 — Real trading kecil
Bulan 2-3 (Juli-Agustus):  Phase 4 Stage 3-4 + Phase 5 — Scale up
```

**Estimasi konservatif sampai full real trading: 6-8 minggu.**

---

*Dokumen ini di-update setiap kali ada milestone tercapai atau keputusan strategis baru.*
