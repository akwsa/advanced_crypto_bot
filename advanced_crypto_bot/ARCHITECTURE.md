# 🏗️ Architecture — Advanced Crypto Trading Bot

Penjelasan struktur internal bot, modul-modul utama, dan alur data dari price update sampai eksekusi trade.

---

## 🎯 Entry Point

```
File:   advanced_crypto_bot/bot.py
Class:  AdvancedCryptoBot
Run:    python3 bot.py
```

`bot.py` adalah orchestrator utama (~10000 baris). Class `AdvancedCryptoBot` initialize semua komponen, register Telegram handlers, dan jalankan main event loop.

---

## 📦 Struktur Modul

```
advanced_crypto_bot/
├── bot.py                  # 🚀 Entry point + main bot class
│
├── core/                   # 🔧 Infrastruktur dasar (config, DB, logger, utils)
├── analysis/               # 📊 Technical Analysis + 4 versi ML model
├── autotrade/              # 💹 Trading engine, risk manager, portfolio
├── autohunter/             # 🎯 Smart Hunter & Ultra Hunter (profit hunting)
├── scalper/                # ⚡ Scalper module (satu-satunya jalur real money)
├── signals/                # 📡 Signal pipeline, queue, scheduler, formatter
├── quant/                  # 📈 Quantitative engines (mean reversion, Kelly, momentum)
├── api/                    # 🔌 Indodax API + TMA dashboard server
├── cache/                  # 💾 Redis price cache, state manager, task queue
├── workers/                # 👷 Background workers (price poller, async worker)
├── bot_parts/              # 🤖 Telegram UI helpers (formatting, charts, keyboards)
├── monitoring/             # 📈 Runtime observers
├── tests/                  # 🧪 Test suites (~300+ tests)
└── data/                   # 💾 SQLite DB, signals DB, log files
```

---

## 🔧 Modul Detail

### CORE (`core/`)
Infrastruktur dasar — semua modul lain depend ke sini.

| File | Class / Function | Tujuan |
|------|------------------|--------|
| `config.py` | `Config` | Konfigurasi global (API keys, thresholds, feature flags) |
| `database.py` | `Database` | SQLite wrapper (trades, signals, watchlist, performance) |
| `logger.py` | `CustomLogger` | Logger dengan rotating file handler |
| `utils.py` | `Utils` | Format currency, format price, helper umum |
| `signal_enhancement_engine.py` | `SignalEnhancementEngine` | AI signal enhancement (Volume, VWAP, Ichimoku, Divergence) |
| `handler_registry.py` | `register_bot_handlers()` | Register semua Telegram command handlers ke `Application` |

### ANALYSIS (`analysis/`)
Technical Analysis + Machine Learning.

| File | Class | Tujuan |
|------|-------|--------|
| `technical_analysis.py` | `TechnicalAnalysis` | RSI, MACD, Bollinger Bands, ATR, ADX, MA |
| `ml_model.py` | `MLTradingModel` | ML V1 (basic Random Forest) |
| `ml_model_v2.py` | `MLTradingModelV2` | ML V2 (multi-class target, undersampling) |
| `ml_model_v3.py` | `MLTradingModelV3` | ML V3 (backtesting + Kelly Criterion) |
| `ml_model_v4.py` | `MLTradingModelV4` | ML V4 (trade-outcome based, learns dari hasil trade actual) |
| `ml_signal_trainer.py` | `train_model_from_signals()` | Generate signal outcomes untuk training V4 |
| `signal_analyzer.py` | `SignalAnalyzer` | Quality scoring per signal |
| `support_resistance.py` | `SupportResistanceDetector` | Auto-detect S/R levels (manual override didukung) |
| `adaptive_learning.py` | `AdaptiveLearningEngine` | Nightly batch analysis untuk update threshold |

**Fallback chain:** V2 → V1 jika V2 fail. V3 & V4 optional (auto-train di background saat startup).

### AUTOTRADE (`autotrade/`)
Auto-trading engine. **DRY RUN only** karena safety policy.

**Auto-Promote:** Watched pairs otomatis masuk `auto_trade_pairs` saat signal BUY/STRONG_BUY terdeteksi (DRY RUN mode). Tidak perlu manual `/add_autotrade`.

| File | Class / Function | Tujuan |
|------|------------------|--------|
| `trading_engine.py` | `TradingEngine` | Eksekusi BUY/SELL, calculate SL/TP, duplicate-position guard |
| `risk_manager.py` | `RiskManager` | Position sizing, daily loss check, drawdown circuit breaker |
| `portfolio.py` | `Portfolio` | Portfolio summary, unrealized PnL |
| `price_monitor.py` | `PriceMonitor` | Monitor SL/TP per posisi, kirim notifikasi |
| `runtime.py` | `check_trading_opportunity()`, `execute_auto_sell()`, `monitor_strong_signal()`, `detect_market_regime()` | Runtime trading logic dipanggil dari bot.py |

### AUTOHUNTER (`autohunter/`)
Profit hunters. Juga **DRY RUN only**.

