#!/usr/bin/env python3
"""
Comprehensive module health check for Advanced Crypto Trading Bot
Tests all imports, initializations, and connections
"""

import sys
import os
import time

# Add current directory to path
sys.path.insert(0, '.')

print("=" * 80)
print("ADVANCED CRYPTO BOT - MODULE HEALTH CHECK")
print("=" * 80)
print()

errors = []
warnings = []

# =============================================================================
# 1. CORE MODULES
# =============================================================================
print("1️⃣  Testing CORE modules...")
try:
    from core.config import Config
    print("   ✅ Config loaded")
    
    # Check required config
    required_attrs = ['TELEGRAM_BOT_TOKEN', 'ADMIN_IDS', 'WATCH_PAIRS', 'DATABASE_PATH']
    for attr in required_attrs:
        if hasattr(Config, attr):
            print(f"   ✅ Config.{attr} exists")
        else:
            msg = f"Config missing: {attr}"
            warnings.append(msg)
            print(f"   ⚠️  {msg}")
    
    if not Config.TELEGRAM_BOT_TOKEN:
        warnings.append("TELEGRAM_BOT_TOKEN is empty")
        print("   ⚠️  TELEGRAM_BOT_TOKEN not set")
    
    print("   ✅ Core modules OK")
except Exception as e:
    errors.append(f"Core config failed: {e}")
    print(f"   ❌ FAILED: {e}")

try:
    from core.logger import CustomLogger
    logger = CustomLogger('health_check').get_logger()
    print("   ✅ Logger initialized")
except Exception as e:
    errors.append(f"Logger failed: {e}")
    print(f"   ❌ Logger FAILED: {e}")

try:
    from core.database import Database
    start = time.time()
    db = Database()
    elapsed = (time.time() - start) * 1000
    print(f"   ✅ Database initialized ({elapsed:.0f}ms)")
    
    # Test DB connection
    if hasattr(db, 'get_connection'):
        print("   ✅ DB connection method exists")
except Exception as e:
    errors.append(f"Database failed: {e}")
    print(f"   ❌ Database FAILED: {e}")

try:
    from core.utils import Utils
    print("   ✅ Utils imported")
except Exception as e:
    errors.append(f"Utils failed: {e}")
    print(f"   ❌ Utils FAILED: {e}")

print()

# =============================================================================
# 2. API MODULES
# =============================================================================
print("2️⃣  Testing API modules...")
try:
    from api.indodax_api import IndodaxAPI
    indodax = IndodaxAPI()
    print("   ✅ IndodaxAPI initialized")
    
    # Check if API keys are set
    if indodax.api_key and indodax.secret_key:
        print("   ✅ API keys configured")
    else:
        warnings.append("Indodax API keys not configured (read-only mode)")
        print("   ⚠️  API keys not configured (read-only mode)")
except Exception as e:
    errors.append(f"IndodaxAPI failed: {e}")
    print(f"   ❌ IndodaxAPI FAILED: {e}")

print()

# =============================================================================
# 3. ANALYSIS MODULES
# =============================================================================
print("3️⃣  Testing ANALYSIS modules...")
try:
    from analysis.technical_analysis import TechnicalAnalysis
    print("   ✅ TechnicalAnalysis imported")
except Exception as e:
    errors.append(f"TechnicalAnalysis failed: {e}")
    print(f"   ❌ TechnicalAnalysis FAILED: {e}")

# Skip ML model init (too slow) - just test import
try:
    from analysis.ml_model import MLTradingModel
    print("   ✅ MLTradingModel (V1) imported (init skipped - takes too long)")
except Exception as e:
    errors.append(f"MLTradingModel V1 import failed: {e}")
    print(f"   ❌ MLTradingModel V1 import FAILED: {e}")

try:
    from analysis.ml_model_v2 import MLTradingModelV2
    print("   ✅ MLTradingModelV2 imported (init skipped - takes too long)")
except Exception as e:
    errors.append(f"MLTradingModelV2 import failed: {e}")
    print(f"   ❌ MLTradingModelV2 import FAILED: {e}")

try:
    from analysis.signal_analyzer import SignalAnalyzer
    print("   ✅ SignalAnalyzer imported")
except Exception as e:
    errors.append(f"SignalAnalyzer failed: {e}")
    print(f"   ❌ SignalAnalyzer FAILED: {e}")

try:
    from analysis.support_resistance import SupportResistanceDetector
    print("   ✅ SupportResistanceDetector imported")
except Exception as e:
    errors.append(f"SupportResistanceDetector failed: {e}")
    print(f"   ❌ SupportResistanceDetector FAILED: {e}")

print()

# =============================================================================
# 4. TRADING MODULES
# =============================================================================
print("4️⃣  Testing TRADING modules...")
try:
    from trading.trading_engine import TradingEngine
    print("   ✅ TradingEngine imported")
except Exception as e:
    errors.append(f"TradingEngine failed: {e}")
    print(f"   ❌ TradingEngine FAILED: {e}")

try:
    from trading.risk_manager import RiskManager
    print("   ✅ RiskManager imported")
except Exception as e:
    errors.append(f"RiskManager failed: {e}")
    print(f"   ❌ RiskManager FAILED: {e}")

try:
    from trading.portfolio import Portfolio
    print("   ✅ Portfolio imported")
except Exception as e:
    errors.append(f"Portfolio failed: {e}")
    print(f"   ❌ Portfolio FAILED: {e}")

try:
    from trading.price_monitor import PriceMonitor
    print("   ✅ PriceMonitor imported")
