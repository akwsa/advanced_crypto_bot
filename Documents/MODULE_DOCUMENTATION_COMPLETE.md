# 📚 COMPREHENSIVE MODULE DOCUMENTATION

**Date**: 2026-04-14
**Status**: All modules verified and documented

---

## 🏗️ ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                         bot.py (Main)                        │
│  • Telegram Bot Handler                                      │
│  • Command Routing                                           │
│  • Signal Generation Orchestration                           │
│  • Auto-Trading Control (DRYMODE/REALTRADE)                 │
└──────────────┬──────────────────────────────┬────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────┐          ┌──────────────────────────┐
│   Trading Engine     │          │   Redis Infrastructure   │
│  • Signal Generation │          │  • redis_price_cache.py  │
│  • TA + ML Combo     │          │  • redis_state_manager.py│
│  • Risk Management   │          │  • redis_task_queue.py   │
└──────────┬───────────┘          └──────────┬───────────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────┐          ┌──────────────────────────┐
│   ML Models          │          │   Background Workers     │
│  • ml_model.py (V1)  │          │  • async_worker.py       │
│  • ml_model_v2.py    │          │  • signal_queue.py       │
│  • Multi-class       │          │  • price_poller.py       │
└──────────┬───────────┘          └──────────┬───────────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────┐          ┌──────────────────────────┐
│   Technical Analysis │          │   Specialized Modules    │
│  • technical_analysis│          │  • scalper_module.py     │
│  • 15+ indicators    │          │  • smart_hunter_*.py     │
│  • Support/Resistance│          │  • signal_analyzer.py    │
└──────────────────────┘          └──────────────────────────┘
```

---

## 📦 MODULE CATALOG

### 1️⃣ **bot.py** - Main Orchestrator
**Purpose**: Central bot controller with Telegram interface  
**Lines**: ~8,300  
**Dependencies**: All modules  

**Key Responsibilities**:
- Telegram command handling
- Signal generation orchestration
- Auto-trading mode control (DRYMODE/REALTRADE)
- WebSocket/REST API price polling
- Background task management
- User watchlist management

**Main Commands**:
```
/start, /menu, /help     - User interface
/watch, /unwatch, /list  - Watchlist management
/signal, /price          - Signal generation
/autotrade, /autotrade_status - Auto-trading control
/trade, /balance, /trades - Trading operations
/s_menu, /s_buy, /s_sell - Scalper module interface
```

**Auto-Trading Modes**:
- **DRYMODE** (`/autotrade dryrun`): Simulation, no real trades
- **REALTRADE** (`/autotrade real`): Real money trading
- **DISABLED** (`/autotrade off`): No auto-trading

**Signal Generation Flow**:
1. Fetch historical data (60+ candles)
2. Run Technical Analysis (15+ indicators)
3. Run ML Prediction (V1 or V2 model)
4. Combine TA + ML (60/40 weighting)
5. Apply stabilization filter (anti-jump)
6. Save to SQLite DB
7. Send to Telegram user

---

### 2️⃣ **trading_engine.py** - Signal Generator
**Purpose**: Combine TA + ML into final trading signal  
**Lines**: ~165  

**Key Function**: `generate_signal()`
```python
signal = trading_engine.generate_signal(
    pair='BTCIDR',
    ta_signals={...},           # From TechnicalAnalysis
    ml_prediction=True/False,   # From ML model
    ml_confidence=0.75,         # ML confidence 0-1
    ml_signal_class='BUY'       # V2 only: signal class
)
```

**Signal Strength Calculation**:
```
combined_strength = (TA_strength × 0.6) + (ML_strength × 0.4)
```

**Thresholds** (UPDATED 2026-04-14):
```python
STRONG_THRESHOLD = 0.45     # Was 0.6 - more reachable
MODERATE_THRESHOLD = 0.20   # Was 0.25 - more sensitive
ML_STRONG_THRESHOLD = 0.65  # Was 0.70 - slightly relaxed
CONFIDENCE_THRESHOLD = 0.55 # Min ML confidence (unchanged)
```

**Signal Classes**:
- `STRONG_BUY`: combined > 0.45 AND ML conf > 0.65
- `BUY`: combined > 0.20
- `HOLD`: mixed signals or low confidence
- `SELL`: combined < -0.20
- `STRONG_SELL`: combined < -0.45 AND ML conf > 0.65

---

### 3️⃣ **ml_model_v2.py** - Advanced ML Model
**Purpose**: Multi-class ML prediction with improved features  
**Lines**: ~717  

**Model Type**: Ensemble (RandomForest + GradientBoosting)  
**Classes**: `STRONG_BUY`, `BUY`, `HOLD`, `SELL`, `STRONG_SELL`

**Features** (50+):
- Price returns (1, 5, 10, 20 periods)
- Moving averages (SMA 9, 20, 50)
- RSI, MACD, Bollinger Bands
- Support/Resistance levels
- Volume anomaly detection
- Market regime indicators

**Training**:
- Auto-retrain every 24 hours
- Minimum 60 candles required
- Class balancing with `class_weight='balanced'`

**Output**:
```python
(predicted_class, confidence, signal_class)
# Example: (4, 0.75, 'STRONG_BUY')
```

---

### 4️⃣ **signal_analyzer.py** - Historical Signal Quality
**Purpose**: Analyze historical signal accuracy  
**Lines**: ~300  

**NOT signal_analyzer_v2.py** - This is a testing tool, NOT used in production

**Key Functions**:
```python
# Get signal quality report
report = analyzer.get_signal_quality('BTCIDR', 'BUY')
# Returns: {win_rate, score (1-10), quality_grade, ...}