| File | Class | Strategi |
|------|-------|----------|
| `smart_profit_hunter.py` | `SmartProfitHunter` | Partial sell di +3% (50%), +5% (30%), +8% (20%), trailing 1.5%, hard SL -2% |
| `smart_hunter_integration.py` | `SmartHunterBotIntegration` | Adapter ke main bot |
| `ultra_hunter.py` | `UltraHunter` | Conservative: max 100k IDR/posisi, 2 trades/hari, TP +4%, SL -2% |
| `ultra_hunter_integration.py` | `UltraHunterBotIntegration` | Adapter ke main bot |

### SCALPER (`scalper/`)
**Satu-satunya jalur real trading uang asli.** Manual & semi-auto.

| File | Class | Tujuan |
|------|-------|--------|
| `scalper_module.py` | `ScalperModule` | Buy/sell command, position tracking, confirmation flow |

### SIGNALS (`signals/`)
Signal pipeline, queue, formatter.

| File | Tujuan |
|------|--------|
| `signal_pipeline.py` | `generate_signal_for_pair()` — main entry, panggil TA + ML + AI enhancement |
| `signal_queue.py` | Redis-backed queue + scheduler untuk task periodik |
| `signal_quality_engine.py` | Confluence scoring V3 (cooldown, volume confirmation) |
| `signal_formatter.py` | Format pesan Telegram (HTML / Markdown) |
| `signal_filter_v2.py` | Rule-based filter (gate sebelum dispatch) |
| `signal_db.py` | Persist signal ke `data/signals.db` (untuk filter `/signal buy/sell/hold`) |

### QUANT (`quant/`)
Quantitative engines (pure computation, no external calls).

| Engine | Output | Konsumen |
|--------|--------|----------|
| `MeanReversionEngine` | Z-Score, mean reversion score | `signal_quality_engine`, `signal_pipeline` (confidence boost) |
| `BayesianKellyEngine` | Adaptive position size | `trading_engine` (sizing) |
| `MomentumFactorEngine` | Multi-timeframe momentum | `core/profit_optimizer` (edge bonus) |
| `PerformanceAnalytics` | Sharpe, Sortino, Calmar | `risk_manager` (drawdown gating) |
| `DynamicCorrelationEngine` | Portfolio correlation matrix | `risk_manager` (portfolio heat) |
| `StatArbEngine` | Pair trading opportunities | Standalone scanner + `/quant_arb` |

### API (`api/`)
| File | Tujuan |
|------|--------|
| `indodax_api.py` | REST + WebSocket client untuk Indodax (ticker, orderbook, balance, orders) |
| `tma_server.py` | HTTP server untuk Telegram Mini App dashboard (port 8080) |

### CACHE (`cache/`)
| File | Tujuan |
|------|--------|
| `redis_price_cache.py` | Price cache via Redis dengan fallback ke dict |
| `redis_state_manager.py` | State sync (price_data, historical_data metadata) |
| `redis_task_queue.py` | Task queue untuk background work |

Redis **opsional**. Tanpa Redis, bot fallback ke in-memory dict.

### WORKERS (`workers/`)
| File | Class | Tujuan |
|------|-------|--------|
| `price_poller.py` | `PricePoller` | Polling REST API setiap 15s untuk semua watched pairs |
| `async_worker.py` | `BackgroundWorker` | Generic async task runner |

### BOT_PARTS (`bot_parts/`)
Telegram UI components (di-extract dari bot.py untuk modularity).

| File | Tujuan |
|------|--------|
| `command_texts.py` | Static text untuk `/help`, `/menu`, `/start` |
| `formatting.py` | Helper format pesan signal (HTML overview, batches) |
| `telegram_keyboards.py` | Build inline & reply keyboards |
| `admin_panels.py` | Admin panel markup |
| `charts.py` | Generate chart image untuk signal |
| `microstructure.py` | Spoofing detection, liquidity zones, smart order routing |
| `state_sync.py` | Watchlist & historical data sync ke DB |
| `dashboard_heartbeat.py` | Publish heartbeat ke Redis untuk dashboard |

---

## 🔄 Data Flow

### 1. Startup Sequence

```
bot.py
  ├─→ Load Config
  ├─→ Init Database (SQLite)
  ├─→ Init ML models (V1/V2 + V3 + V4 background train)
  ├─→ Init TradingEngine, RiskManager, Portfolio, PriceMonitor
  ├─→ Init IndodaxAPI, PricePoller
  ├─→ Init SignalAnalyzer, SignalQualityEngine, SR Detector
  ├─→ Init Redis StateManager
  ├─→ Init ScalperModule, SmartHunter, UltraHunter
  ├─→ register_bot_handlers() → semua /command
  ├─→ Load watchlist & auto-trade pairs dari DB
  ├─→ _enable_startup_dryrun_autotrade()  ← SAFETY: force DRY RUN
  ├─→ Start PricePoller thread
  ├─→ Start scheduler (market scan, db cleanup, signal stats)
  ├─→ Start Signal Queue worker (consume queued signals)
  ├─→ Start health monitor (auto-restart if RAM > 2GB)
  ├─→ Start Redis state syncer (every 120s)
  ├─→ Start dashboard heartbeat thread
  └─→ Application.run_polling() / run_webhook()
```

### 2. Price Update Flow

