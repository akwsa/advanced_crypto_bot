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
print("1. Testing CORE modules...")
try:
    from core.config import Config
    print("   [OK] Config loaded")
    
    # Check required config
    required_attrs = ['TELEGRAM_BOT_TOKEN', 'ADMIN_IDS', 'WATCH_PAIRS', 'DATABASE_PATH']
    for attr in required_attrs:
        if hasattr(Config, attr):
            print(f"   [OK] Config.{attr} exists")
        else:
            msg = f"Config missing: {attr}"
            warnings.append(msg)
            print(f"   [WARN] {msg}")
    
    if not Config.TELEGRAM_BOT_TOKEN:
        warnings.append("TELEGRAM_BOT_TOKEN is empty")
        print("   [WARN] TELEGRAM_BOT_TOKEN not set")
    
    print("   [OK] Core modules OK")
except Exception as e:
    errors.append(f"Core config failed: {e}")
    print(f"   [FAIL] FAILED: {e}")

try:
    from core.logger import CustomLogger
    logger = CustomLogger('health_check').get_logger()
    print("   [OK] Logger initialized")
except Exception as e:
    errors.append(f"Logger failed: {e}")
    print(f"   [FAIL] Logger FAILED: {e}")

try:
    from core.database import Database
    start = time.time()
    db = Database()
    elapsed = (time.time() - start) * 1000
    print(f"   [OK] Database initialized ({elapsed:.0f}ms)")
    
    # Test DB connection
    if hasattr(db, 'get_connection'):
        print("   [OK] DB connection method exists")
except Exception as e:
    errors.append(f"Database failed: {e}")
    print(f"   [FAIL] Database FAILED: {e}")

try:
    from core.utils import Utils
    print("   [OK] Utils imported")
except Exception as e:
    errors.append(f"Utils failed: {e}")
    print(f"   [FAIL] Utils FAILED: {e}")

print()

# =============================================================================
# 2. API MODULES
# =============================================================================
print("2. Testing API modules...")
try:
    from api.indodax_api import IndodaxAPI
    indodax = IndodaxAPI()
    print("   [OK] IndodaxAPI initialized")
    
    # Check if API keys are set
    if indodax.api_key and indodax.secret_key:
        print("   [OK] API keys configured")
    else:
        warnings.append("Indodax API keys not configured (read-only mode)")
        print("   [WARN] API keys not configured (read-only mode)")
except Exception as e:
    errors.append(f"IndodaxAPI failed: {e}")
    print(f"   [FAIL] IndodaxAPI FAILED: {e}")

print()

# =============================================================================
# 3. ANALYSIS MODULES
# =============================================================================
print("3. Testing ANALYSIS modules...")
try:
    from analysis.technical_analysis import TechnicalAnalysis
    print("   [OK] TechnicalAnalysis imported")
except Exception as e:
    errors.append(f"TechnicalAnalysis failed: {e}")
    print(f"   [FAIL] TechnicalAnalysis FAILED: {e}")

# Skip ML model init (too slow) - just test import
try:
    from analysis.ml_model import MLTradingModel
    print("   [OK] MLTradingModel (V1) imported (init skipped - takes too long)")
except Exception as e:
    errors.append(f"MLTradingModel V1 import failed: {e}")
    print(f"   [FAIL] MLTradingModel V1 import FAILED: {e}")

try:
    from analysis.ml_model_v2 import MLTradingModelV2
    print("   [OK] MLTradingModelV2 imported (init skipped - takes too long)")
except Exception as e:
    errors.append(f"MLTradingModelV2 import failed: {e}")
    print(f"   [FAIL] MLTradingModelV2 import FAILED: {e}")

try:
    from analysis.signal_analyzer import SignalAnalyzer
    print("   [OK] SignalAnalyzer imported")
except Exception as e:
    errors.append(f"SignalAnalyzer failed: {e}")
    print(f"   [FAIL] SignalAnalyzer FAILED: {e}")

try:
    from analysis.support_resistance import SupportResistanceDetector
    print("   [OK] SupportResistanceDetector imported")
except Exception as e:
    errors.append(f"SupportResistanceDetector failed: {e}")
    print(f"   [FAIL] SupportResistanceDetector FAILED: {e}")

print()

# =============================================================================
# 4. TRADING MODULES
# =============================================================================
print("4. Testing TRADING modules...")
try:
    from trading.trading_engine import TradingEngine
    print("   [OK] TradingEngine imported")
except Exception as e:
    errors.append(f"TradingEngine failed: {e}")
    print(f"   [FAIL] TradingEngine FAILED: {e}")

try:
    from trading.risk_manager import RiskManager
    print("   [OK] RiskManager imported")
except Exception as e:
    errors.append(f"RiskManager failed: {e}")
    print(f"   [FAIL] RiskManager FAILED: {e}")

try:
    from trading.portfolio import Portfolio
    print("   [OK] Portfolio imported")
except Exception as e:
    errors.append(f"Portfolio failed: {e}")
    print(f"   [FAIL] Portfolio FAILED: {e}")

try:
    from trading.price_monitor import PriceMonitor
    print("   [OK] PriceMonitor imported")
