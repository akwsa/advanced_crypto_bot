#!/usr/bin/env python3
"""
Debug script: Check why no BUY/SELL signals appear in Telegram
"""

import sys
sys.path.insert(0, '.')

print("=" * 80)
print("DEBUG: Why no BUY/SELL signals in Telegram?")
print("=" * 80)
print()

# 1. Check Config
print("1. Checking Config.WATCH_PAIRS...")
from core.config import Config
print(f"   WATCH_PAIRS: {Config.WATCH_PAIRS}")
print(f"   Count: {len(Config.WATCH_PAIRS)} pairs")
print()

# 2. Check Database
print("2. Checking Database watchlist...")
from core.database import Database
db = Database()

# Get all watchlists
all_watchlists = db.get_all_watchlists()
print(f"   Users with watchlist: {list(all_watchlists.keys())}")
for user_id, pairs in all_watchlists.items():
    print(f"   User {user_id}: {pairs}")

if not all_watchlists:
    print("   ⚠️ NO WATCHLIST IN DATABASE!")
    print("   → _monitor_strong_signal will NOT send signals!")
    print("   → Solution: Use /watch btcidr first")
print()

# 3. Check if price poller has data
print("3. Checking historical data in DB...")
for pair in Config.WATCH_PAIRS:
    df = db.get_price_history(pair, limit=5)
    if not df.empty:
        print(f"   {pair}: {len(df)} candles in DB (latest: {df.index[-1]})")
    else:
        print(f"   {pair}: NO DATA in DB")
print()

# 4. Check signal generation conditions
print("4. Signal Generation Requirements:")
print("   ✓ Pair must be in user's watchlist (subscribers)")
print("   ✓ Need 60+ candles of historical data")
print("   ✓ Signal must be BUY/SELL/STRONG_BUY/STRONG_SELL (not HOLD)")
print("   ✓ Rate limit: max 1 signal per 5 minutes per pair")
print()

# 5. Check market scan conditions
print("5. Market Scan Requirements (every 5 min):")
print("   ✓ Uses Config.WATCH_PAIRS (not user watchlist)")
print("   ✓ Need 50+ candles")
print("   ✓ RSI < 40 + MACD bullish → BUY")
print("   ✓ RSI > 65 + MACD bearish → SELL")
print("   ⚠️ ONLY TA-based, NO ML!")
print()

# 6. Check if bot is running
print("6. Bot Configuration:")
print(f"   AUTO_TRADING_ENABLED: {Config.AUTO_TRADING_ENABLED}")
print(f"   AUTO_TRADE_DRY_RUN: {Config.AUTO_TRADE_DRY_RUN}")
print(f"   ML_MODEL_PATH: {Config.ML_MODEL_PATH}")
print(f"   CONFIDENCE_THRESHOLD: {Config.CONFIDENCE_THRESHOLD}")
print()

# 7. Check ML model file
import os
model_path = Config.ML_MODEL_PATH
if os.path.exists(model_path):
    model_size = os.path.getsize(model_path)
    print(f"7. ML Model file: {model_path} ({model_size / 1024:.1f} KB)")
else:
    print(f"7. ML Model file: {model_path} - NOT FOUND!")
    print("   → ML predictions will fail!")
print()

# 8. Check Redis
print("8. Checking Redis connection...")
try:
    from cache.redis_price_cache import price_cache as redis_cache
    redis_ok = redis_cache.is_redis_available()
    if redis_ok:
        print("   ✓ Redis connection OK")
        info = redis_cache.get_info()
        print(f"   Cache size: {info.get('local_cache_size', 0)} pairs")
    else:
        print("   ⚠️ Redis NOT available (using dict fallback)")
        print("   → This is OK, but slower")
except Exception as e:
    print(f"   ✗ Redis check failed: {e}")
print()

# 9. Summary
print("=" * 80)
print("DIAGNOSIS SUMMARY")
print("=" * 80)

if not all_watchlists:
    print("\n⚠️ PRIMARY ISSUE: No watchlist in database!")
    print("\nThe bot's _monitor_strong_signal function ONLY sends signals")
    print("for pairs that users have added via /watch command.")
    print("\nSolution:")
    print("1. Start the bot: python bot.py")
    print("2. Use /watch btcidr (or other pairs)")
    print("3. Wait for price poller to collect 60+ candles (~5-10 min)")
    print("4. Signals will appear automatically!")
elif len(all_watchlists) > 0:
    total_pairs = sum(len(pairs) for pairs in all_watchlists.values())
    print(f"\n✓ Watchlist exists: {total_pairs} pairs across {len(all_watchlists)} users")
    print("\nIf still no signals, check:")
    print("1. Is price poller running? (check logs for 'Polling X pairs')")
    print("2. Are candles being saved? (need 60+ per pair)")
    print("3. Is ML model loaded? (check for models/trading_model.pkl)")
    print("4. Are signals being generated but not sent? (check _monitor_strong_signal logs)")

print()
print("=" * 80)