```
Indodax REST API (every 15s)
        ↓
PricePoller
        ↓
redis_price_cache.set_price()  ──→  price_data[pair] (in-memory)
        ↓
_process_price_update(pair, data)
        ├─→ _update_historical_data() (in-memory DataFrame)
        ├─→ _save_price_history_background() (DB write via heavy_executor)
        ├─→ price_monitor.check_price_levels() (SL/TP trigger)
        ├─→ process_price_update_signal_tasks() (signal generation trigger)
        └─→ _send_price_update() (broadcast ke subscribers)
```

### 3. Signal Generation Flow

```
Trigger: /signal command, watchlist scan, atau price update
        ↓
generate_signal_for_pair(pair)  [signals/signal_pipeline.py]
        ├─→ TechnicalAnalysis.get_signals()  → RSI, MACD, MA, BB, etc
        ├─→ MLTradingModelV2.predict()  → ML confidence score
        ├─→ MLTradingModelV4.predict()   → Trade outcome score (jika trained)
        ├─→ SignalEnhancementEngine     → Volume, VWAP, Ichimoku, Divergence
        ├─→ MeanReversionEngine          → Z-Score confluence boost
        ├─→ MomentumFactorEngine         → Multi-TF momentum edge
        ├─→ SignalQualityEngine          → Confluence score, cooldown check
        └─→ Output: signal dict {recommendation, ml_confidence, combined_strength, ...}
        ↓
Signal output ──┬─→ format_signal_message_html()  → Telegram message
                ├─→ signal_db.save()  → data/signals.db (untuk filter /signal buy)
                └─→ _build_signal_action_markup()  → BUY/SELL button (route to Scalper)
```

### 4. Auto-Trade Flow (DRY RUN)

```
Strong signal detected
        ↓
check_trading_opportunity(pair, signal)  [autotrade/runtime.py]
        ├─→ Check Config.AUTO_TRADING_ENABLED & is_trading
        ├─→ Decision Layer: display_recommendation check
        │       ├─→ PANTAU + exploration thresholds met → entry 20% size
        │       ├─→ BELI_BERTAHAP → entry 50% size
        │       ├─→ BUY / STRONG_BUY → full entry
        │       └─→ PANTAU below threshold → blocked
        ├─→ RiskManager.validate_trade()
        │       ├─→ Daily loss limit check
        │       ├─→ Max drawdown circuit breaker
        │       └─→ Dynamic correlation portfolio heat
        ├─→ Market Intelligence (spread, orderbook, volume)
        ├─→ TradingEngine.calculate_position_size()
        │       └─→ BayesianKelly adaptive sizing
        ├─→ Entry Zone calculation (limit price below market)
        ├─→ DRY RUN Execution:
        │       ├─→ Immediate fill if ask within 1% of entry zone
        │       │       ├─→ Apply slippage (DRYRUN_SLIPPAGE_PCT, default 0.1%)
        │       │       ├─→ Apply fee (TRADING_FEE_RATE, 0.3%)
        │       │       └─→ Save trade to DB + setup SL/TP
        │       └─→ Otherwise → register PENDING order
        │               └─→ check_pending_orders() fills when ask <= limit
        ├─→ price_monitor.set_price_level() → SL/TP/trailing setup
        └─→ Send Telegram notification (if signal_notifications ON)
```

#### DRY RUN Execution Realism (2026-06-04)

DRY RUN profit/loss sekarang **menyertakan fee + slippage** supaya hasil simulasi mendekati real:

| Komponen | Nilai | Keterangan |
|----------|-------|------------|
| Entry slippage | +0.1% (BUY pays more) | `DRYRUN_SLIPPAGE_PCT` |
| Trading fee | 0.3% per side | `TRADING_FEE_RATE` (Indodax standard) |
| Exit slippage | -0.1% (SELL gets less) | Applied saat auto-sell |
| Fill rule | Ask ≤ limit price + 1% | Limit order dianggap fill jika market dekat |
| Timeout | 15 menit | `LIMIT_ORDER_TIMEOUT_MINUTES` |

#### Exploration Mode (PANTAU / BELI_BERTAHAP)

Sinyal yang belum cukup kuat untuk full entry tapi masih layak di-evaluasi:

| Label | Position Size | Syarat |
|-------|--------------|--------|
| PANTAU | 20% | conf≥0.45, strength≥0.05, rr≥0.6 |
| BELI_BERTAHAP | 50% | Otomatis lolos (sudah melewati decision layer) |
| BUY / STRONG_BUY | 100% | Full size sesuai Kelly/risk |

Config exploration di `.env`:
```env
DRYRUN_EXPLORATION_ENABLED=true
DRYRUN_EXPLORATION_POSITION_FACTOR=0.20
DRYRUN_EXPLORATION_MIN_CONFIDENCE=0.45
DRYRUN_EXPLORATION_MIN_STRENGTH=0.05
DRYRUN_EXPLORATION_MIN_RR=0.6
```

### 5. Real Trade Flow (Scalper Only)

