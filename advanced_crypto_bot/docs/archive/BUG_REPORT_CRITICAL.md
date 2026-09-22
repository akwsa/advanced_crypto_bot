# BUG REPORT — CRITICAL & HIGH Severity
### Audit: 2026-05-19 | Re-Audit #2: 2026-05-19

Dokumen hasil audit 3x penuh codebase. Mencakup **bot.py** (9704 lines) + seluruh module (`core/`, `analysis/`, `signals/`, `autotrade/`, `bot_parts/`).

**Status:** ✅ FIXED | ❌ STILL BROKEN | 🟡 PARTIAL | ⬚ NOT RE-CHECKED

---

## ═══════════════════════════════════════
## CURRENT STATUS — Verified 2026-05-20
## ═══════════════════════════════════════

> **Authoritative update:** Bagian "Still Broken" di bawah adalah catatan audit lama
> yang belum di-rebase. Verifikasi kode per 2026-05-20 menunjukkan semua item
> CRITICAL dan HIGH yang tercantum di laporan ini sudah fixed atau guarded.

| ID | Status | Verifikasi/Fix Terkini |
|---|---|---|
| C1 | ✅ FIXED | `core/config.py` dan `core/signal_enhancement_config.py` memakai safe env parser. |
| C2 | ✅ FIXED | `MAX_DRAWDOWN_PCT = 0.10` dipertahankan sebagai rasio 10%; perbandingan drawdown juga rasio. |
| C3 | ✅ FIXED | RSI divergence memakai Wilder smoothing, bukan `np.convolve`. |
| C4 | ✅ FIXED | `autotrade/runtime.py` memakai fallback harga dari signal → WS cache → API. |
| C5 | ✅ FIXED | `analysis/ml_model_v3.py` menghitung target quantile dari training slice. |
| C6 | ✅ FIXED | `analysis/ml_model_v4.py` memakai deterministic `md5` symbol hash. |
| C7 | ✅ FIXED | `analysis/signal_analyzer.py` menjaga lifecycle connection/cursor tetap valid. |
| C8 | ✅ FIXED | `signals/signal_quality_engine.py` menerima `current_price` real-time dari pipeline untuk Mean Reversion, fallback ke close terakhir. |
| H1-H2 | ✅ FIXED | `core/database.py` guard kolom lama dan `original_total is not None`. |
| H3 | ✅ FIXED | `autotrade/runtime.py` validasi hasil `calculate_position_size` sebelum scaling. |
| H4 | ✅ FIXED | `analysis/ml_signal_trainer.py` menutup koneksi via `finally`. |
| H5-H6 | ✅ FIXED | `analysis/ml_model_v4.py` win rate dari ground truth dan `LabelEncoder.fit(CLASSES)`. |
| H7 | ✅ FIXED | `analysis/support_resistance.py` guard `bin_size <= 0`. |
| H8-H9 | ✅ FIXED | `bot_parts/microstructure.py` safe float parser dan chunk minimum 1. |
| H10 | ✅ FIXED | `analysis/ml_model_v2.py` path V2 stabil, tidak append `_v2` berulang. |
| H11 | ✅ FIXED | `autotrade/risk_manager.py` tahan `None` pada total open trades. |
| H12 | ✅ FIXED | `signals/signal_filter_v2.py` truncates `validation_history`. |
| EXTRA | ✅ FIXED | `signals/signal_formatter.py` SyntaxError f-string dibetulkan. |
| EXTRA | ✅ FIXED | Modul quant punya fallback tanpa SciPy untuk VPS minimal; quant command import tahan tanpa Telegram package saat test. |

**Verification commands (2026-05-20):**
- `python -m py_compile ...` untuk file CRITICAL/HIGH terkait: ✅ pass
- `python -m unittest tests.test_bug_fixes_verification -v`: ✅ OK (dependency opsional di-skip jika tidak terpasang)
- `python -m unittest tests.test_quant_new_features -v`: ✅ 68/68 OK
- `python -m unittest tests.test_quant_integration.TestSignalFormatterQuant tests.test_quant_integration.TestVaRCVaRGate -v`: ✅ OK