except Exception as e:
    errors.append(f"PriceMonitor failed: {e}")
    print(f"   [FAIL] PriceMonitor FAILED: {e}")

# Skip heavy module init - just test import
try:
    from trading.scalper_module import ScalperModule
    print("   [OK] ScalperModule imported (init skipped - heavy)")
except Exception as e:
    errors.append(f"ScalperModule import failed: {e}")
    print(f"   [FAIL] ScalperModule import FAILED: {e}")

try:
    from trading.smart_hunter_integration import SmartHunterBotIntegration
    print("   [OK] SmartHunterBotIntegration imported")
except Exception as e:
    errors.append(f"SmartHunterBotIntegration failed: {e}")
    print(f"   [FAIL] SmartHunterBotIntegration FAILED: {e}")

print()

# =============================================================================
# 5. SIGNAL MODULES
# =============================================================================
print("5. Testing SIGNAL modules...")
try:
    from signals.signal_quality_engine import SignalQualityEngine
    print("   [OK] SignalQualityEngine imported")
except Exception as e:
    errors.append(f"SignalQualityEngine failed: {e}")
    print(f"   [FAIL] SignalQualityEngine FAILED: {e}")

try:
    from signals.signal_queue import signal_queue, scheduler
    print("   [OK] Signal queue & scheduler imported")
except Exception as e:
    errors.append(f"Signal queue failed: {e}")
    print(f"   [FAIL] Signal queue FAILED: {e}")

try:
    from signals.signal_db import SignalDatabase
    print("   [OK] SignalDatabase imported")
except Exception as e:
    errors.append(f"SignalDatabase failed: {e}")
    print(f"   [FAIL] SignalDatabase FAILED: {e}")

try:
    from signals.signal_filter_v2 import SignalFilterV2
    print("   [OK] SignalFilterV2 imported")
except Exception as e:
    errors.append(f"SignalFilterV2 failed: {e}")
    print(f"   [FAIL] SignalFilterV2 FAILED: {e}")

print()

# =============================================================================
# 6. CACHE MODULES
# =============================================================================
print("6. Testing CACHE modules...")
try:
    from cache.redis_price_cache import price_cache as redis_price_cache
    print("   [OK] Redis price cache imported")
    
    # Test Redis connection
    try:
        redis_ok = redis_price_cache.is_redis_available()
        if redis_ok:
            print("   [OK] Redis connection OK")
        else:
            warnings.append("Redis not available (using fallback dict)")
            print("   [WARN] Redis not available (using fallback dict)")
    except Exception as e:
        warnings.append(f"Redis check failed: {e}")
        print(f"   [WARN] Redis check failed: {e}")
except Exception as e:
    errors.append(f"Redis price cache failed: {e}")
    print(f"   [FAIL] Redis price cache FAILED: {e}")

try:
    from cache.redis_state_manager import state_manager
    print("   [OK] Redis state manager imported")
except Exception as e:
    errors.append(f"Redis state manager failed: {e}")
    print(f"   [FAIL] Redis state manager FAILED: {e}")

try:
    from cache.price_cache import PriceCache
    print("   [OK] PriceCache (local) imported")
except Exception as e:
    errors.append(f"PriceCache failed: {e}")
    print(f"   [FAIL] PriceCache FAILED: {e}")

print()

# =============================================================================
# 7. WORKER MODULES
# =============================================================================
print("7. Testing WORKER modules...")
try:
    from workers.async_worker import BackgroundWorker
    print("   [OK] BackgroundWorker imported")
except Exception as e:
    errors.append(f"BackgroundWorker failed: {e}")
    print(f"   [FAIL] BackgroundWorker FAILED: {e}")

try:
    from workers.price_poller import PricePoller
    print("   [OK] PricePoller imported")
except Exception as e:
    errors.append(f"PricePoller failed: {e}")
    print(f"   [FAIL] PricePoller FAILED: {e}")

print()

# =============================================================================
# 8. EXTERNAL DEPENDENCIES
# =============================================================================
print("8. Testing EXTERNAL dependencies...")
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
        print(f"   [OK] {display_name} ({module_name})")
    except ImportError as e:
        errors.append(f"Missing dependency: {module_name}")
        print(f"   [FAIL] {display_name} ({module_name}) - NOT INSTALLED")

print()

# =============================================================================
# SUMMARY
# =============================================================================
print("=" * 80)
print("HEALTH CHECK SUMMARY")
print("=" * 80)

if errors:
    print(f"\n[FAIL] ERRORS ({len(errors)}):")
    for error in errors:
        print(f"   - {error}")
else:
    print("\n[OK] No critical errors found!")

if warnings:
    print(f"\n[WARN] WARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(f"   - {warning}")
else:
    print("\n[OK] No warnings!")

print(f"\n{'=' * 80}")
if errors:
    print(f"RESULT: {len(errors)} errors, {len(warnings)} warnings")
    print("Bot may have issues starting. Please fix errors above.")
else:
    print(f"RESULT: All modules healthy! ({len(warnings)} warnings)")
    print("Bot should start successfully.")
print(f"{'=' * 80}")

# Exit with error code if there are errors
sys.exit(1 if errors else 0)