```
User: /s_buy btcidr 150000000 100000
        ↓
ScalperModule.cmd_buy()
        ├─→ Validate pair, price, amount
        ├─→ Show confirmation message dengan inline buttons
        ↓
User confirm "YES"
        ↓
        ├─→ DRY RUN: simulasi + save ke DB
        └─→ REAL: IndodaxAPI.create_order() → real order ke Indodax
              ↓
            Save trade ke DB
            Setup SL/TP via PriceMonitor
            Send execution notification
```

### 6. Scheduled Tasks (`scheduler` di `signals/signal_queue.py`)

| Task | Interval | Fungsi |
|------|----------|--------|
| `market_scan` | 10 menit | Scan watched + auto-trade pairs untuk strong signal, push ke signal_queue |
| `db_cleanup` | 6 jam | Hapus price_history & signals lebih dari 30 hari |
| `signal_stats` | 1 jam | Update statistik queue |
| `cache_health` | 30 menit | Check Redis connection |
| `adaptive_analysis` | 6 jam | Update adaptive thresholds dari trade outcomes |

---

## 🎯 Signal Decision Logic (BUY / SELL / HOLD)

Ini detail metode yang menentukan kapan satu pair muncul signal BUY / SELL / HOLD. Pipeline punya **14 layer filter** — base recommendation dari TA + ML, lalu di-validasi berlapis.

### Urutan Eksekusi

```
[1] Technical Analysis (5 indikator)  →  ta_strength
[2] Machine Learning V1/V2 (+ V4 outcome)  →  ml_confidence + ml_signal_class
[3] Combined Strength = TA × 0.70 + ML × 0.30  →  base recommendation
[4] Signal Stabilization (anti-flip-flop)
[5] Price Validation (stale price check)
[6] Volatility Filter & Market Regime
[7] Signal Quality Engine V3 (confluence + cooldown)
[8] Quant Mean Reversion (Z-Score boost)
[9] Support/Resistance Validation
[10] Signal Enhancement (VWAP, Ichimoku, divergence)
[11] GARCH + VaR + ARIMA enrichment
[12] ML V4 Trade Outcome Validation
[13] Adaptive Learning Threshold (per-pair)
[14] Final Policy Confidence Floor
       ↓
   FINAL: BUY / SELL / HOLD
```

Setiap layer bisa override base recommendation menjadi HOLD kalau gagal validasi.

---

### [1] Technical Analysis — `analysis/technical_analysis.py`

5 indikator klasik dengan scoring symmetric:

| Indikator | BUY signal | SELL signal | Skor |
|-----------|-----------|------------|------|
| **RSI** | < 30 (oversold) | > 70 (overbought) | ±1.0 |
| **MACD** | Bullish cross | Bearish cross | ±1.0 (cross) / ±0.5 (trend) |
| **Moving Averages** | Close > SMA20 > SMA50 | Close < SMA20 < SMA50 | ±1.0 |
| **Bollinger Bands** | Price < lower band | Price > upper band | ±1.0 |
| **Volume** | High vol + price up | High vol + price down | ±0.5 |

**Output:** `ta_strength` = average semua skor, range **-1.0 sampai +1.0**.

TA standalone recommendation:
- `STRONG_BUY` kalau strength > 0.5
- `BUY` kalau > 0.05
- `SELL` kalau < -0.05
- `STRONG_SELL` kalau < -0.5
- `HOLD` kalau di antara

---

### [2] Machine Learning — 4 versi dengan fallback

| Versi | File | Tujuan |
|-------|------|--------|
| **V1** | `analysis/ml_model.py` | Random Forest binary (BUY/SELL) — legacy |
| **V2** ⭐ primary | `analysis/ml_model_v2.py` | Multi-class: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL |
| **V3** | `analysis/ml_model_v3.py` | Backtesting engine + Kelly Criterion (untuk sizing) |
| **V4** | `analysis/ml_model_v4.py` | **Trade outcome learning** — belajar dari hasil trade actual (GOOD_BUY, BAD_BUY, NEUTRAL_BUY, dst) |

**Fallback chain:** kalau V2 tidak fitted atau return default HOLD → coba V1 sebagai fallback.

**Output:** `ml_confidence` (0–1) + `ml_signal_class`.

---

### [3] Combined Strength — `autotrade/trading_engine.py::generate_signal`

Formula:
```
combined_strength = (ta_strength × 0.70) + (ml_strength × 0.30)
```

ML weight tetap 0.30 untuk semua direction (symmetric, supaya bot tidak bias bearish).

**Threshold base recommendation:**

| Recommendation | Combined Strength | + ML Confidence |
|----------------|-------------------|-----------------|
| `STRONG_BUY` | > **+0.20** | AND ≥ 0.45 |
| `BUY` | > **+0.12** | — |
| `HOLD` | -0.12 ≤ x ≤ +0.12 | — |
| `SELL` | < **-0.12** | — |
| `STRONG_SELL` | < **-0.20** | AND ≥ 0.45 |

Ini hasil **base recommendation**. Layer berikutnya bisa override ke HOLD.

---

### [4] Signal Stabilization — anti-flip-flop

Cek perubahan recommendation dari signal sebelumnya untuk pair yang sama:

| Jump magnitude | Aksi |
|---------------|------|
| ≥ 7 levels (extreme) | STRONG → moderate (e.g. STRONG_BUY → BUY) |
| ≥ 5 levels (moderate) | Downgrade kecuali confidence > 70% |
| < 5 levels | Allow |
| Time gap > 30 menit | Allow apapun |