**Known environment-only test blockers:**
- Full discovery masih membutuhkan paket opsional `python-telegram-bot` dan `matplotlib` untuk beberapa test Telegram/chart.
- Ini bukan regresi dari item CRITICAL/HIGH di laporan ini.

---

## ═══════════════════════════════════════
## STATUS UPDATE — Re-Audit #2
## ═══════════════════════════════════════

### ✅ Bugs yang sudah FIXED (post-audit #1 dan #2)

| # | Bug | File | Fix Detail |
|---|-----|------|-------------|
| F1 | Health monitor `sys.exit` thread issue | `bot.py:942` | `sys.exit(3)` → `os._exit(3)` |
| F2 | Quant cache recompute tiap signal | `signal_pipeline.py:26` | `_quant_cache` dict per pair TTL 5min |
| F3 | GARCH/VaR/ARIMA enrichment | `signal_pipeline.py:682-750` | Full quant enrichment pipeline |
| F4 | ARIMA direction filter | `signal_pipeline.py:793-811` | Block BUY if ARIMA predicts DOWN |
| F5 | VaR/CVaR thresholds terlalu tinggi | `trading_engine.py:264-283` | Adjusted ke -3%/-5% candle scale |
| F6 | GARCH regime scaling | `trading_engine.py:410-438` | Position size scaling by GARCH regime |
| F7 | Kelly ZeroDivision | `trading_engine.py:719-722` | avg_win_pct/avg_loss_pct minimum guards |
| F8 | Mean Reversion enrichment | `signal_pipeline.py:438-463` | MR z-score langsung di pipeline |
| F9 | **signal overwrite recommendation | `trading_engine.py:597-618` | Order dibalik: `**signal` sekarang SEBELUM explicit keys → `HOLD` menang |
| F10 | `min_confidence_for` NameError | `signal_pipeline.py:17` | Ditambahkan ke import list |
| F11 | `check_volatility_filter` no pair param | `signal_quality_engine.py:156` | Ditambah `pair: Optional[str] = None` |
| F12 | `check_volatility_filter` call no pair | `signal_pipeline.py:375` | Call sekarang `check_volatility_filter(df, pair=pair)` |
| F13 | Bare `except:pass` di pipeline | `signal_pipeline.py:377-378` | Sekarang log error: `logger.warning(...)` |
| F14 | `logger` undefined di ml_model | `ml_model.py:20` | Ditambah `logger = logging.getLogger("crypto_bot")` |
| F15 | `close_trade` None entry_price | `database.py:595-614` | None guard: validasi + return False jika invalid |

### ✅ Status Tambahan — Patch Implementasi Lanjutan (2026-05-19)

> **Catatan penting:** bagian lama di bawah dipertahankan sebagai historical audit trail.
> Status authoritative ada di **CURRENT STATUS — Verified 2026-05-20**.