except Exception as e:
    errors.append(f"PriceMonitor failed: {e}")
    print(f"   ❌ PriceMonitor FAILED: {e}")

# Skip heavy module init - just test import
try:
    from trading.scalper_module import ScalperModule
    print("   ✅ ScalperModule imported (init skipped - heavy)")
except Exception as e:
    errors.append(f"ScalperModule import failed: {e}")
    print(f"   ❌ ScalperModule import FAILED: {e}")

try:
    from trading.smart_hunter_integration import SmartHunterBotIntegration
    print("   ✅ SmartHunterBotIntegration imported")
except Exception as e:
    errors.append(f"SmartHunterBotIntegration failed: {e}")
    print(f"   ❌ SmartHunterBotIntegration FAILED: {e}")

print()

# =============================================================================
# 5. SIGNAL MODULES
# =============================================================================
print("5️⃣  Testing SIGNAL modules...")
try:
    from signals.signal_quality_engine import SignalQualityEngine
    print("   ✅ SignalQualityEngine imported")
except Exception as e:
    errors.append(f"SignalQualityEngine failed: {e}")
    print(f"   ❌ SignalQualityEngine FAILED: {e}")

try:
    from signals.signal_queue import signal_queue, scheduler
    print("   ✅ Signal queue & scheduler imported")
except Exception as e:
    errors.append(f"Signal queue failed: {e}")
    print(f"   ❌ Signal queue FAILED: {e}")

try:
    from signals.signal_db import SignalDatabase
    print("   ✅ SignalDatabase imported")
except Exception as e:
    errors.append(f"SignalDatabase failed: {e}")
    print(f"   ❌ SignalDatabase FAILED: {e}")

try:
    from signals.signal_filter_v2 import SignalFilterV2
    print("   ✅ SignalFilterV2 imported")
except Exception as e:
    errors.append(f"SignalFilterV2 failed: {e}")
    print(f"   ❌ SignalFilterV2 FAILED: {e}")

print()

# =============================================================================
# 6. CACHE MODULES
# =============================================================================
print("6️⃣  Testing CACHE modules...")
try:
    from cache.redis_price_cache import price_cache as redis_price_cache
    print("   ✅ Redis price cache imported")
    
    # Test Redis connection
    try:
        redis_ok = redis_price_cache.is_redis_available()
        if redis_ok:
            print("   ✅ Redis connection OK")
        else:
            warnings.append("Redis not available (using fallback dict)")
            print("   ⚠️  Redis not available (using fallback dict)")
    except Exception as e:
        warnings.append(f"Redis check failed: {e}")
        print(f"   ⚠️  Redis check failed: {e}")
except Exception as e:
    errors.append(f"Redis price cache failed: {e}")
    print(f"   ❌ Redis price cache FAILED: {e}")

try:
    from cache.redis_state_manager import state_manager
    print("   ✅ Redis state manager imported")
except Exception as e:
    errors.append(f"Redis state manager failed: {e}")
    print(f"   ❌ Redis state manager FAILED: {e}")

try:
    from cache.price_cache import PriceCache
    print("   ✅ PriceCache (local) imported")
except Exception as e:
    errors.append(f"PriceCache failed: {e}")
    print(f"   ❌ PriceCache FAILED: {e}")

print()

# =============================================================================
# 7. WORKER MODULES
# =============================================================================
print("7️⃣  Testing WORKER modules...")
try:
    from workers.async_worker import BackgroundWorker
    print("   ✅ BackgroundWorker imported")
except Exception as e:
    errors.append(f"BackgroundWorker failed: {e}")
    print(f"   ❌ BackgroundWorker FAILED: {e}")

try:
    from workers.price_poller import PricePoller
    print("   ✅ PricePoller imported")
except Exception as e:
    errors.append(f"PricePoller failed: {e}")
    print(f"   ❌ PricePoller FAILED: {e}")

print()

# =============================================================================
# 8. EXTERNAL DEPENDENCIES
# =============================================================================
print("8️⃣  Testing EXTERNAL dependencies...")
external_deps = [
    ('telegram', 'python-telegram-bot'),
    ('telegram.ext', 'python-telegram-bot extensions'),
    ('pandas', 'pandas'),
    ('numpy', 'numpy'),
    ('sklearn', 'scikit-learn'),
    ('requests', 'requests'),
]

for module_name, display_name in external_deps:
    try:
        __import__(module_name)
        print(f"   ✅ {display_name} ({module_name})")
    except ImportError as e:
        errors.append(f"Missing dependency: {module_name}")
        print(f"   ❌ {display_name} ({module_name}) - NOT INSTALLED")

print()

# =============================================================================
# SUMMARY
# =============================================================================
print("=" * 80)
print("📊 HEALTH CHECK SUMMARY")
print("=" * 80)

if errors:
    print(f"\n❌ ERRORS ({len(errors)}):")
    for error in errors:
        print(f"   • {error}")
else:
    print("\n✅ No critical errors found!")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(f"   • {warning}")
else:
    print("\n✅ No warnings!")

print(f"\n{'=' * 80}")
if errors:
    print(f"❌ RESULT: {len(errors)} errors, {len(warnings)} warnings")
    print("⚠️  Bot may have issues starting. Please fix errors above.")
else:
    print(f"✅ RESULT: All modules healthy! ({len(warnings)} warnings)")
    print("💡 Bot should start successfully.")
print(f"{'=' * 80}")

# Exit with error code if there are errors
sys.exit(1 if errors else 0)
