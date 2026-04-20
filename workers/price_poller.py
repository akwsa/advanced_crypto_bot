#!/usr/bin/env python3
"""
REST API Price Poller - OPTIMIZED
Polls Indodax REST API periodically with smart caching
OPTIMIZED: Integrated with price_cache for instant access
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from core.config import Config
from api.indodax_api import IndodaxAPI
from core.utils import Utils, RateLimitedLogger
from cache.price_cache import price_cache  # Original cache (dict-based)
from cache.redis_price_cache import price_cache as redis_price_cache  # NEW: Redis-backed cache

# Use rate-limited logger to reduce log spam during polling
logger = RateLimitedLogger(logging.getLogger(__name__), default_interval=60)


class PricePoller:
    """Polls prices from Indodax REST API at regular intervals"""

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.indodax = IndodaxAPI()
        self.polling_task = None
        self.is_running = False
        # Optimal poll interval - fast enough for responsive cache, safe for Indodax
        # With 9 pairs sequential + 0.6s delay = ~10s per cycle
        # So 15s interval = ~5s between cycles (safe & responsive)
        self.poll_interval = 15  # seconds - balanced between speed and safety

        # Global rate limit cooldown
        self.rate_limit_cooldown_until = None  # datetime when cooldown expires
        self.rate_limit_count = 0  # Track 429 errors

        # Blacklist for invalid/non-existent pairs (prevents endless retries)
        self.invalid_pairs = set()  # Pairs confirmed to not exist on Indodax
        self.max_invalid_attempts = 10  # Increased from 2 - only blacklist after consistent failures
        self.pair_fail_count = {}  # Track failure count per pair
        
    async def start_polling(self):
        """Start price polling loop"""
        if self.is_running:
            logger.warning("⚠️ Price poller already running")
            return
            
        self.is_running = True
        logger.info(f"🔄 Starting price poller (interval: {self.poll_interval}s)")

        # Run polling loop
        self.polling_task = asyncio.create_task(self._poll_loop())
        logger.info("✅ Polling task created")
    
    async def stop_polling(self):
        """Stop price polling loop"""
        self.is_running = False
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Price poller stopped")
    
    async def _poll_loop(self):
        """Main polling loop"""
        # Log startup once, not repeatedly
        logging.getLogger(__name__).info(f"🔄 Poll loop started, will poll every {self.poll_interval}s")

        while self.is_running:
            try:
                # Check if in rate limit cooldown
                if self.rate_limit_cooldown_until and datetime.now() < self.rate_limit_cooldown_until:
                    cooldown_remaining = (self.rate_limit_cooldown_until - datetime.now()).total_seconds()
                    # Use regular logger for warnings (important events)
                    logging.getLogger(__name__).warning(
                        f"⏸️ Rate limit cooldown active for {cooldown_remaining:.0f}s"
                    )
                    await asyncio.sleep(5)  # Check every 5s if cooldown expired
                    continue

                # Reduced logging - use rate-limited logger
                logger.debug("🔄 Starting polling cycle...", key="poll_start", interval=300)
                await self._poll_all_pairs()
                logger.debug("✅ Polling cycle complete", key="poll_complete", interval=300)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logging.getLogger(__name__).info("🛑 Poll loop cancelled")
                break
            except Exception as e:
                # Use rate-limited error logging
                logger.error(f"❌ Polling error: {str(e)[:100]}", key="poll_error", interval=30)
                import traceback
                logging.getLogger(__name__).debug(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(self.poll_interval)
    
    async def _poll_all_pairs(self):
        """Poll prices for all watched pairs (sequential, original working code)"""
        # Get all watched pairs from bot subscribers + config
        all_pairs = set()

        # Pairs from user subscriptions
        for pairs in self.bot.subscribers.values():
            all_pairs.update(pairs)

        # Also poll default pairs from config (always poll these)
        for pair in Config.WATCH_PAIRS:
            all_pairs.add(pair.upper().strip())

        # Remove invalid/blacklisted pairs
        valid_pairs = all_pairs - self.invalid_pairs

        # Log if any pairs were filtered out (rate limited)
        filtered_pairs = all_pairs - valid_pairs
        if filtered_pairs:
            logger.warning(
                f"⏭️ Skipping {len(filtered_pairs)} invalid pair(s)",
                key="filtered_pairs",
                interval=300
            )

        if not valid_pairs:
            return

        # Reduced logging - use rate-limited logger
        logger.debug(
            f"🔄 Polling {len(valid_pairs)} pair(s)",
            key="poll_pairs_count",
            interval=60
        )

        # Poll pairs sequentially with delay to avoid rate limiting
        for i, pair in enumerate(valid_pairs):
            try:
                await self._poll_single_pair(pair)
                # Add delay between requests to respect rate limits
                # Indodax limit ~100 req/min = ~600ms per request
                if i < len(valid_pairs) - 1:  # Don't sleep after last request
                    await asyncio.sleep(0.6)
            except Exception as e:
                # Rate limited error logging per pair
                logger.error(
                    f"❌ Error polling {pair}: {str(e)[:80]}",
                    key=f"poll_error_{pair}",
                    interval=120
                )

    async def _poll_single_pair_async(self, pair):
        """
        OPTIMIZED: Async version untuk concurrent batch processing
        Wrapper untuk _poll_single_pair yang synchronous
        """
        try:
            # Fetch ticker dari REST API (async)
            ticker = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.indodax.get_ticker(pair)
            )

            if not ticker:
                # Rate limited warning logging
                logger.warning(
                    f"⚠️ No ticker data for {pair}",
                    key=f"no_ticker_{pair}",
                    interval=300
                )
                self._track_pair_failure(pair)
                return

            # Success - reset failure tracking
            self.pair_fail_count.pop(pair, None)

            last_price = ticker['last']
            volume = ticker.get('volume', 0)

            # Calculate change_percent manually (Indodax doesn't always provide it)
            old_price = self.bot.price_data.get(pair, {}).get('last', last_price)
            if old_price > 0:
                change_pct = ((last_price - old_price) / old_price) * 100
            else:
                change_pct = 0.0

            # Update price cache (bot's internal cache)
            self.bot.price_data[pair] = {
                'last': last_price,
                'volume': volume,
                'change_percent': change_pct,
                'timestamp': datetime.now()
            }

            # OPTIMIZED: Update price_cache_manager untuk instant access
            price_cache.update_price(pair, last_price)

            # Also write to Redis cache (Phase 1: Price Cache)
            try:
                redis_price_cache.set_price(pair, last_price)
            except Exception as e:
                logger.debug(
                    f"Redis cache write failed for {pair}: {e}",
                    key=f"redis_fail_{pair}",
                    interval=300
                )

            # Rate limited info logging - log only significant changes
            if abs(change_pct) > 1.0:
                logging.getLogger(__name__).info(f"📊 {pair}: {last_price:,.0f} ({change_pct:+.2f}%)")
            else:
                logger.debug(
                    f"📊 Polled {pair}: {last_price:,.0f}",
                    key=f"poll_{pair}",
                    interval=120
                )

            # Reset rate limit counter on successful poll
            self.rate_limit_count = 0

            # Update historical data untuk ML
            self.bot._update_historical_data(pair, self.bot.price_data[pair])

            # Save to database
            self.bot.db.save_price(pair, {
                'timestamp': datetime.now(),
                'open': last_price,
                'high': last_price,
                'low': last_price,
                'close': last_price,
                'volume': volume
            })

            # Log candle data
            candle_count = len(self.bot.historical_data.get(pair, []))
            logger.info(f"🕯️ Candle saved for {pair}: {last_price:,.0f} | Total candles: {candle_count}")

            # Check SL/TP levels
            asyncio.create_task(self.bot.price_monitor.check_price_levels(pair, last_price))

            # Check for strong signals every 5 minutes (after 60+ candles)
            if candle_count >= 60:
                try:
                    await self.bot._monitor_strong_signal(pair)
                except Exception as e:
                    logger.error(f"❌ Error monitoring signal for {pair}: {e}")

                # Auto-trigger trade if enabled
                if self.bot.is_trading:
                    asyncio.create_task(self.bot._check_trading_opportunity(pair))

        except Exception as e:
            error_str = str(e)
            is_timeout = any(kw in error_str.lower() for kw in ['timeout', 'timed out', 'readerror', 'connecttimeout', 'connection', 'read error'])
            is_rate_limit = '429' in error_str or 'rate_limit' in error_str.lower()

            if is_rate_limit:
                self.rate_limit_count += 1
                if self.rate_limit_count >= 2:
                    cooldown_duration = 60
                    self.rate_limit_cooldown_until = datetime.now() + timedelta(seconds=cooldown_duration)
                    logger.error(f"🛑 GLOBAL RATE LIMIT COOLDOWN: Pausing all polls for {cooldown_duration}s")
                else:
                    logger.info("💡 Tip: Increase poll_interval or reduce watched pairs to avoid rate limits")
            else:
                logger.error(f"❌ Price fetch failed for {pair}: {error_str}")
                self._track_pair_failure(pair)

    async def _poll_single_pair(self, pair, retry_count=0, max_retries=3):
        """Poll price for a single pair with exponential backoff"""
        try:
            # Fetch ticker from REST API
            ticker = self.indodax.get_ticker(pair)

            if not ticker:
                # Only track failure if not during cooldown (avoid false blacklisting during rate limits)
                if self.rate_limit_cooldown_until and datetime.now() < self.rate_limit_cooldown_until:
                    logger.debug(f"⏭️ Skipping pair {pair} during rate limit cooldown")
                    return
                logger.warning(f"⚠️ No ticker data for {pair}")
                # Track failure for invalid pair detection
                self._track_pair_failure(pair)
                return

            # Success - reset failure tracking for this pair
            self.pair_fail_count.pop(pair, None)

            last_price = ticker['last']
            volume = ticker.get('volume', 0)
            change_pct = ticker.get('change_percent', 0)

            # Update price cache (bot's internal cache)
            self.bot.price_data[pair] = {
                'last': last_price,
                'volume': volume,
                'change_percent': change_pct,
                'timestamp': datetime.now()
            }

            # OPTIMIZED: Update price_cache_manager untuk instant access
            price_cache.update_price(pair, last_price)

            # Also write to Redis cache (Phase 1: Price Cache)
            try:
                redis_price_cache.set_price(pair, last_price)
            except Exception as e:
                logger.debug(f"Redis cache write failed for {pair}: {e}")

            logger.info(f"📊 Polled {pair}: {last_price:,.0f} IDR ({change_pct:+.2f}%)")

            # Reset rate limit counter on successful poll
            self.rate_limit_count = 0

            # Update historical data for ML
            self.bot._update_historical_data(pair, self.bot.price_data[pair])

            # Save to database
            self.bot.db.save_price(pair, {
                'timestamp': datetime.now(),
                'open': last_price,
                'high': last_price,
                'low': last_price,
                'close': last_price,
                'volume': volume
            })

            # Log candle data for visibility
            candle_count = len(self.bot.historical_data.get(pair, []))
            logger.info(f"🕯️ Candle saved for {pair}: {last_price:,.0f} | Total candles: {candle_count}")

            # Check SL/TP levels for notifications
            # Note: asyncio already imported at module level
            asyncio.create_task(self.bot.price_monitor.check_price_levels(pair, last_price))

            # Check for strong signals every 5 minutes (after 60+ candles)
            if candle_count >= 60:
                try:
                    await self.bot._monitor_strong_signal(pair)
                except Exception as e:
                    logger.error(f"❌ Error monitoring signal for {pair}: {e}")

                # Auto-trigger trade if enabled
                if self.bot.is_trading:
                    asyncio.create_task(self.bot._check_trading_opportunity(pair))

        except Exception as e:
            error_str = str(e)
            is_timeout = any(kw in error_str.lower() for kw in ['timeout', 'timed out', 'readerror', 'connecttimeout', 'connecttimeout', 'connection', 'read error'])
            is_rate_limit = '429' in error_str or 'rate_limit' in error_str.lower()

            if (is_timeout or is_rate_limit) and retry_count < max_retries:
                # Exponential backoff: 2s, 4s, 8s
                backoff_time = 2 ** (retry_count + 1)
                error_type = "Rate limit" if is_rate_limit else "Timeout"
                logger.warning(f"⏱️ {error_type} for {pair} (attempt {retry_count + 1}/{max_retries}), retry in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
                return await self._poll_single_pair(pair, retry_count + 1, max_retries)

            # Max retries exceeded or non-retryable error
            if is_rate_limit:
                self.rate_limit_count += 1
                if self.rate_limit_count >= 2:
                    cooldown_duration = 60  # 60 second cooldown
                    self.rate_limit_cooldown_until = datetime.now() + timedelta(seconds=cooldown_duration)
                    logger.error(f"🛑 GLOBAL RATE LIMIT COOLDOWN: Pausing all polls for {cooldown_duration}s")
                    logger.info("💡 Indodax IP is temporarily blocked. Waiting for cooldown...")
                else:
                    logger.info("💡 Tip: Increase poll_interval or reduce watched pairs to avoid rate limits")
            else:
                logger.error(f"❌ Price fetch failed for {pair} after {retry_count + 1} attempts: {error_str}")
                self._track_pair_failure(pair)

    def _track_pair_failure(self, pair):
        """Track pair failures and blacklist if consistently failing.
        NOTE: This is only called for non-rate-limit, non-timeout errors.
        """
        # Don't track during rate limit cooldown (temporary issue)
        if self.rate_limit_cooldown_until and datetime.now() < self.rate_limit_cooldown_until:
            return

        self.pair_fail_count[pair] = self.pair_fail_count.get(pair, 0) + 1

        if self.pair_fail_count[pair] >= self.max_invalid_attempts:
            if pair not in self.invalid_pairs:
                self.invalid_pairs.add(pair)
                logger.warning(f"🚫 Pair {pair.upper()} added to skip list after {self.pair_fail_count[pair]} failures")
                logger.info(f"💡 Total skipped pairs: {len(self.invalid_pairs)} - {', '.join([p.upper() for p in self.invalid_pairs])}")

    def reset_invalid_pairs(self):
        """Reset the invalid pairs blacklist. Useful when a pair was incorrectly flagged."""
        count = len(self.invalid_pairs)
        self.invalid_pairs.clear()
        self.pair_fail_count.clear()
        logger.info(f"🔄 Reset invalid pairs blacklist ({count} pairs cleared)")
        return count