| ID | Status Terbaru | Ringkasan |
|---|---|---|
| C1 | ✅ FIXED | Safe env parser ditambahkan di `core/config.py` + `core/signal_enhancement_config.py` |
| C2 | ✅ FIXED (clarified) | `MAX_DRAWDOWN_PCT = 0.10` dipertahankan sebagai **rasio 10%** + komentar diperjelas |
| C3 | ✅ FIXED | RSI engine di `signal_enhancement_engine` diganti ke Wilder smoothing |
| C4 | ✅ FIXED | `autotrade/runtime.py` pakai safe price fallback (`signal/ws/api`) tanpa KeyError |
| C5 | ✅ FIXED | `ml_model_v3.py` quantile target pakai training slice (hindari lookahead leakage) |
| C6 | ✅ FIXED | `ml_model_v4.py` symbol hash jadi deterministic (`md5`) |
| C7 | ✅ FIXED | `signal_analyzer.py` lifecycle connection/cursor diperbaiki |
| C8 | ✅ FIXED | MR `current_price` fallback dari close terakhir jika key price tidak ada |
| H2 | ✅ FIXED | `original_total` check jadi `is not None` (tidak pakai falsy check) |
| H3 | ✅ FIXED | Guard hasil `calculate_position_size` sebelum scaling (hindari `None * float`) |
| H4 | ✅ FIXED | `ml_signal_trainer.py` pakai `finally` untuk `conn.close()` |
| H5 | ✅ FIXED | `ml_model_v4.py` win rate dihitung dari `test_labels` (ground truth) |
| H6 | ✅ FIXED | `LabelEncoder` distabilkan dengan `fit(CLASSES)` |
| H7 | ✅ FIXED | `support_resistance.py` guard `bin_size <= 0` sebelum `np.arange` |
| DB-L1 | ✅ FIXED | `VACUUM` dipindah ke koneksi dedicated (outside transaction) |
| DB-L2 | ✅ FIXED | `timeout=30s`, `busy_timeout`, WAL tuning ditambahkan (`core/database.py`, `signals/signal_db.py`) |
| ML-B1 | ✅ TUNED | Threshold BUY/SELL dibuat asymmetric profit-oriented (SELL lebih ketat untuk kurangi bias bearish) |
| ML-B2 | ✅ TUNED | V4 soft-filter: `STRONG_SELL` didowngrade saat V4 `NEUTRAL_*`; SELL lemah bisa di-hold |

---

## ═══════════════════════════════════════
## 🔴 HISTORICAL — CRITICAL Findings From Old Audit (now fixed/guarded)
## ═══════════════════════════════════════

---

### ✅ C1. `core/config.py` + `core/signal_enhancement_config.py` — Env var crash startup
**File:** `core/config.py` lines 35, 62, 67, 134-135, 159-160, 177-182, 201, 214  
**Juga:** `core/signal_enhancement_config.py` lines 35-63

Semua `float(os.getenv(...))` / `int(os.getenv(...))` di module level tanpa try/except.

**Dampak:** Satu env var non-numeric → `ValueError` → bot gagal startup tanpa error message jelas.

**Fix:** Safe env helper. Estimasi: 30 min.

---

### ✅ C2. `core/config.py` — MAX_DRAWDOWN_PCT 0.1%, bukan 10%
**File:** `core/config.py` line 79

```python
MAX_DRAWDOWN_PCT = 0.10  # Komentar: 10%
```

Nilai asli `0.10` = 0.1%. Circuit breaker trigger di drawdown 0.1% — auto-trade selalu mati.

**Fix aktual:** Dipertahankan sebagai `0.10` karena kode membandingkan drawdown sebagai rasio, bukan persen. Komentar diperjelas agar tidak dibaca sebagai 0.1%.

---

### ✅ C3. `core/signal_enhancement_engine.py` — RSI calculation salah (convolve)
**File:** `core/signal_enhancement_engine.py` lines 252-262

```python
avg_gain = np.convolve(gains, np.ones(period)/period, mode='full')[:len(prices)]
```

