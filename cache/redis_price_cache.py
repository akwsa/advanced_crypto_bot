"""
Redis Price Cache - Phase 1
============================
Redis-backed price cache dengan automatic fallback ke dict lokal.

KEUNTUNGAN:
  ⚡ Price access ~0.1ms (dari Redis memory)
  🔒 Survive bot restart (kalau Redis persist enabled)
  🔄 Share cache antar process (bot + worker)
  🛡️ Fallback ke dict lokal kalau Redis down

CARA PAKAI:
    from redis_price_cache import price_cache
    
    # Get price (auto Redis → fallback dict)
    price = price_cache.get_price_sync("BTCIDR")
    
    # Update price (write ke Redis + dict lokal)
    price_cache.set_price("BTCIDR", 1245000000)

CONFIG:
    REDIS_HOST=localhost  (default)
    REDIS_PORT=6379       (default)
    REDIS_DB=0            (default)
    REDIS_TTL=300         (5 menit default, dalam detik)

TIDAK MENGUBAH:
    - price_cache.py (tetap ada, tetap jalan)
    - bot.py (tidak perlu diubah untuk fallback)
    - price_poller.py (otomatis detect Redis)
"""

import os
import time
import logging
from typing import Optional, Dict

logger = logging.getLogger('crypto_bot')

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ redis package not installed. Using dict fallback only.")


class RedisPriceCache:
    """
    Price cache dengan Redis backend + dict fallback.
    API compatible dengan PriceCacheManager untuk easy migration.
    """

    def __init__(self, host: str = None, port: int = None, db: int = None, ttl: int = None):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", port or 6379))
        self.db_num = int(os.getenv("REDIS_DB", db or 0))
        self.ttl = int(os.getenv("REDIS_TTL", ttl or 300))  # 5 menit default

        self._redis = None
        self._local_cache: Dict[str, tuple] = {}  # {pair: (price, timestamp)}
        self._connected = False

        # Try connect to Redis
        self._connect_redis()

    def _connect_redis(self):
        """Try connect to Redis server"""
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis package not available, using dict fallback")
            return

        try:
            self._redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db_num,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True
            )
            # Test connection
            self._redis.ping()
            self._connected = True
            logger.info(f"✅ Redis connected at {self.host}:{self.port} (TTL: {self.ttl}s)")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable ({e}), using dict fallback")
            self._connected = False
            self._redis = None

    def set_price(self, pair: str, price: float):
        """
        Set price - write ke Redis + dict lokal.
        Kalau Redis down, tetap write ke dict lokal.
        """
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'

        timestamp = time.time()

        # Write ke Redis (kalau available)
        if self._connected and self._redis:
            try:
                key = f"price:{pair}"
                self._redis.setex(key, self.ttl, f"{price}:{timestamp}")
            except Exception as e:
                logger.debug(f"Redis set failed for {pair}: {e}")
                self._connected = False

        # Selalu write ke dict lokal (fallback)
        self._local_cache[pair] = (price, timestamp)

    def get_price_sync(self, pair: str) -> Optional[float]:
        """
        Get price - baca dari Redis → fallback dict lokal.
        Return None kalau tidak ada cache.
        """
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'

        # Try Redis first
        if self._connected and self._redis:
            try:
                key = f"price:{pair}"
                data = self._redis.get(key)
                if data:
                    price_str, ts_str = data.split(':')
                    price = float(price_str)
                    # Update local cache juga
                    self._local_cache[pair] = (price, float(ts_str))
                    return price
            except Exception as e:
                logger.debug(f"Redis get failed for {pair}: {e}")
                self._connected = False

        # Fallback ke dict lokal
        if pair in self._local_cache:
            price, timestamp = self._local_cache[pair]
            # Check TTL
            if (time.time() - timestamp) < self.ttl:
                return price
            else:
                # Expired
                del self._local_cache[pair]

        return None

    def get_price_with_fallback(self, pair: str, fetch_func=None) -> Optional[float]:
        """
        Get price - kalau tidak ada di cache, panggil fetch_func untuk fetch.
        fetch_func: callable yang return float(price) atau None.
        """
        price = self.get_price_sync(pair)
        if price is not None:
            return price

        # Cache miss - fetch kalau ada fetch_func
        if fetch_func:
            try:
                price = fetch_func()
                if price:
                    self.set_price(pair, price)
                    return price
            except Exception as e:
                logger.error(f"❌ Fetch failed for {pair}: {e}")

        return None

    def batch_set(self, price_map: Dict[str, float]):
        """
        Batch set prices - atomic write ke Redis + dict lokal.
        price_map: {pair: price}
        """
        if not price_map:
            return

        timestamp = time.time()

        # Write ke Redis (pipeline untuk speed)
        if self._connected and self._redis:
            try:
                pipe = self._redis.pipeline()
                for pair, price in price_map.items():
                    pair_clean = pair.lower().replace('/', '')
                    if not pair_clean.endswith('idr'):
                        pair_clean += 'idr'
                    key = f"price:{pair_clean}"
                    pipe.setex(key, self.ttl, f"{price}:{timestamp}")
                pipe.execute()
            except Exception as e:
                logger.debug(f"Redis pipeline failed: {e}")
                self._connected = False

        # Selalu write ke dict lokal
        for pair, price in price_map.items():
            pair_clean = pair.lower().replace('/', '')
            if not pair_clean.endswith('idr'):
                pair_clean += 'idr'
            self._local_cache[pair_clean] = (price, timestamp)

    def invalidate(self, pair: str):
        """Invalidate cache untuk pair tertentu"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'

        if self._connected and self._redis:
            try:
                key = f"price:{pair}"
                self._redis.delete(key)
            except Exception:
                pass

        if pair in self._local_cache:
            del self._local_cache[pair]

    def invalidate_all(self):
        """Clear semua cache"""
        if self._connected and self._redis:
            try:
                keys = self._redis.keys("price:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception:
                pass

        self._local_cache.clear()

    def get_info(self) -> Dict:
        """Info cache untuk debugging"""
        now = time.time()
        local_info = {}
        for pair, (price, timestamp) in self._local_cache.items():
            age = now - timestamp
            local_info[pair] = {
                'price': price,
                'age_seconds': round(age, 1),
                'valid': age < self.ttl
            }

        return {
            'redis_connected': self._connected,
            'redis_host': f"{self.host}:{self.port}",
            'ttl_seconds': self.ttl,
            'local_cache_size': len(self._local_cache),
            'local_pairs': local_info
        }

    def is_redis_available(self) -> bool:
        """Check apakah Redis available"""
        if not self._connected and self._redis:
            try:
                self._redis.ping()
                self._connected = True
            except Exception:
                self._connected = False
        return self._connected

    # Alias untuk compatibility dengan PriceCacheManager
    update_price = set_price
    update_prices_batch = batch_set


# Global instance
price_cache = RedisPriceCache()