Tujuan: hindari signal yang flip-flop terus dalam waktu singkat.

---

### [5] Price Validation

| Kondisi | Aksi |
|---------|------|
| Realtime price stale (cache > 60s tanpa API fresh) | Block actionable signal → HOLD |
| Pakai historical fallback price | Block actionable signal → HOLD |

Mencegah signal berdasarkan harga lama yang tidak akurat.

---

### [6] Volatility Filter & Market Regime — `signals/signal_quality_engine.py`

| Kondisi | Aksi |
|---------|------|
| ATR-based volatility terlalu tinggi | → HOLD |
| Market regime = `HIGH_VOLATILITY` | → HOLD (`position_multiplier = 0.0`) |
| Regime = `TREND` | Lanjut (full position) |
| Regime = `RANGE` | Lanjut (reduced position) |

---

### [7] Signal Quality Engine V3

Confluence scoring + cooldown:

- Cek alignment antar indikator (TA + ML + enhancement)
- **Cooldown 5 menit per (pair, signal_type)** — anti-spam
- Volume confirmation requirement
- Bisa downgrade STRONG → moderate kalau confluence kurang
- Bisa override ke HOLD kalau quality score rendah

---

### [8] Quant Mean Reversion — `quant/mean_reversion.py`

- Hitung Z-Score composite (price vs rolling mean multi-timeframe)
- Kalau MR signal align dengan base recommendation → **boost ml_confidence**
- Tidak override, hanya enrichment

---

### [9] Support/Resistance Validation — `analysis/support_resistance.py`

Auto-detect S/R levels (atau manual override via `/set_sr`). Threshold dari `Config`:

| Rule | Default | Aksi kalau gagal |
|------|---------|------------------|
| BUY rejected: harga dekat resistance | < 2% dari R1 | → HOLD |
| BUY rejected: di luar support entry zone | — | → HOLD |
| SELL rejected: harga dekat support | < 2% dari S1 | → HOLD |
| Risk/Reward ratio terlalu rendah | < 1.5 | → HOLD |
| Stop distance terlalu tipis | < 0.3% | → HOLD |

Validasi ini PALING SERING jadi alasan signal di-reject ke HOLD.

---

### [10] Signal Enhancement Engine — `core/signal_enhancement_engine.py`

5 fitur AI enhancement:

- **Volume profile** (VPVR-style)
- **VWAP** analysis (price vs VWAP)
- **Ichimoku Cloud** (trend confirmation)
- **RSI/MACD divergence** (reversal warning)
- **Candlestick patterns** (engulfing, pin bar, doji, dll)

**Efek:**
- Adjust `ml_confidence` ±0.03 (capped, biar tidak kill signal)
- Bisa override ke HOLD kalau ada strong contrarian signal

---

### [11] Quant Enrichment: GARCH + VaR + ARIMA

Cached per pair (TTL 5 menit) — `quant/`:

| Module | Output | Efek |
|--------|--------|------|
| **GARCH(1,1)** | Volatility regime forecast (LOW / NORMAL / HIGH) | Disimpan ke `trading_engine` untuk position sizing |
| **VaR/CVaR** | Risk metric (95% confidence) | Display only |
| **ARIMA filter** | Forecast direction & % change | Block BUY kalau ARIMA prediksi turun > 1% |

---

### [12] ML V4 Trade Outcome Validation

V4 model belajar dari hasil trade actual. Output kategori: `GOOD_BUY` / `BAD_BUY` / `GOOD_SELL` / `BAD_SELL` / `NEUTRAL_*`.

| V4 Prediction | Aksi |
|---------------|------|
| `BAD_BUY` (untuk BUY signal) | → HOLD |
| `BAD_SELL` (untuk SELL signal) | → HOLD |
| `NEUTRAL_SELL` + STRONG_SELL | Soft veto: STRONG_SELL → SELL |
| `NEUTRAL_SELL` + SELL + low confidence | → HOLD |

---

### [13] Adaptive Learning Threshold — `analysis/adaptive_learning.py`

Per-pair learning dari trade outcomes 7 hari terakhir:

| Kondisi | Aksi |
|---------|------|
| Pair Profit Factor 7d < 1.0 | **Skip pair** → HOLD (auto-blacklist) |
| Custom confidence threshold per pair | Override default kalau ada di DB |

Update via scheduled task `adaptive_analysis` setiap 6 jam.

---

### [14] Final Policy Confidence Floor — `signals/signal_rules.py`

Minimum confidence per recommendation type. Kalau di bawah → force HOLD:

| Recommendation | Min Confidence |
|----------------|----------------|
| `BUY` | **0.50** |
| `STRONG_BUY` | **0.64** |
| `SELL` | **0.58** |
| `STRONG_SELL` | **0.70** |

SELL threshold sengaja lebih tinggi dari BUY karena cost downside lebih besar (kena fee 2x kalau buy back).

---

### Tracing Kenapa Signal Di-HOLD

Kalau signal akhirnya HOLD padahal awalnya BUY/SELL, log akan punya tag yang menunjukkan layer mana yang reject:

| Tag log | Asal reject |
|---------|-------------|
| `🛡️ [PRICE VALIDATION]` | Layer [5] Stale price |
| `🛡️ [VOLATILITY]` / `🛡️ [REGIME]` | Layer [6] |
| `🛡️ [QUALITY ENGINE]` | Layer [7] |
| `🛡️ [S/R VALIDATION]` | Layer [9] |
| `🛡️ [ENHANCEMENT]` | Layer [10] |
| `🛡️ [ARIMA FILTER]` | Layer [11] ARIMA |
| `🛡️ [V4 VALIDATION]` / `🛡️ [V4 SOFT FILTER]` | Layer [12] |
| `🛡️ [ADAPTIVE]` | Layer [13] |
| `🛡️ [FINAL POLICY]` | Layer [14] |

Field di signal dict yang flag rejection: `price_filtered`, `volatility_filtered`, `regime_filtered`, `quality_filtered`, `sr_filtered`, `enhancement_filtered`, `arima_filtered`, `v4_filtered`, `adaptive_filtered`, `final_policy_filtered`.

Trace lengkap di log: `🧭 [HOLD TRACE] {pair}: source={layer} | reason={detail}`.

---

### Ringkas: Apa yang Bikin Signal BUY Akhirnya Lolos?

Signal BUY benar-benar tampil di Telegram kalau lolos **SEMUA** kondisi:

1. ✅ TA: minimal 2-3 indikator bullish (RSI oversold + MACD bullish + MA bullish, dll)
2. ✅ ML: confidence ≥ 0.50 dengan signal_class `BUY` atau `STRONG_BUY`
3. ✅ Combined strength > +0.12
4. ✅ Tidak flip-flop dari signal sebelumnya
5. ✅ Realtime price fresh (< 60s)
6. ✅ Volatility normal & regime bukan HIGH_VOLATILITY
7. ✅ Quality engine confluence cukup
8. ✅ Harga **bukan** di dekat resistance (> 2% dari R1)
9. ✅ Harga di **support entry zone** (sekitar S1)
10. ✅ Risk/Reward ratio ≥ 1.5
11. ✅ ARIMA forecast tidak prediksi turun > 1%
12. ✅ ML V4 tidak prediksi `BAD_BUY`
13. ✅ Pair profit factor 7d ≥ 1.0
14. ✅ Final confidence ≥ 0.50 (atau 0.64 untuk STRONG_BUY)

Kalau ada satu saja gagal → signal jadi **HOLD**.

Itu kenapa banyak signal yang awalnya BUY/SELL akhirnya jadi HOLD — sistem sengaja konservatif supaya minim false positive.

---

## 🔒 Critical Paths (Jangan Rusak!)

1. **Signal pipeline:** `signals/signal_pipeline.py` ← `analysis/technical_analysis.py` + `core/signal_enhancement_engine.py`
2. **Trade execution:** `autotrade/trading_engine.py` ← `api/indodax_api.py`
3. **Risk management:** `autotrade/risk_manager.py` ← `autotrade/portfolio.py`
4. **Database:** `core/database.py` (semua modul depend)
5. **Safety lock:** `bot._lock_no_money_automation()` + `_enable_startup_dryrun_autotrade()` — JANGAN dibypass

---

## 💾 Database Schema

File utama: `data/trading.db` (SQLite).

Tabel penting:
- `users` — Telegram user registry
- `telegram_users` — Whitelist + role (admin/user)
- `watchlist` — Per-user pair subscriptions
- `auto_trade_pairs` — Per-user auto-trade list
- `trades` — Open & closed trades dengan PnL
- `price_history` — OHLCV per pair (rolling 30 hari)
- `pending_orders` — Limit orders yang masih open
- `trade_outcomes` — Hasil trade (untuk ML V4 training)
- `pair_performance` — Per-pair win rate, profit factor (auto-skip rule)
- `adaptive_thresholds` — Threshold adaptif hasil nightly analysis
- `signal_notifications` & `signal_notification_filter` — Persisted user preference

File kedua: `data/signals.db` — signal history (`signals/signal_db.py`).

---

## 🧵 Threading Model

Bot pakai mix asyncio (Telegram) + threading (background workers):

| Thread | Daemon | Tujuan |
|--------|--------|--------|
| Main thread | No | Telegram polling (asyncio loop) |
| `PricePoller` thread | Yes | REST polling 15s loop |
| `RedisStateSync` thread | Yes | Sync state ke Redis (120s) |
| `HealthMonitor` thread | Yes | Memory check + auto-restart kalau > 2GB |
| `MarketScan-*` threads | Yes | Background market scans |
| `SignalQueue-Worker` thread | Yes | Consume signal queue → execute trade |
| `ML-Retrain` / `ML-AutoRetrain` threads | Yes | Train ML model di background |
| `HeavyDB` ThreadPoolExecutor (4 workers) | - | DB write yang berat (price history) |

Graceful shutdown lewat `_shutdown()` dengan timeout 10s. Signal handlers terdaftar untuk SIGTERM & SIGINT.

---

## 📊 Stack & Dependencies