Harusnya EMA (Wilder's smoothing), bukan SMA via convolve. `mode='full'` + truncate = misalignment → divergensi palsu.

**Dampak:** Semua BUY/SELL dari enhancement engine tidak akurat. Divergence detection (fitur utama) memberikan sinyal palsu.

**Fix:** Rewrite dengan EMA. Estimasi: 30 min.

---

### ✅ C4. `autotrade/runtime.py` — KeyError di signal["price"]
**File:** `autotrade/runtime.py` line 361

```python
current_price = signal["price"]  # KeyError
```

Signal dict divalidasi untuk `"recommendation"` tapi tidak untuk `"price"`.

**Dampak:** Auto-trade path gagal per pair.

**Fix:** `signal.get("price")` dengan Redis/API fallback. Estimasi: 5 min.

---

### ✅ C5. `analysis/ml_model_v3.py` — Lookahead bias (test leak ke train)
**File:** `analysis/ml_model_v3.py` lines 175-197

```python
future_ret = df['close'].pct_change(...).shift(...)
p25 = future_ret.dropna().quantile(0.25)  # SELURUH dataset
```

Target kelas dari persentil seluruh dataset (train + test). Bug difix di V2, reintroduced di V3.

**Dampak:** Evaluasi over-optimistic (80%+), performa real random (50%).

**Fix:** Hitung persentil dari training set saja. Estimasi: 45 min.

---

### ✅ C6. `analysis/ml_model_v4.py` — hash() non-deterministic
**File:** `analysis/ml_model_v4.py` line 134

```python
features['symbol_hash'] = df['symbol'].apply(lambda x: hash(x) % 10)
```

Python `hash()` = SipHash dengan random seed per-process (Python 3.3+). Nilai berbeda setiap restart → training ≠ prediction.

**Dampak:** Model V4 tidak bisa belajar dari symbol fitur. Tidak reproducible.

**Fix:** `hashlib.md5(x.encode()).hexdigest()`. Estimasi: 10 min.

---

### ✅ C7. `analysis/signal_analyzer.py` — Cursor setelah connection close
**File:** `analysis/signal_analyzer.py` lines 90-142

```python
cursor = signals_conn.cursor()
signals_conn.close()   # line 112
cursor.execute(...)    # line 142 → ProgrammingError
```

**Dampak:** Runtime crash saat signal analyzer.

**Fix:** Buka connection baru untuk query kedua. Estimasi: 10 min.

---

### ✅ C8. `signals/signal_quality_engine.py` — current_price selalu None di MR
**File:** `signals/signal_quality_engine.py` line 356

```python
current_price=ta_signals.get('price')  # ta_signals TIDAK punya key 'price'
```

`TechnicalAnalysis.get_signals()` tidak return key `'price'`. Mean Reversion z-score dijalankan tanpa reference price.

**Note:** Pipeline sudah memanggil `analyze_mean_reversion()` langsung (line 443) dengan `current_price=real_time_price` — tapi call dari `generate_signal()` di quality engine tetap broken.

**Fix:** Pass real_time_price dari pipeline ke quality engine. Estimasi: 10 min.

---

## ═══════════════════════════════════════
## 🟠 HISTORICAL — HIGH Findings From Old Audit (now fixed/guarded)
## ═══════════════════════════════════════

---

### ✅ H1. `core/database.py` — Schema column KeyError
**File:** `core/database.py` line 610

```python
previous_realized = trade['realized_profit_loss'] if 'realized_profit_loss' in trade.keys() and ...
# KeyError terjadi SEBELUM guard — kolom mungkin tidak ada di schema lama
```

---

### ✅ H2. `core/database.py` — original_total falsy check
**File:** `core/database.py` line 610

```python
original_total = trade['original_total'] if ... and trade['original_total'] else trade['total']
# falsy jika nilainya 0 legitimate → fallback ke trade['total'] yang mungkin sudah reduced
```

**Fix:** `is not None` check.

---

### ✅ H3. `autotrade/runtime.py` — None * 0.5 → TypeError
**File:** `autotrade/runtime.py` lines 389-402

`calculate_position_size` bisa return `(None, None)` → aritmatika crash.

---

### ✅ H4. `analysis/ml_signal_trainer.py` — 2 file descriptor leak
**File:** `analysis/ml_signal_trainer.py` lines 111-117, 135-148

`conn.close()` di luar try block → tidak dipanggil jika query raise.

---

### ✅ H5. `analysis/ml_model_v4.py` — Win rate dari prediksi, bukan ground truth
**File:** `analysis/ml_model_v4.py` lines 256-258

```python
good_count = sum(1 for p in pred_labels if p.startswith('GOOD'))
# Hitung dari prediksi, bukan test_labels
```

---

### ✅ H6. `analysis/ml_model_v4.py` — LabelEncoder re-fit corrupt mapping
**File:** `analysis/ml_model_v4.py` line 185

`fit_transform` ulang setiap training → mapping class bergeser → predict return label salah.

---

### ✅ H7. `analysis/support_resistance.py` — np.arange step=0 crash
**File:** `analysis/support_resistance.py` lines 349-356

Market flat → `price_range=0` → `bin_size=0` → `np.arange` ValueError.

---

### ✅ H8. `bot_parts/microstructure.py` — float() crash di order book (9 titik)
**File:** `bot_parts/microstructure.py` lines 20-162

`float(price)` / `float(vol)` tanpa exception handling untuk exchange data.

---

### ✅ H9. `bot_parts/microstructure.py` — ZeroDivisionError di routing
**File:** `bot_parts/microstructure.py` lines 112, 155

`total_size / Config.SMART_ROUTING_CHUNKS` — /0 jika CHUNKS=0.

---

### ✅ H10. `analysis/ml_model_v2.py` — Double _v2 suffix
**File:** `analysis/ml_model_v2.py` lines 59-63

`Config.ML_MODEL_PATH.replace('.pkl', '_v2.pkl')` — path jadi `model_v2_v2_v2.pkl`.

---

### ✅ H11. `autotrade/risk_manager.py` — sum() crash None values
**File:** `autotrade/risk_manager.py` lines 77, 146

`sum(trade['total'] for trade in open_trades)` — TypeError jika ada None.

---

### ✅ H12. `signal_filter_v2.py` — Unbounded list memory leak
**File:** `signal_filter_v2.py` line 86

`self.validation_history: List = []` — append terus, tidak pernah truncate → OOM.

---

## ═══════════════════════════════════════
## 📊 STATISTIK
## ═══════════════════════════════════════

| Category | Count | Detail |
|----------|-------|--------|
| ✅ FIXED total | 15 | 7 dari audit #1 + 8 dari re-audit #2 |
| ✅ CRITICAL fixed/guarded | 8 | C1-C8 diverifikasi ulang 2026-05-20 |
| ✅ HIGH fixed/guarded | 12 | H1-H12 diverifikasi ulang 2026-05-20 |
| ⬚ MEDIUM (not re-checked) | ~16 | Degradasi / memory leak / data palsu |
| ⬚ LOW (not re-checked) | ~10 | Minor / cosmetic / code smell |

---

## ═══════════════════════════════════════
## 🎯 HISTORICAL PRIORITY LIST (completed/guarded as of 2026-05-20)
## ═══════════════════════════════════════

| # | Bug | File | Est. | Alasan |
|---|-----|------|------|--------|
| 1 | C2 — MAX_DRAWDOWN_PCT | `config.py:79` | **1 min** | Auto-trade selalu mati |
| 2 | C4 — KeyError signal["price"] | `runtime.py:361` | **5 min** | Crash auto-trade per pair |
| 3 | C8 — current_price None | `quality_engine.py:356` | **10 min** | MR analysis data palsu |
| 4 | C6 — hash() non-deterministic | `ml_model_v4.py:134` | **10 min** | Model V4 tidak belajar |
| 5 | C7 — Cursor after close | `signal_analyzer.py:142` | **10 min** | Crash signal analyzer |
| 6 | C3 — RSI convolve salah | `enhancement_engine.py:252` | **30 min** | Semua enhancement signal salah |
| 7 | C1 — Env var crash | `config.py` multi | **30 min** | Bot gagal startup |
| 8 | C5 — Lookahead bias V3 | `ml_model_v3.py:175` | **45 min** | Model V3 useless |
| 9 | H4 — File descriptor leak | `ml_signal_trainer.py` | **10 min** | OOM file handles |
| 10 | H12 — Memory leak | `signal_filter_v2.py:86` | **5 min** | OOM RAM |
| 11 | H8 — float() crash | `microstructure.py` | **15 min** | Pipeline crash |
| 12 | H1-H6 | various | **30 min** | Data integrity / evaluation |

---

**Historical estimate:** ~3.5 jam untuk fix semua CRITICAL + HIGH.
**Historical quick wins (< 30 min):** C2, C4, C6, C7, C8, H4, H12 ≈ 51 min.
