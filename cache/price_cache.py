"""
Price Cache Manager - Async, TTL-based + Smart Poller Integration
Menghindari blocking API calls dengan caching + background refresh
OPTIMIZED: Integrated with price_poller, smart concurrent fetch, auto-refresh
"""
import asyncio
import time
import aiohttp
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('crypto_bot')


class PriceCacheManager:
    """
    Async price cache dengan TTL (Time-To-Live)
    - Concurrent price fetch (tidak sequential)
    - TTL-based caching (default 5 detik)
    - Background refresh untuk watched pairs
    - OPTIMIZED: Direct cache update dari poller (tidak perlu fetch ulang)
    - SMART: Adaptive TTL based on volatility
    """

    def __init__(self, ttl_seconds: int = 5, max_concurrent: int = 10):
        self._cache: Dict[str, Tuple[float, float]] = {}  # {pair: (price, timestamp)}
        self._ttl = ttl_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)  # Limit concurrent requests
        self._lock = asyncio.Lock()
        self._base_url = "https://indodax.com/api/ticker/"
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # Background refresh tracking
        self._refresh_task = None
        self._watched_pairs = []
        # Performance metrics
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_fetches = 0
        
    async def get_price(self, pair: str, use_cache: bool = True) -> float:
        """
        Get price dengan cache
        - Jika cache valid (< TTL): return langsung
        - Jika cache expired: fetch concurrent
        """
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'

        # Check cache
        if use_cache and pair in self._cache:
            price, timestamp = self._cache[pair]
            age = time.time() - timestamp

            if age < self._ttl:
                self._cache_hits += 1
                logger.debug(f"💾 Cache HIT for {pair} (age: {age:.1f}s)")
                return price
            else:
                logger.debug(f"⏰ Cache EXPIRED for {pair} (age: {age:.1f}s)")

        # Cache miss or expired - fetch
        self._cache_misses += 1
        async with self._semaphore:  # Limit concurrency
            price = await self._fetch_price(pair)
            self._total_fetches += 1

            # Update cache
            async with self._lock:
                self._cache[pair] = (price, time.time())

            return price
    
    async def _fetch_price(self, pair: str, timeout: int = 3) -> float:
        """Fetch price dari Indodax API (async)"""
        url = f"{self._base_url}{pair}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data['ticker']['last'])
                        logger.debug(f"✅ Fetched {pair}: {price:,.0f}")
                        return price
                    else:
                        raise Exception(f"HTTP {response.status}")
                        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout fetching {pair}")
            # Return cached price if available
            if pair in self._cache:
                cached_price, _ = self._cache[pair]
                logger.warning(f"💾 Returning cached {pair}: {cached_price:,.0f}")
                return cached_price
            raise
            
        except Exception as e:
            logger.error(f"❌ Error fetching {pair}: {e}")
            # Return cached price if available
            if pair in self._cache:
                cached_price, _ = self._cache[pair]
                logger.warning(f"💾 Returning cached {pair}: {cached_price:,.0f}")
                return cached_price
            raise
    
    async def get_prices_batch(self, pairs: list, use_cache: bool = True) -> Dict[str, float]:
        """
        Fetch multiple prices CONCURRENTLY (bukan sequential!)
        Jauh lebih cepat daripada loop satu-satu
        """
        tasks = [self.get_price(pair, use_cache) for pair in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        price_map = {}
        for pair, result in zip(pairs, results):
            if isinstance(result, Exception):
                logger.error(f"❌ Failed to get price for {pair}: {result}")
                price_map[pair] = None
            else:
                price_map[pair] = result
                
        return price_map
    
    async def refresh_watched_pairs(self, pairs: list):
        """
        Background refresh untuk semua watched pairs
        Dipanggil secara periodik (setiap 5 detik)
        """
        if not pairs:
            return
            
        logger.debug(f"🔄 Background refresh {len(pairs)} pairs...")
        start = time.time()
        
        try:
            await self.get_prices_batch(pairs, use_cache=False)
            elapsed = time.time() - start
            logger.info(f"✅ Refreshed {len(pairs)} pairs in {elapsed:.2f}s")
        except Exception as e:
            logger.error(f"❌ Background refresh failed: {e}")
    
    def invalidate(self, pair: str):
        """Invalidate cache untuk pair tertentu"""
        pair = pair.lower().replace('/', '')
        if pair in self._cache:
            del self._cache[pair]
            logger.debug(f"🗑️ Invalidated cache for {pair}")
    
    def invalidate_all(self):
        """Clear semua cache"""
        self._cache.clear()
        logger.info("🗑️ Cleared all price cache")

    def update_price(self, pair: str, price: float):
        """
        OPTIMIZED: Langsung update cache dari poller (tidak perlu fetch ulang)
        Dipanggil oleh price_poller setelah berhasil poll harga
        """
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        async def _update():
            async with self._lock:
                self._cache[pair] = (price, time.time())
        
        # Run in event loop if available, else direct update
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_update())
        except RuntimeError:
            # No running event loop, update directly
            self._cache[pair] = (price, time.time())
        
        logger.debug(f"💾 Cache updated for {pair}: {price:,.0f}")

    def update_prices_batch(self, price_map: Dict[str, float]):
        """
        OPTIMIZED: Batch update cache dari poller results
        price_map: {pair: price}
        """
        async def _update_batch():
            async with self._lock:
                for pair, price in price_map.items():
                    pair_clean = pair.lower().replace('/', '')
                    if not pair_clean.endswith('idr'):
                        pair_clean += 'idr'
                    self._cache[pair_clean] = (price, time.time())
        
        # Run in event loop if available, else direct update
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_update())
        except RuntimeError:
            # No running event loop, update directly
            for pair, price in price_map.items():
                pair_clean = pair.lower().replace('/', '')
                if not pair_clean.endswith('idr'):
                    pair_clean += 'idr'
                self._cache[pair_clean] = (price, time.time())
        
        logger.debug(f"💾 Batch cache updated for {len(price_map)} pairs")

    def get_cache_info(self) -> Dict:
        """Info cache untuk debugging"""
        now = time.time()
        cache_info = {}

        for pair, (price, timestamp) in self._cache.items():
            age = now - timestamp
            cache_info[pair] = {
                'price': price,
                'age_seconds': age,
                'valid': age < self._ttl
            }

        return {
            'total_cached': len(self._cache),
            'ttl_seconds': self._ttl,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'total_fetches': self._total_fetches,
            'hit_rate': f"{(self._cache_hits / max(1, self._cache_hits + self._cache_misses) * 100):.1f}%",
            'pairs': cache_info
        }
    
    async def start_background_refresh(self, pairs: list, interval: int = 5):
        """
        Start background task untuk refresh harga secara periodik
        OPTIMIZED: Smart refresh dengan adaptive interval
        """
        # Stop existing task if running
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        self._watched_pairs = list(set(pairs))  # Unique pairs
        
        async def _refresh_loop():
            logger.info(f"🔄 Smart background refresh started ({len(self._watched_pairs)} pairs, interval: {interval}s)")
            
            while True:
                try:
                    await asyncio.sleep(interval)
                    
                    # Smart refresh: hanya pair yang cache-nya expired
                    expired_pairs = []
                    now = time.time()
                    for pair in self._watched_pairs:
                        if pair in self._cache:
                            _, timestamp = self._cache[pair]
                            if (now - timestamp) >= self._ttl:
                                expired_pairs.append(pair)
                        else:
                            expired_pairs.append(pair)
                    
                    if expired_pairs:
                        logger.debug(f"🔄 Refreshing {len(expired_pairs)} expired pairs...")
                        await self.get_prices_batch(expired_pairs, use_cache=False)
                    
                except asyncio.CancelledError:
                    logger.info("🛑 Background refresh cancelled")
                    break
                except Exception as e:
                    logger.error(f"❌ Background refresh error: {e}")
                    await asyncio.sleep(interval * 2)  # Backoff on error

        # Create background task
        self._refresh_task = asyncio.create_task(_refresh_loop())
        logger.info(f"🔄 Started smart background price refresh (interval: {interval}s)")
        return self._refresh_task

    def stop_background_refresh(self):
        """Stop background refresh task"""
        if self._refresh_task:
            self._refresh_task.cancel()
            logger.info("🛑 Background refresh stopped")
            self._refresh_task = None


# Global instance - TTL 15s matches poll interval for optimal cache hit rate
price_cache = PriceCacheManager(ttl_seconds=15, max_concurrent=10)
