# 📁 Advanced Crypto Trading Bot - Project Structure

## 🏗️ Directory Organization

```
advanced-crypto-bot/
├── bot.py                          # Main entry point
├── PROJECT_STRUCTURE.md            # This file
│
├── core/                           # Core system modules
│   ├── __init__.py
│   ├── config.py                   # Configuration & settings
│   ├── database.py                 # SQLite database wrapper
│   ├── logger.py                   # Logging system
│   └── utils.py                    # Utility functions
│
├── api/                            # External API integrations
│   ├── __init__.py
│   ├── indodax_api.py              # Indodax REST API wrapper
│   └── websocket_handler.py        # WebSocket handler (disabled)
│
├── analysis/                       # Technical & ML analysis
│   ├── __init__.py
│   ├── technical_analysis.py       # TA indicators (RSI, MACD, etc)
│   ├── ml_model.py                 # ML Model V1 (Random Forest)
│   ├── ml_model_v2.py            # ML Model V2 (Gradient Boosting)
│   ├── signal_analyzer.py        # Signal quality analyzer
│   └── support_resistance.py     # S/R level detection
│
├── trading/                        # Trading & risk modules
│   ├── __init__.py
│   ├── trading_engine.py           # Signal generation & trading logic
│   ├── risk_manager.py           # Risk management
│   ├── portfolio.py              # Portfolio tracking
│   ├── price_monitor.py          # Price monitoring & alerts
│   ├── scalper_module.py         # Manual trading module (DRYRUN support)
│   ├── smart_hunter_integration.py # Smart Hunter integration (DRYRUN support)
│   ├── smart_profit_hunter.py    # Profit hunting logic (DRYRUN/REAL)\n│   └── ultra_hunter.py           # Ultra conservative hunter (DRYRUN/REAL) (DRYRUN support)
│   └── ultra_hunter.py           # Ultra conservative hunter (DRYRUN support)
│
├── signals/                        # Signal processing
│   ├── __init__.py
│   ├── signal_db.py              # Signal database
│   ├── signal_filter_v2.py       # Signal validation filter
│   ├── signal_quality_engine.py  # Quality scoring engine
│   └── signal_queue.py           # Signal queue & scheduler
│
├── cache/                          # Caching & state management
│   ├── __init__.py
│   ├── price_cache.py            # In-memory price cache
│   ├── redis_price_cache.py      # Redis price cache
│   ├── redis_state_manager.py    # Redis state management
│   └── redis_task_queue.py       # Redis task queue
│
├── workers/                        # Background workers
│   ├── __init__.py
│   ├── async_worker.py           # Async task worker
│   ├── price_poller.py           # Price polling worker
│   └── worker.py                 # Background job worker
│
├── Documents/                      # Documentation
│   ├── README.md                 # Documentation index
│   ├── MASTER_DOCUMENTATION.md   # Main documentation
│   └── [100+ .md, .txt files]    # Guides, fixes, analysis
│
├── data/                           # Data storage
│   ├── trading.db                # Main database
│   ├── signals.db                # Signal database
│   └── ...
│
├── models/                         # ML model files
│   └── *.pkl                     # Trained models
│
├── logs/                           # Log files
│   └── *.log
│
    └── [historical files]
```

## 📊 Module Categories

### Core (core/)
System-level modules that other modules depend on:
- **config.py** - Centralized configuration
- **database.py** - Database operations with connection pooling
- **logger.py** - Structured logging
- **utils.py** - Common utilities

### API Integration (api/)
External exchange connectivity:
- **indodax_api.py** - Indodax REST API with async support
- **websocket_handler.py** - WebSocket (currently disabled)

### Analysis (analysis/)
Market analysis and ML prediction:
- **technical_analysis.py** - TA indicators with safe calculations
- **ml_model.py** & **ml_model_v2.py** - ML prediction models
- **signal_analyzer.py** - Signal quality analysis
- **support_resistance.py** - Auto S/R detection

### Trading (trading/)
Trading execution and management:
- **trading_engine.py** - Main trading logic with signal generation
- **risk_manager.py** - Risk metrics and limits
- **portfolio.py** - Position tracking
- **scalper_module.py** - Manual trading interface

### Signals (signals/)
Signal processing pipeline:
- **signal_filter_v2.py** - Signal validation
- **signal_quality_engine.py** - Confluence scoring
- **signal_db.py** - Signal persistence
- **signal_queue.py** - Async signal processing

### Cache (cache/)
Caching layer for performance:
- **price_cache.py** - Local price cache
- **redis_*.py** - Redis-backed caching

### Workers (workers/)
Background task processing:
- **price_poller.py** - Periodic price fetching
- **async_worker.py** - Async task execution
- **worker.py** - Background job processor

## 🔧 Import Pattern

After reorganization, imports follow this pattern:

```python
# Core modules
from core.config import Config
from core.database import Database
from core.utils import Utils

# API
from api.indodax_api import IndodaxAPI

# Analysis
from analysis.technical_analysis import TechnicalAnalysis
from analysis.ml_model_v2 import MLTradingModelV2

# Trading
from trading.trading_engine import TradingEngine
from trading.scalper_module import ScalperModule

# Signals
from signals.signal_quality_engine import SignalQualityEngine

# Cache
from cache.redis_price_cache import price_cache

# Workers
from workers.price_poller import PricePoller
```

## 📝 Notes

- All modules have `__init__.py` for proper package structure
- Old application files preserved in `old_app/` for reference
- Documentation organized in `Documents/` with 100+ guides
- Main entry point is `bot.py` in root directory

---

**Last Updated:** April 2026  
**Structure Version:** 2.0
