# SYSTEM MAP - Advanced Crypto Trading Bot

**Last Updated:** 2026-04-30  
**Purpose:** Index navigasi utama untuk semua modul, dependencies, dan entry points.

---

## 🎯 Entry Point

**File:** `advanced_crypto_bot/bot.py`  
**Class:** `AdvancedCryptoBot`  
**Run:** `python3 bot.py`

---

## 📦 Module Architecture

```
advanced_crypto_bot/
├── 🔧 core/              # Infrastruktur dasar
├── 📊 analysis/          # Technical & ML analysis
├── 💹 autotrade/         # Auto-trading engine
├── 🎯 autohunter/        # Smart & Ultra profit hunters
├── ⚡ scalper/           # Scalping module
├── 📡 signals/           # Signal generation & processing
├── 🔌 api/               # External API integrations
├── 💾 cache/             # Redis & price caching
├── 👷 workers/           # Background async workers
├── 🤖 bot_parts/         # Telegram UI components
├── 🧪 tests/             # Test suites
└── 📈 monitoring/        # Runtime observers
```

---

## 🔧 CORE (Infrastruktur)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `core/config.py` | Konfigurasi global (API keys, thresholds) | `Config` |
| `core/database.py` | SQLite DB wrapper | `Database` |
| `core/logger.py` | Custom logging | `CustomLogger` |
| `core/utils.py` | Helper utilities | `Utils` |
| `core/signal_enhancement_engine.py` | AI signal enhancement | `SignalEnhancementEngine` |
| `core/signal_enhancement_config.py` | Enhancement config | `SignalEnhancementConfig` |
| `core/handler_registry.py` | Command handler registration | `register_bot_handlers()` |

**Dependencies:** Standard library + SQLite  
**External Calls:** None (pure logic)

---

## 📊 ANALYSIS (Technical & ML)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `analysis/technical_analysis.py` | TA-Lib indicators (RSI, MACD, Bollinger) | `TechnicalAnalysis` |
| `analysis/ml_model.py` | ML model V1 | `MLTradingModel` |
| `analysis/ml_model_v2.py` | ML model V2 (improved) | `MLTradingModelV2` |
| `analysis/ml_model_v3.py` | ML model V3 (backtesting) | `MLTradingModelV3`, `create_model()` |
| `analysis/ml_model_v4.py` | ML model V4 (trade outcome) | `MLTradingModelV4` |
| `analysis/ml_signal_trainer.py` | Signal outcome labeling | `SignalOutcomeLabeler`, `train_model_from_signals()` |
| `analysis/signal_analyzer.py` | Signal quality analysis | `SignalAnalyzer` |
| `analysis/support_resistance.py` | S/R level detection | `SupportResistanceDetector` |
| `analysis/analyze_signals.py` | Quick BUY/SELL analysis | `AnalyzeSignals` |
| `analysis/adaptive_learning.py` | Adaptive ML learning | - |
| `analysis/nightly_analyzer.py` | Nightly batch analysis | - |

**Dependencies:** `pandas`, `numpy`, `talib`, `sklearn`, `anthropic` (Claude API)  
**External Calls:** Claude API untuk AI enhancement

---

## 💹 AUTOTRADE (Trading Engine)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `autotrade/trading_engine.py` | Core trading execution | `TradingEngine` |
| `autotrade/risk_manager.py` | Risk & position sizing | `RiskManager` |
| `autotrade/portfolio.py` | Portfolio tracking | `Portfolio` |
| `autotrade/price_monitor.py` | Real-time price monitoring | `PriceMonitor` |
| `autotrade/runtime.py` | Runtime operations (market regime, S/R, auto-sell) | `detect_market_regime()`, `execute_auto_sell()`, `analyze_market_intelligence()` |

**Dependencies:** `core/*`, `api/indodax_api`, `signals/*`  
**External Calls:** Indodax API (buy/sell orders)

---

## 🎯 AUTOHUNTER (Profit Hunters)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `autohunter/smart_profit_hunter.py` | Smart profit hunting logic | `SmartProfitHunter` |
| `autohunter/smart_hunter_integration.py` | Smart hunter integration | `SmartHunterBotIntegration` |
| `autohunter/ultra_hunter.py` | Ultra aggressive hunting | `UltraHunter` |
| `autohunter/ultra_hunter_integration.py` | Ultra hunter integration | `UltraHunterBotIntegration` |

**Dependencies:** `autotrade/*`, `signals/*`  
**External Calls:** Indodax API

---

## ⚡ SCALPER

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `scalper/scalper_module.py` | Scalping strategy module | `ScalperModule` |

**Dependencies:** `autotrade/*`, `signals/*`  
**External Calls:** Indodax API

---

## 📡 SIGNALS (Signal Pipeline)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `signals/signal_pipeline.py` | Signal generation pipeline | `generate_signal_for_pair()` |
| `signals/signal_queue.py` | Signal queue + scheduler | `signal_queue`, `scheduler` |
| `signals/signal_quality_engine.py` | Signal quality scoring V3 | `SignalQualityEngine` |
| `signals/signal_formatter.py` | Telegram message formatting | `format_signal_message()`, `format_signal_message_html()` |
| `signals/signal_filter_v2.py` | Signal filtering V2 | - |
| `signals/signal_rules.py` | Rule-based signal validation | - |
| `signals/signal_db.py` | Signal database operations | - |