# Check if signal should be taken
should_trade, report = analyzer.should_trade('BTCIDR', 'BUY', min_score=5)

# Get comprehensive pair summary
summary = analyzer.get_pair_summary('BTCIDR', days=30)
```

**Scoring System**:
- Win rate (40%)
- Average profit (20%)
- Data volume (20%)
- ML confidence (20%)

**Quality Grades**:
- **A** (8-10): Excellent - auto-trade even in dry run
- **B** (6-7): Good - recommended
- **C** (4-5): Average - caution
- **D** (1-3): Poor - avoid

**Database Dependencies**:
- `data/signals.db`: Historical signals
- `data/trading.db`: Price history for validation

---

### 5️⃣ **Redis Infrastructure** (3 Modules)

#### 5a. **redis_price_cache.py**
**Purpose**: Redis-backed price cache with dict fallback  
**Lines**: ~270  

**API**:
```python
from redis_price_cache import price_cache

# Get price (auto Redis → fallback dict)
price = price_cache.get_price_sync('BTCIDR')

# Update price (write to Redis + dict)
price_cache.set_price('BTCIDR', 1245000000)
```

**Features**:
- TTL: 300 seconds (5 minutes)
- Automatic fallback to dict if Redis down
- Thread-safe operations

#### 5b. **redis_state_manager.py**
**Purpose**: Unified state management via Redis  
**Lines**: ~457  

**State Types**:
- Active positions (scalper positions)
- Price data (real-time history)
- Historical data (cached)
- ML model metadata

**API**:
```python
from redis_state_manager import state_manager

# Positions
state_manager.set_position('btcidr', {...})
pos = state_manager.get_position('btcidr')

# Price data
state_manager.set_price_data('btcidr', {...})
data = state_manager.get_price_data('btcidr')

# Historical data
state_manager.set_historical('btcidr', df)
df = state_manager.get_historical('btcidr')
```

**Features**:
- TTL: 86400 seconds (24 hours)
- Thread-safe with locks
- Background sync to Redis

#### 5c. **redis_task_queue.py**
**Purpose**: Async task queue for heavy commands  
**Lines**: ~226  

**Workflow**:
```python
from redis_task_queue import task_queue

# Push task to queue
task_id = task_queue.push_task('s_posisi', user_id=123, data={...})

# Worker picks up task
task = task_queue.pop_task()  # Blocking wait

# Mark complete
task_queue.mark_complete(task_id, result={...})

# Get result
result = task_queue.get_result(task_id)
```

**Features**:
- Results expire after 1 hour
- Multiple workers can scale horizontally
- Tasks survive bot restarts

---

### 6️⃣ **async_worker.py** - Background Worker
**Purpose**: Process heavy tasks asynchronously  
**Lines**: ~170  

**Task Types**:
- `s_posisi`: Scalper position analysis
- `s_menu`: Scalper menu data
- Other heavy DB operations

**Architecture**:
```
bot.py ──push_task──> Redis Queue ──pop_task──> async_worker.py
                                                      │
                                               Process task
                                                      │
bot.py <──send_result── Redis Result <──mark_complete──┘
```

---

### 7️⃣ **signal_queue.py** - Signal Queue + Scheduler
**Purpose**: Periodic signal scanning and auto-trade queue  
**Lines**: ~270  

**Features**:
- Signal Scanner: Scan all pairs every 5 minutes
- Auto-Trade Queue: Queue BUY/SELL signals
- Smart Alerts: Notify only strong signals (STRONG_BUY/STRONG_SELL)

**Scheduler Tasks**:
1. Market scanner (every 5 min)
2. Database cleanup (every 6 hours)
3. Signal stats update (every 1 hour)
4. Redis cache health check (every 30 min)

---

### 8️⃣ **scalper_module.py** - Scalping Tool
**Purpose**: Quick manual scalping operations  
**Dependencies**: bot.py (config sharing)

**Commands**:
```
/s_menu         - Scalper main menu
/s_posisi       - View positions
/s_analisa      - Analyze pair
/s_buy <pair>   - Manual buy
/s_sell <pair>  - Manual sell
```

**Mode Support**:
- Works in both DRYMODE and REALTRADE
- Uses main bot's dry-run config

---

### 9️⃣ **smart_hunter_integration.py** - Conservative Hunter
**Purpose**: Ultra-conservative signal hunting  
**Dependencies**: bot.py (main bot reference)

**Commands**:
```
/ultrahunter           - Toggle hunter
/hunter_status         - Check status
/smarthunter           - Hunter control
/smarthunter_status    - Hunter status
```

**Strategy**:
- Very high confidence threshold (>75%)
- Only trades on extreme oversold/overbought
- Risk-averse approach

---

## 🔧 CONFIGURATION

### Environment Variables (`.env`)
```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_IDS=123456,789012

