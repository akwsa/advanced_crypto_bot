# 📚 MASTER DOCUMENTATION — Advanced Crypto Trading Bot

**Last Updated:** 2026-04-11  
**Version:** 4.0 (Redis Integration Complete)  
**Status:** ✅ Production Ready

---

## 📋 TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Installation & Setup](#3-installation--setup)
4. [Running the Bot](#4-running-the-bot)
5. [All Commands](#5-all-commands)
6. [ML Signal Collection Status](#6-ml-signal-collection-status)
7. [Phase 1: Redis Price Cache](#7-phase-1-redis-price-cache)
8. [Phase 2: Parallel Fetch](#8-phase-2-parallel-fetch)
9. [Phase 3: Async Workers](#9-phase-3-async-workers)
10. [Phase 4: Signal Queue + Scheduler](#10-phase-4-signal-queue--scheduler)
11. [ML Model Training](#11-ml-model-training)
12. [Performance Benchmarks](#12-performance-benchmarks)
13. [Troubleshooting](#13-troubleshooting)
14. [File Structure](#14-file-structure)

---

## 1. PROJECT OVERVIEW

### What is this Bot?
Advanced Crypto Trading Bot with real-time WebSocket/REST API polling, Machine Learning predictions, Technical Analysis, automated trading, risk management, and Telegram interface.

### Key Features
- 🔗 **Indodax Integration** — REST API polling + WebSocket (disabled)
- 🤖 **Machine Learning** — Random Forest + Gradient Boosting ensemble
- 📊 **Technical Analysis** — RSI, MACD, MA, Bollinger Bands, Volume
- 💬 **Telegram Interface** — Full command set + inline keyboards
- 💰 **Scalper Module** — Manual buy/sell with TP/SL management
- 🎯 **Auto Trading** — Dry run + real trading modes
- 📡 **Price Monitoring** — Support/resistance levels, alerts
- 🔍 **Smart Hunter** — Conservative position scanning
- 📈 **Portfolio Tracking** — P/L, performance metrics, risk management

### Tech Stack
| Component | Technology |
|-----------|------------|
| **Language** | Python 3.11+ |
| **ML Library** | scikit-learn (Random Forest, Gradient Boosting) |
| **Database** | SQLite (signals.db, prices.db, trades.db) |
| **Cache** | Redis 7.x (Phase 1-4) |
| **Messaging** | Telegram Bot API |
| **Exchange** | Indodax (REST API) |

---

## 2. ARCHITECTURE

### System Architecture
```
┌─────────────────────────────────────────────────────┐
│              BOT UTAMA (bot.py)                      │
│                                                      │
│  ┌─ Telegram Handlers (Commands + Callbacks)        │
│  ┌─ Price Monitor + Alerts                          │
│  ┌─ Trading Engine + Risk Manager                   │
│  ┌─ Portfolio Manager                               │
│  ┌─ ML Model (Random Forest / Gradient Boosting)    │
│  ┌─ Technical Analysis Engine                       │
│  ┌─ Scalper Module (Manual trading)                 │
│  ┌─ Smart Hunter Integration                        │
│  ┌─ Auto Trade Scheduler                            │
│                                                      │
│  Background Threads:                                 │
│  ├─ Price Poller (REST API, 15s interval)           │
│  ├─ Auto Trade Checker (5min interval)              │
│  ├─ ML Auto Retrain (24h interval)                  │
│  ├─ Background Worker (Phase 3: Async Queue)        │
│  └─ Task Scheduler (Phase 4: 4 periodic tasks)      │
└─────────────────────────────────────────────────────┘
           │                    │                    │
    ┌──────▼──────┐    ┌───────▼──────┐    ┌────────▼────────┐
    │  Redis      │    │  SQLite      │    │  Indodax API    │
    │  Server     │    │  Databases   │    │  (REST)         │
    │             │    │              │    │                 │
    │ • Price     │    │ • signals.db │    │ • Ticker        │
    │   Cache     │    │ • prices.db  │    │ • Order Book    │
    │ • Task      │    │ • trades.db  │    │ • Orders        │
    │   Queue     │    │ • users.db   │    │ • Balance       │
    │ • Signal    │    │              │    │ • Trade History │
    │   Queue     │    │              │    │                 │
    └─────────────┘    └──────────────┘    └─────────────────┘
```

### Data Flow
```
1. Price Poller → Fetch prices every 15s → Redis Cache + SQLite
2. Signal Generation → TA + ML analysis → signals.db
3. Auto Trade Check → Every 5min → Execute if threshold met
4. User Command → Instant response → Redis cache first, fallback API
```

---

## 3. INSTALLATION & SETUP

### Prerequisites
```bash
# Python 3.11+ required
python --version

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup (.env)
```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321

# Indodax API
INDODAX_API_KEY=your_api_key
INDODAX_SECRET_KEY=your_secret_key

# Trading
AUTO_TRADE_DRY_RUN=True
DRY_RUN_ENABLED=True

# Redis (Phase 1-4)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL=300

# Watchlist
WATCH_PAIRS=btcidr,ethidr,solidr,dogeidr,xrpidr,adaidr,pippinidr,bridr
```

### Redis Installation (Windows)
1. Download Redis for Windows: https://github.com/microsoftarchive/redis/releases
2. Extract and run `redis-server.exe`
3. Verify: `redis-cli ping` → `PONG`

### Python Redis Package
```bash
pip install redis
```

---

## 4. RUNNING THE BOT

### Quick Start (Windows)
```cmd
:: Start bot (foreground, with console)
start_bot.bat

:: Start bot (background, no console)
start_bot_bg.bat

:: Stop bot
stop_bot.bat
```

### Manual Start
```cmd
:: Set UTF-8 encoding (prevents UnicodeEncodeError on Windows)
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
python bot.py
```

### Verify Running
```cmd
tasklist | findstr python
:: Should show python.exe process
```

### Check Logs
```powershell
# Main log
Get-Content logs\trading_bot.log -Tail 20

# Poller log
Get-Content logs\smart_profit_hunter.log -Tail 20

# Error log
Get-Content logs\errors.log -Tail 20
```

---

## 5. ALL COMMANDS

### Main Bot Commands
| Command | Description | Admin Only |
|---------|-------------|------------|
| `/start` | Welcome message + menu | No |
| `/help` | Complete user guide | No |
| `/menu` | Quick command reference | No |
| `/cmd` | Command guide (bot/scalp/trade/pair/status) | No |

### Watchlist Commands
| Command | Description |
|---------|-------------|
| `/watch <PAIR>` or `/watch <P1>, <P2>` | Add pairs to watchlist |
| `/unwatch <PAIR>` or `/unwatch <P1>, <P2>` | Remove from watchlist |
| `/list` | View your watchlist |

### Price & Signals
| Command | Description |
|---------|-------------|
| `/price <PAIR>` | Quick price check (Redis cached) |
| `/signal <PAIR>` | Detailed trading signal |
| `/signals` | Signals for all watched pairs |
| `/position <PAIR>` | Position analysis with order book |
| `/scan` | Market scanner for opportunities |
| `/topvolume` | Top volume pairs |

### Portfolio & Trades
| Command | Description |
|---------|-------------|
| `/balance` | Portfolio balance + positions |
| `/trades` | Trade history |
| `/sync` | Sync trades from Indodax |
| `/performance` | Win rate, P/L, Sharpe ratio |
| `/monitor` | Price monitoring setup |
| `/set_sl <ID> <PRICE>` | Set stop loss |
| `/set_tp <ID> <PRICE>` | Set take profit |

### Auto Trading (Admin)
| Command | Description |
|---------|-------------|
| `/autotrade` | Toggle auto-trading |
| `/autotrade dryrun` | Enable simulation mode |
| `/autotrade real` | Enable real trading |
| `/autotrade off` | Disable auto-trading |
| `/autotrade_status` | Check auto-trade status |
| `/set_interval <minutes>` | Change scan interval |
| `/scheduler_status` | Check scheduler + signal queue |

### Auto-Trade Pairs
| Command | Description |
|---------|-------------|
| `/add_autotrade <PAIR>` | Add to auto-trade list |
| `/remove_autotrade <PAIR>` | Remove from auto-trade list |
| `/list_autotrade` | View auto-trade pairs |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/status` | Bot system status |
| `/start_trading` | Enable trading mode |
| `/stop_trading` | Disable trading mode |
| `/retrain` | Manually retrain ML model |
| `/backtest` | Run backtest |
| `/trade` | Manual trading |
| `/trade_auto_sell` | Auto sell positions |
| `/cancel <TRADE_ID>` | Cancel trade |

### ML Training & Analysis
| Command | Description |
|---------|-------------|
| `python -m analysis.ml_model_v2` | Train ML model V2 (built-in) |
| `/retrain` | Retrain ML via Telegram command |
| `/signal_report` | Analyze signal database via Telegram |
| `/signal_quality <PAIR>` | Analyze signal quality for pair |

### Scalper Commands (s_ prefix)
| Command | Description |
|---------|-------------|
| `/s_menu` | Scalper main menu |
| `/s_posisi` | View active positions (Redis cached) |
| `/s_buy <PAIR> <AMOUNT>` | Buy position |
| `/s_sell <PAIR>` | Sell position |
| `/s_sltp <PAIR> <TP> <SL>` | Set TP/SL |
| `/s_info <PAIR>` | Pair analysis |
| `/s_pair add <PAIR>` | Add monitoring pair |
| `/s_pair remove <PAIR>` | Remove monitoring pair |
| `/s_pair list` | List monitored pairs |
| `/s_portfolio` | View all scalper pairs |
| `/s_riwayat` | Trade history |
| `/s_sync` | Sync with Indodax |
| `/s_reset` | Reset all positions |
| `/s_refresh` | Refresh portfolio |
| `/s_close_all` | Close all positions |
| `/s_analisa <PAIR>` | Technical analysis |

### Convenience Aliases (no s_ prefix)
| Command | Maps To |
|---------|---------|
| `/buy <PAIR> <AMOUNT>` | `/s_buy` |
| `/sell <PAIR>` | `/s_sell` |
| `/sltp <PAIR> <TP> <SL>` | `/s_sltp` |
| `/posisi` | `/s_posisi` |
| `/analisa <PAIR>` | `/s_analisa` |

---

## 6. ML SIGNAL COLLECTION STATUS

### ✅ **YES — Signal Recording STILL ACTIVE!**

The bot **continues to collect** signal data into `data/signals.db`:

#### How It Works
```
Every polling cycle (15s):
  1. Fetch price from Indodax API
  2. Calculate TA indicators (RSI, MACD, MA, BB, Volume)
  3. Generate ML prediction
  4. Create signal (STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL)
  5. Save to signals.db ← THIS IS STILL RUNNING!
  6. Update Redis cache
```

#### Current Data Stats (as of 2026-04-11)
| Metric | Value |
|--------|-------|
| **Total Signals** | ~2,080+ (growing daily) |
| **Date Range** | 2026-04-06 → Present |
| **Unique Pairs** | 54 |
| **Distribution** | HOLD: 70%, STRONG_BUY: 10.5%, BUY: 8.6%, SELL: 6.2%, STRONG_SELL: 4.7% |

#### Where Data is Stored
| Database | Table | Columns |
|----------|-------|---------|
| `data/signals.db` | `signals` | symbol, price, recommendation, rsi, macd, ma_trend, bollinger, volume, ml_confidence, combined_strength, received_at |

#### How to Check Signal Count
```bash
# Quick count
python -c "
import sqlite3
conn = sqlite3.connect('data/signals.db')
count = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
print(f'Total signals: {count}')
conn.close()
"
```

#### Retraining Schedule
- **Manual**: Run `python ml_trainer.py --report` anytime
- **Auto**: Every 24 hours (when trading enabled)
- **Recommended**: Retrain when 3,000+ signals collected

---

## 7. PHASE 1: REDIS PRICE CACHE

### What It Does
Replaces in-memory dict with Redis-backed price cache. Survives bot restart.

### How It Works
```
Price Poller fetches price → Writes to 3 places:
  1. self.bot.price_data (dict in memory)
  2. price_cache (dict-based cache)
  3. redis_price_cache (Redis-backed) ← NEW!
```

### Files
| File | Purpose |
|------|---------|
| `redis_price_cache.py` | Redis price cache module |
| `bot.py` | Integration (import + write on fetch) |
| `price_poller.py` | Auto-write every poll |

### Configuration
```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL=300
```

### Verification
```bash
# Test Redis connection
python -c "from redis_price_cache import price_cache; print(price_cache.is_redis_available())"

# Test get/set
python -c "
from redis_price_cache import price_cache
price_cache.set_price('BTCIDR', 1245000000)
print(price_cache.get_price_sync('BTCIDR'))
"
```

### Commands Affected
- `/price` → Now shows `💾 Cache: 🟢 Redis` at bottom

---

## 8. PHASE 2: PARALLEL FETCH

### What It Does
Replaces sequential price fetching (35 calls × 3s = 105s) with parallel ThreadPoolExecutor (10 workers = ~3-5s).

### How It Works
```
/s_posisi called:
  1. Check Redis cache for all 35 pairs (~0.1s)
  2. Missing pairs → Fetch in parallel (10 threads, ~3-5s)
  3. Results → Cache to Redis (next call instant)
  4. Render response
```

### Files Modified
| File | Change |
|------|--------|
| `scalper_module.py` | `_get_price_sync` checks Redis first, parallel fetch for missing |
| `scalper_module.py` | `cmd_posisi` + `refresh_posisi_callback` use batch fetch |
| `bot.py` | `position` command uses Redis cache first |

### Performance Improvement
| Command | Before | After | Improvement |
|---------|--------|-------|-------------|
| `/s_posisi` | ~30-100s | ~0.5-5s | ⚡ 20x faster |
| `/price` | ~2-5s | ~0.1s | ⚡ 20-50x faster |

---

## 9. PHASE 3: ASYNC WORKERS

### What It Does
Background worker thread processes tasks from Redis queue. Bot never hangs on heavy operations.

### Architecture
```
User Command → Bot (instant reply "Processing...")
                    ↓
              Redis Task Queue
                    ↓
          Background Worker (separate thread)
                    ↓
          Process heavy task → Send result via Telegram API
```

### Files
| File | Purpose |
|------|---------|
| `redis_task_queue.py` | Task queue with priority, result storage |
| `async_worker.py` | Background worker that processes tasks |
| `bot.py` | Worker initialization + start in `run()` |

### How to Use
```python
from redis_task_queue import task_queue

# Push task
task_id = task_queue.push_task("s_posisi", user_id=123, chat_id=123)

# Check result
result = task_queue.get_result(task_id)
```

---

## 10. PHASE 4: SIGNAL QUEUE + SCHEDULER

### What It Does
Periodic signal scanning, auto-trade queue, and scheduled maintenance tasks.

### Scheduled Tasks
| Task | Interval | Function |
|------|----------|----------|
| **market_scan** | 5 minutes | Scan all pairs for STRONG_BUY/STRONG_SELL signals |
| **db_cleanup** | 6 hours | Cleanup price data >30 days old |
| **signal_stats** | 1 hour | Update signal queue statistics |
| **cache_health** | 30 minutes | Check Redis + cache health |

### Signal Queue
Strong signals detected by market scanner are queued in Redis:
- STRONG_BUY → Priority 10 → Queued for auto-trade
- STRONG_SELL → Priority 10 → Queued for auto-sell
- BUY/SELL → Priority 5 → Queued for review

### New Commands
| Command | Description |
|---------|-------------|
| `/scheduler_status` | View scheduler + signal queue status |

### Files
| File | Purpose |
|------|---------|
| `signal_queue.py` | SignalQueue + TaskScheduler classes |
| `bot.py` | `_setup_scheduler_tasks()` + scheduled task methods |
| `scalper_module.py` | Fixed callback handlers (s_buy:, s_sell:, s_menu) |

### Callback Links Fixed
| Button | Before | After |
|--------|--------|-------|
| **⬇️ BUY BTC** | ❌ No response | ✅ Shows buy confirmation |
| **⬆️ SELL BTC** | ❌ No response | ✅ Shows sell confirmation |
| **📊 Menu** | ❌ No handler | ✅ Returns to main menu |

---

## 11. ML MODEL TRAINING

### Current Model Stats
| Metric | Value |
|--------|-------|
| **Best Model** | Gradient Boosting |
| **Test Accuracy** | 80.05% |
| **Training Data** | 2,080 signals |
| **Features** | 6 (price, RSI, MACD, MA, BB, Volume) |
| **Data Leakage** | ✅ Fixed (no ml_confidence/combined_strength) |

### Feature Importance
| Feature | Importance |
|---------|------------|
| price_scaled | 40.29% |
| macd_encoded | 31.87% |
| rsi_encoded | 17.27% |
| ma_encoded | 10.57% |
| volume_encoded | 0.00% |
| bollinger_encoded | 0.00% |

### How to Retrain
```bash
# Quick train
python ml_trainer.py

# Train with report
python ml_trainer.py --report

# Train specific model
python ml_trainer.py --model gradient_boosting
```

### Model Files
| File | Purpose |
|------|---------|
| `models/signal_model_v2.pkl` | Newly trained model (TA-only) |
| `models/trading_model.pkl` | Original model (still used by bot) |
| `ml_training_report.txt` | Training report |

---

## 12. PERFORMANCE BENCHMARKS

### Response Times
| Command | Before Redis | After Redis | Improvement |
|---------|-------------|-------------|-------------|
| `/price` | 2-5s | ~0.1s | ⚡ 20-50x |
| `/s_posisi` (1st call) | 30-100s | 3-5s | ⚡ 10-30x |
| `/s_posisi` (2nd call) | 30-100s | ~0.5s | ⚡ 60-200x |
| `/s_menu` | 5-10s | ~1s | ⚡ 5-10x |

### Resource Usage
| Metric | Value |
|--------|-------|
| **RAM (Bot)** | ~200-250 MB |
| **RAM (Redis)** | ~50-100 MB |
| **CPU** | ~1-2 cores (of 4) |
| **Disk (Database)** | ~200 MB |
| **Redis Keys** | ~8-40 (price:* + task_queue:*) |

---

## 13. TROUBLESHOOTING

### Bot Won't Start
```cmd
:: Check if another Python process is running
tasklist | findstr python

:: Kill existing process
taskkill /F /PID <PID>

:: Start with UTF-8 encoding
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
python bot.py
```

### Redis Not Connected
```bash
# Check Redis server
redis-cli ping
# Should return: PONG

# If not running, start Redis server
redis-server.exe

# Check Python redis package
python -c "import redis; print(redis.__version__)"
```

### UnicodeEncodeError on Windows
```cmd
:: Set UTF-8 encoding before running
set PYTHONIOENCODING=utf-8
python bot.py
```

### Rate Limit (HTTP 429)
- Bot automatically pauses polling for 60s cooldown
- Reduce watched pairs or increase poll interval
- Check `price_poller.py` for rate limit handling

### Database Corruption
```bash
# Backup database
copy data\signals.db data\signals.db.backup

# If corrupted, bot will recreate on next run
```

---

## 14. FILE STRUCTURE

```
C:\advanced_crypto_bot\
│
├── bot.py                          # Main bot file (updated with Phase 1-4)
├── config.py                       # Configuration
├── database.py                     # SQLite database wrapper
├── technical_analysis.py           # TA indicators
├── ml_model.py                     # ML trading model
├── trading_engine.py               # Trade execution
├── risk_manager.py                 # Risk management
├── portfolio.py                    # Portfolio tracking
├── websocket_handler.py            # WebSocket (disabled)
├── logger.py                       # Custom logging
├── utils.py                        # Utility functions
├── price_monitor.py                # Price level monitoring
├── indodax_api.py                  # Indodax REST API wrapper
├── price_poller.py                 # REST API poller (updated with Redis)
├── scalper_module.py               # Manual scalping (fixed links)
├── smart_hunter_integration.py     # Smart Hunter module
├── backtester.py                   # Backtesting tool
│
├── cache/redis_price_cache.py      # Phase 1: Redis price cache
├── cache/redis_task_queue.py       # Phase 3: Task queue
├── workers/async_worker.py         # Phase 3: Background worker
├── signals/signal_queue.py         # Phase 4: Signal Queue + Scheduler
│
├── trading/smart_profit_hunter.py   # Smart Hunter (DRYRUN/REAL)
├── trading/ultra_hunter.py          # Ultra Hunter (DRYRUN/REAL)
│
├── start_bot.bat                   # Start bot (foreground)
├── start_bot_bg.bat                # Start bot (background)
├── stop_bot.bat                    # Stop bot
│
├── .env                            # Environment variables
├── .gitignore                      # Git ignore
│
├── data/
│   ├── signals.db                  # Signal database (single source of truth)
│   ├── trading.db                  # Main database (prices, trades, users, watchlist)
│   └── cache/                      # Cache data
│
├── models/
│   ├── trading_model.pkl           # Original ML model (used by bot)
│   └── signal_model_v2.pkl         # Newly trained model (TA-only)
│
├── logs/
│   ├── trading_bot.log             # Main log
│   ├── smart_profit_hunter.log     # Poller log
│   ├── errors.log                  # Errors only
│   └── bot_stdout.log              # Console output
│
└── docs/ (59 .md files)
    ├── MASTER_DOCUMENTATION.md     # THIS FILE
    ├── ML_TRAINING_DEMO.md         # ML training demo
    ├── REDIS_ARCHITECTURE_ANALYSIS.md
    ├── COMMANDS_GUIDE.md
    └── ... (55 more)
```

---

## 📝 CHANGELOG

### Version 4.0 (2026-04-11)
- ✅ Phase 1: Redis Price Cache
- ✅ Phase 2: Parallel Fetch (ThreadPoolExecutor)
- ✅ Phase 3: Async Workers (Background Queue)
- ✅ Phase 4: Signal Queue + Scheduler (4 tasks)
- ✅ Fixed menu callback links (s_buy:, s_sell:, s_menu)
- ✅ Added `/scheduler_status` command
- ✅ ML model retrained (2,080 signals, 80% accuracy, TA-only)
- ✅ Data leakage fixed (no ml_confidence/combined_strength)
- ✅ Added `start_bot.bat`, `start_bot_bg.bat`, `stop_bot.bat`
- ✅ `/s_posisi` buttons colored (🟢 profit / 🔴 loss)
- ✅ `/s_posisi` info in button text (Entry → Current | P/L%)

### Version 3.0 (Previous)
- ML model training script
- Signal database collection
- Scalper module integration
- Smart Hunter integration

---

## 📞 SUPPORT

For issues or questions:
1. Check logs: `logs/trading_bot.log`, `logs/errors.log`
2. Review this documentation
3. Check Redis: `redis-cli ping` → `PONG`
4. Verify bot process: `tasklist | findstr python`

---

**Document Created:** 2026-04-11  
**Status:** ✅ Complete — All 4 phases documented  
**Next Review:** When new features added