**Dependencies:** `analysis/*`, `core/*`  
**External Calls:** Claude API (via `SignalEnhancementEngine`)

---

## 🔌 API

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `api/indodax_api.py` | Indodax REST/WebSocket API | `IndodaxAPI` |
| `api/tma_server.py` | TMA server integration | - |

**Dependencies:** `requests`, `websocket`  
**External Calls:** Indodax exchange API

---

## 💾 CACHE

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `cache/redis_price_cache.py` | Redis-backed price cache | `price_cache` (global instance) |
| `cache/price_cache.py` | In-memory price cache | - |
| `cache/redis_state_manager.py` | Redis state management | - |
| `cache/redis_task_queue.py` | Redis task queue | - |

**Dependencies:** `redis`  
**External Calls:** Redis server

---

## 👷 WORKERS

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `workers/async_worker.py` | Background async workers | `BackgroundWorker` |
| `workers/price_poller.py` | Price polling worker | `PricePoller` |

**Dependencies:** `asyncio`, `threading`  
**External Calls:** Indodax API (via price polling)

---

## 🤖 BOT_PARTS (Telegram UI)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `bot_parts/charts.py` | Chart generation | - |
| `bot_parts/command_texts.py` | Static command text templates | - |
| `bot_parts/formatting.py` | Message formatting helpers | - |
| `bot_parts/microstructure.py` | Market microstructure analysis | - |
| `bot_parts/state_sync.py` | State synchronization | - |

**Dependencies:** `matplotlib`, `telegram`  
**External Calls:** None (rendering only)

---

## 🧪 TESTS

| File | Purpose |
|------|---------|
| `tests/test_adaptive_learning.py` | Test adaptive ML |
| `tests/test_performance_backfill.py` | Test performance metrics |
| `tests/test_v4_integration.py` | Test ML V4 integration |
| `tests/test_telegram_ui_formatting.py` | Test Telegram UI |
| `tests/test_dryrun_safety.py` | Test dry-run mode |
| `tests/test_scalper_dryrun_positions.py` | Test scalper dry-run |
| `tests/test_signal_notification_controls.py` | Test signal notifications |

**Run:** `pytest tests/test_<module>.py`

---

## 📈 MONITORING

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `monitoring/runtime_observer.py` | Runtime metrics observer | - |

---

## 🔄 Data Flow (Startup → Runtime)

### Startup Sequence
1. **bot.py** → Load `Config`, init `Database`
2. Load ML models: `MLTradingModelV3`, `MLTradingModelV4`
3. Init trading components: `TradingEngine`, `RiskManager`, `Portfolio`
4. Init hunters: `ScalperModule`, `SmartHunterBotIntegration`, `UltraHunterBotIntegration`
5. Init workers: `BackgroundWorker`, `PricePoller`
6. Register Telegram handlers via `register_bot_handlers()`
7. Start Telegram bot polling

### Runtime Flow (Signal Generation)
1. **Price Update** → `PricePoller` → `redis_price_cache`
2. **Signal Trigger** → `signal_queue.add_signal_task()`
3. **Signal Pipeline** → `generate_signal_for_pair()`
   - Technical analysis via `TechnicalAnalysis`
   - ML scoring via `MLTradingModelV3/V4`
   - AI enhancement via `SignalEnhancementEngine` (Claude API)
   - Quality check via `SignalQualityEngine`
4. **Signal Output** → Format via `format_signal_message()` → Telegram

### Runtime Flow (Auto-Trading)
1. **Signal Detected** → `check_trading_opportunity()`
2. **Risk Check** → `RiskManager.validate_trade()`
3. **Order Execution** → `TradingEngine.execute_buy/sell()`
4. **Portfolio Update** → `Portfolio.update()`
5. **Auto-Sell Monitor** → `execute_auto_sell()` (profit target/stop loss)

---

## 🚨 Critical Paths (Jangan Rusak!)

1. **Signal Pipeline**: `signals/signal_pipeline.py` → `analysis/technical_analysis.py` → `core/signal_enhancement_engine.py`
2. **Trading Execution**: `autotrade/trading_engine.py` → `api/indodax_api.py`
3. **Risk Management**: `autotrade/risk_manager.py` → `autotrade/portfolio.py`
4. **Database**: `core/database.py` (semua modul depend on this)

---

## 📝 Quick Navigation Commands

```bash
# Cari fungsi/class
grep -rn "class SignalEnhancementEngine" advanced_crypto_bot/

# Cari import modul
grep -rn "from analysis.ml_model_v4 import" advanced_crypto_bot/

# Lihat dependency tree
grep -rn "^from |^import " advanced_crypto_bot/bot.py | head -30

# Test specific module
pytest tests/test_scalper_dryrun_positions.py -v
```

---

**Next Steps:**
- Baca `OPERATIONS_FLOW_ALGORITHMA.md` untuk flow detail
- Baca `COMMAND_REFERENCE.md` untuk Telegram commands
- Baca `DOCUMENTATION_RULES.md` untuk coding standards