| Layer | Library |
|-------|---------|
| Telegram | `python-telegram-bot` |
| Data | `pandas`, `numpy` |
| TA | `talib`, `ta` |
| ML | `scikit-learn` |
| HTTP | `requests` |
| WebSocket | `websocket-client` (disabled — pakai REST polling) |
| Cache | `redis` (opsional) |
| DB | `sqlite3` (built-in) |
| Charts | `matplotlib` |
| Process | `psutil` (untuk health monitor) |
| AI | `anthropic` (Claude API untuk SignalEnhancement) |

---

## 🚪 Extension Points

Mau tambah modul baru? Tempatnya:

| Mau tambah... | Tempat |
|--------------|--------|
| Indikator TA baru | `analysis/technical_analysis.py` (extend `get_signals()`) |
| ML model baru | Buat `analysis/ml_model_v5.py`, init di `__init__` bot.py |
| Signal filter baru | `signals/signal_filter_v2.py` atau `signals/signal_rules.py` |
| Telegram command baru | `core/handler_registry.py` + method di `AdvancedCryptoBot` |
| Quant engine baru | `quant/<engine_name>.py`, integrate di `signal_pipeline.py` |
| Risk rule baru | `autotrade/risk_manager.py` (extend `validate_trade()`) |
| API exchange lain | `api/<exchange>_api.py` (mirror struktur `indodax_api.py`) |

---

## 🚀 Roadmap — Metode/Arsitektur yang Belum Ada

Daftar method & komponen yang biasa dipakai di quant trading profesional tapi **belum** ada di bot ini. Diurutkan berdasarkan **priority** (impact vs effort).

### 🔴 HIGH PRIORITY (impact tinggi, harus segera)

#### R1. Multi-Timeframe Analysis (MTF)
**Status:** Belum ada. Bot saat ini cuma analisa 1 timeframe.

**Apa:** Cek timeframe lebih besar dulu sebelum entry di timeframe kecil.
```
4H trend  → context (HTF bias)
1H trend  → setup confirmation
15M       → execution (existing)
```
**Rule:** Block BUY di 15M kalau 4H trend bearish.

**Effort:** Medium (~3-5 hari) | **Impact:** Very High
**File baru:** `analysis/multi_timeframe.py`
**Integrate:** layer baru di `signals/signal_pipeline.py` setelah base recommendation, sebelum stabilization.

**Kenapa krusial:** Eliminasi 30-50% false BUY di market downtrend (kasus "kena pisau jatuh" — oversold di 15M tapi 4H downtrend besar).

---

#### R2. Order Book Microstructure Integration
**Status:** Code sudah ada di `bot_parts/microstructure.py` (spoofing detection, liquidity zones, smart_order_routing) — **tapi tidak dipanggil dari pipeline**. Idle code.

**Apa yang dibutuhkan:**
- **Order Book Imbalance (OBI):** ratio `(bid_depth - ask_depth) / total`. OBI > 0.3 = strong buying pressure
- **Cumulative Volume Delta (CVD):** akumulasi market buy vs market sell, divergence dengan price = warning
- **Spoofing detection** (sudah ada, tinggal panggil): block signal kalau ada spoof bid wall

**Effort:** Low (~1-2 hari, mostly integration) | **Impact:** Very High
**File:** Extend `bot_parts/microstructure.py`, integrate di `signals/signal_pipeline.py`

**Kenapa krusial:** Crypto Indodax penuh manipulator. Tanpa baca order flow, bot sering masuk di puncak/dasar pump-and-dump.

---

#### R3. BTC Correlation / Market Breadth Filter
**Status:** Belum ada. Bot blind terhadap kondisi market keseluruhan.

**Apa:**
- **BTC trend filter:** kalau pair bukan BTC, cek trend BTC di 1H/4H. Kalau BTC bearish, raise confidence threshold untuk altcoin BUY (atau block langsung).
- **Market breadth:** hitung % pair di Indodax yang lagi naik. Breadth < 30% = market lemah → hindari BUY agresif.

**Effort:** Low (~1 hari) | **Impact:** High
**File baru:** `analysis/market_breadth.py`
**Integrate:** layer baru di pipeline, panggil sebelum [3] Combined Strength.

**Kenapa krusial:** 80%+ altcoin pergerakan correlated ke BTC. Mencegah BUY altcoin saat BTC crash.

---

### 🟡 MEDIUM PRIORITY (bagus tapi optional)

#### R4. Walk-Forward Optimization & Out-of-Sample Validation
**Status:** Backtest ada, tapi pakai dataset yang sama untuk train + test. Overfitting risk tinggi.

**Apa:** Split data 70% in-sample / 30% out-of-sample. Walk-forward: rolling window retrain tiap N hari. Track in-sample vs out-of-sample win rate gap.

**Effort:** Medium (~3-4 hari) | **Impact:** High
**File:** `analysis/walk_forward.py` + extend `analysis/ml_model_v3.py::backtest()`

**Kenapa krusial:** ML V2/V3/V4 bisa "look perfect" di backtest tapi gagal live karena overfit ke pattern lama.

---

#### R5. Session-Aware Filter
**Status:** Belum ada. Bot trading 24/7 tanpa beda session.