# Indodax API (Optional for DRYMODE)
INDODAX_API_KEY=your_api_key
INDODAX_SECRET_KEY=your_secret_key

# Auto-Trading
AUTO_TRADING_ENABLED=true
AUTO_TRADE_DRY_RUN=true  # True = simulation, False = real

# Trading Settings
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=5.0
MIN_TRADE_AMOUNT=100000
MAX_TRADE_AMOUNT=5000000

# ML Settings
CONFIDENCE_THRESHOLD=0.55  # Min ML confidence

# Redis (Optional)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL=300
REDIS_STATE_TTL=86400
```

---

## 🚀 STARTUP FLOW

1. **Initialize Database** (`database.py`)
2. **Load ML Model** (V2 with V1 fallback)
3. **Initialize Trading Engine** (`trading_engine.py`)
4. **Initialize Redis** (price cache, state manager, task queue)
5. **Initialize Specialized Modules** (scalper, hunter, signal analyzer)
6. **Setup Telegram Handlers** (all commands)
7. **Load Watchlist from DB**
8. **Start Price Poller** (background thread)
9. **Start Redis State Syncer** (background thread)
10. **Start Async Worker** (Phase 3)
11. **Start Scheduler** (Phase 4)
12. **Start Telegram Polling** (main loop)

---

## 📊 DATA FLOW

```
User Command (Telegram)
        │
        ▼
┌─────────────────┐
│    bot.py       │
└────────┬────────┘
         │
         ├──> Fetch historical data (DB or API)
         │         │
         │         ▼
         │    ┌──────────────┐
         │    │ database.py  │
         │    └──────┬───────┘
         │           │
         │<──────────┘
         │
         ├──> Technical Analysis
         │         │
         │         ▼
         │    ┌──────────────────────┐
         │    │ technical_analysis.py│
         │    └──────┬───────────────┘
         │           │
         │<──────────┘
         │
         ├──> ML Prediction
         │         │
         │         ▼
         │    ┌──────────────┐
         │    │ ml_model_v2.py│
         │    └──────┬───────┘
         │           │
         │<──────────┘
         │
         ├──> Generate Signal
         │         │
         │         ▼
         │    ┌──────────────────┐
         │    │ trading_engine.py│
         │    └──────┬───────────┘
         │           │
         │<──────────┘
         │
         ├──> Apply Stabilization
         │         │
         │         ▼
         │    (bot.py internal)
         │
         ├──> Save to DB
         │         │
         │         ▼
         │    ┌──────────────┐
         │    │ signal_db.py │
         │    └──────┬───────┘
         │
         └──> Send to User
                   │
                   ▼
              Telegram Message
```

---

## 🔍 TROUBLESHOOTING

### Problem: No BUY signals
**Solution**: 
1. Check ML confidence distribution
2. Verify TA signal strengths
3. Review stabilization logs
4. **Fixed 2026-04-14**: Lowered thresholds, relaxed stabilization

### Problem: Redis connection failed
**Solution**:
- Check Redis server: `redis-cli ping`
- Verify `.env` Redis settings
- Bot will fallback to dict automatically

### Problem: ML model not trained
**Solution**:
- Wait for 60+ candles to accumulate
- Manually trigger: `/retrain`
- Check model files: `models/trading_model_v2.pkl`

### Problem: Signal not sent to user
**Solution**:
- Check HOLD filter (confidence < 0.5 filtered)
- Verify user has pair in watchlist
- Review logs for stabilization downgrades

---

## 📝 CHANGELOG

### 2026-04-14 - Signal Fix Update
- ✅ Lowered combined strength thresholds (0.6 → 0.45)
- ✅ Relaxed signal stabilization filter (jump 5 → 7)
- ✅ Added time-gap rule for signal changes
- ✅ Improved stabilization logging
- ✅ Verified all module connections
- ✅ Confirmed Redis integration working
- ✅ Documented all modules

### Previous
- Redis infrastructure added
- ML Model V2 implemented
- Scalper module integrated
- Smart Hunter added
- Signal queue + scheduler implemented