**Apa:**
- **Asian session** (00:00-08:00 WIB): volume rendah, sering whipsaw → raise threshold
- **Europe + US overlap** (15:00-22:00 WIB): volume tinggi, signal lebih reliable
- **Weekend** (Sat-Sun): volume drop 40-60% → skip pair illiquid

**Effort:** Very Low (~half hari) | **Impact:** Medium
**File:** Extend `signals/signal_quality_engine.py`

**Kenapa berguna:** Mayoritas false signal terjadi di Asian session + weekend. Quick win.

---

#### R6. Sentiment / Fear & Greed Index Filter
**Status:** Belum ada.

**Apa (quick win):**
- **Fear & Greed Index** dari [alternative.me](https://alternative.me/crypto/fear-and-greed-index/) — API gratis, no key
- Rule: Fear < 20 → favor BUY (contrarian); Greed > 80 → favor SELL

**Apa (advanced):** News sentiment via CryptoPanic API, Twitter/X sentiment (paid).

**Effort:** Very Low untuk F&G (~half hari) | **Impact:** Medium-Low
**File baru:** `analysis/sentiment.py`
**Integrate:** sebagai enrichment, adjust confidence ±5%.

---

#### R7. Chart Pattern Recognition (multi-bar)
**Status:** Bot sudah deteksi candlestick patterns (engulfing, doji, pin bar) tapi belum chart patterns multi-bar.

**Apa:** Head & Shoulders / inverse H&S, triangles (ascending/descending/symmetrical), flags & pennants, double top/bottom, cup & handle.

**Effort:** High (~1 minggu) | **Impact:** Medium
**File baru:** `analysis/chart_patterns.py` (pakai TA-Lib pattern functions atau geometric pivot detection)

**Kenapa berguna:** Pattern multi-bar punya R/R yang terdefinisi jelas (entry, SL, TP dari structure).

---

### 🟢 LOW PRIORITY (nice-to-have, ROI tidak jelas)

#### R8. Hidden Markov Model (HMM) Regime Detection
Saat ini cuma 3 regime (TREND/RANGE/HIGH_VOLATILITY). HMM bisa kasih granularity: BULL_TREND, BEAR_TREND, ACCUMULATION, DISTRIBUTION. Library: `hmmlearn`. Marginal improvement vs effort.

#### R9. Ensemble / Stacking ML Models
V1-V4 ada di pipeline tapi combine-nya simple (V2 primary + V4 validation). Stacking proper: train meta-learner kombinasi prediksi V1+V2+V4. Gain ~2-5% accuracy, complexity tambah banyak.

#### R10. Reinforcement Learning Integration
Q-table skeleton ada di `bot.py` (`rl_q_table`, `rl_choose_action`) **tapi tidak dipakai** di signal generation. RL butuh ribuan episode untuk converge — exploration cost tinggi untuk modal kecil. Skip sampai data trade banyak.

#### R11. On-Chain Metrics (BTC/ETH only)
Exchange flow, whale movements, miner reserves dari Glassnode/CryptoQuant. API mahal, cuma applicable top coin, lag time tinggi. Skip kecuali fokus long-term BTC/ETH.

---

### 📋 Ringkasan Roadmap

| ID | Metode | Effort | Impact | Quick Win |
|----|--------|--------|--------|-----------|
| **R1** | **Multi-Timeframe Analysis** | Medium | Very High | ✅ |
| **R2** | **Order Book Microstructure** (integrate existing!) | Low | Very High | ✅✅ |
| **R3** | **BTC Correlation / Market Breadth** | Low | High | ✅ |
| R4 | Walk-Forward Validation | Medium | High | — |
| R5 | Session-Aware Filter | Very Low | Medium | ✅✅ |
| R6 | Fear & Greed Index | Very Low | Medium-Low | ✅✅ |
| R7 | Chart Patterns | High | Medium | — |
| R8 | HMM Regime | High | Low-Medium | — |
| R9 | Ensemble Stacking | High | Low-Medium | — |
| R10 | Reinforcement Learning | Very High | Low | — |
| R11 | On-Chain Metrics | High | Low | — |

### 🎯 Urutan Implementasi yang Disarankan

1. **R2 — Microstructure integration** (code sudah ada, tinggal panggil)
2. **R5 — Session filter** (quick win, very low effort)
3. **R6 — Fear & Greed Index** (quick win, very low effort)
4. **R3 — BTC correlation** (foundational untuk altcoin trading)
5. **R1 — Multi-Timeframe Analysis** (foundational, eliminate false signals)
6. **R4 — Walk-Forward Validation** (kalau mau scale ML lebih agresif)
7. **R7+** (kalau yang di atas sudah live & stabil)

---

## 🧪 Testing

Test di `tests/` directory. Run:

```bash
python3 -m pytest tests/                            # Semua
python3 -m pytest tests/test_dryrun_safety.py -v    # Spesifik
./scripts/test.sh                                    # Wrapper
```

Test coverage area:
- `test_signal_*` — Signal pipeline, formatter, filter, dispatch
- `test_dryrun_safety.py` — Safety policy enforcement
- `test_telegram_*` — UI formatting & access control
- `test_scalper_*` — Scalper module
- `test_v4_integration.py` — ML V4 training flow
- `test_bug_fixes_verification.py` — Regression checks
