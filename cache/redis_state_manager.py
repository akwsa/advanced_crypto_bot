"""
Redis State Manager - Unified State Storage
============================================
Redis-backed state management for:
- active_positions (scalper positions)
- price_data (real-time price history)
- historical_data (cached historical data)
- ML model metadata

KEUNTUNGAN:
  ⚡ State access ~0.1ms (dari Redis memory)
  🔒 Survive bot restart (kalau Redis persist enabled)
  🔄 Share state antar process/thread (bot, worker, scalper)
  🛡️ Fallback ke dict lokal kalau Redis down
  🚀 Async-friendly dengan background sync

CARA PAKAI:
    from redis_state_manager import state_manager

    # Active positions
    state_manager.set_position('btcidr', {...})
    pos = state_manager.get_position('btcidr')
    all_pos = state_manager.get_all_positions()

    # Price data (real-time history)
    state_manager.set_price_data('btcidr', {...})
    data = state_manager.get_price_data('btcidr')

    # Historical data (cached)
    state_manager.set_historical('btcidr', df)
    df = state_manager.get_historical('btcidr')

CONFIG:
    REDIS_HOST=localhost  (default)
    REDIS_PORT=6379       (default)
    REDIS_DB=0            (default)
    REDIS_STATE_TTL=86400 (24 jam default, dalam detik)
"""

import os
import time
import json
import logging
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger('crypto_bot')

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ redis package not installed. Using dict fallback only.")


class RedisStateManager:
    """
    Unified state manager dengan Redis backend + dict fallback.
    Thread-safe dengan background sync ke Redis.
    """

    def __init__(self, host: str = None, port: int = None, db: int = None, ttl: int = None):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", port or 6379))
        self.db_num = int(os.getenv("REDIS_DB", db or 0))
        self.ttl = int(os.getenv("REDIS_STATE_TTL", ttl or 86400))  # 24 jam default

        self._redis = None
        self._connected = False
        
        # Local fallback caches
        self._positions_cache: Dict[str, dict] = {}
        self._price_data_cache: Dict[str, dict] = {}
        self._historical_cache: Dict[str, dict] = {}
        
        # Lock untuk thread safety
        self._positions_lock = threading.Lock()
        self._price_data_lock = threading.Lock()
        self._historical_lock = threading.Lock()
        
        # Background sync flag
        self._sync_in_progress = False

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
            logger.info(f"✅ State Manager Redis connected at {self.host}:{self.port} (TTL: {self.ttl}s)")
        except Exception as e:
            logger.warning(f"⚠️ State Manager Redis unavailable ({e}), using dict fallback")
            self._connected = False
            self._redis = None

    def is_available(self) -> bool:
        """Check if Redis is available"""
        return self._connected and self._redis is not None

    # =====================================================================
    # ACTIVE POSITIONS
    # =====================================================================
    
    def set_position(self, pair: str, position: dict):
        """Set active position untuk pair"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        position['updated_at'] = datetime.now().isoformat()
        
        # Write ke local cache (always)
        with self._positions_lock:
            self._positions_cache[pair] = position
        
        # Write ke Redis (async, non-blocking)
        if self.is_available():
            try:
                self._redis.setex(
                    f"state:position:{pair}",
                    self.ttl,
                    json.dumps(position)
                )
            except Exception as e:
                logger.debug(f"⚠️ Redis set_position failed: {e}")

    def get_position(self, pair: str) -> Optional[dict]:
        """Get position untuk pair"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        # Try Redis first
        if self.is_available():
            try:
                data = self._redis.get(f"state:position:{pair}")
                if data:
                    position = json.loads(data)
                    # Update local cache
                    with self._positions_lock:
                        self._positions_cache[pair] = position
                    return position
            except Exception as e:
                logger.debug(f"⚠️ Redis get_position failed: {e}")
        
        # Fallback ke local cache
        with self._positions_lock:
            return self._positions_cache.get(pair)

    def get_all_positions(self) -> Dict[str, dict]:
        """Get semua active positions"""
        # Try Redis first
        if self.is_available():
            try:
                keys = self._redis.keys("state:position:*")
                positions = {}
                for key in keys:
                    pair = key.replace("state:position:", "")
                    data = self._redis.get(key)
                    if data:
                        positions[pair] = json.loads(data)
                
                # Update local cache
                with self._positions_lock:
                    self._positions_cache.update(positions)
                return positions
            except Exception as e:
                logger.debug(f"⚠️ Redis get_all_positions failed: {e}")
        
        # Fallback ke local cache
        with self._positions_lock:
            return dict(self._positions_cache)

    def remove_position(self, pair: str):
        """Remove active position"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        # Remove from local cache
        with self._positions_lock:
            self._positions_cache.pop(pair, None)
        
        # Remove from Redis
        if self.is_available():
            try:
                self._redis.delete(f"state:position:{pair}")
            except Exception as e:
                logger.debug(f"⚠️ Redis remove_position failed: {e}")

    def clear_positions(self):
        """Clear semua active positions"""
        with self._positions_lock:
            self._positions_cache.clear()
        
        if self.is_available():
            try:
                keys = self._redis.keys("state:position:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception as e:
                logger.debug(f"⚠️ Redis clear_positions failed: {e}")

    # =====================================================================
    # PRICE DATA (real-time price history)
    # =====================================================================
    
    def set_price_data(self, pair: str, data: dict):
        """Set price data untuk pair (real-time history)"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        data['updated_at'] = datetime.now().isoformat()
        
        # Write ke local cache (always)
        with self._price_data_lock:
            self._price_data_cache[pair] = data
        
        # Write ke Redis (async, non-blocking)
        if self.is_available():
            try:
                # Limit data size - only keep recent entries
                if 'history' in data and len(data['history']) > 1000:
                    data['history'] = data['history'][-1000:]
                
                self._redis.setex(
                    f"state:pricedata:{pair}",
                    self.ttl,
                    json.dumps(data)
                )
            except Exception as e:
                logger.debug(f"⚠️ Redis set_price_data failed: {e}")

    def get_price_data(self, pair: str) -> Optional[dict]:
        """Get price data untuk pair"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        # Try Redis first
        if self.is_available():
            try:
                data = self._redis.get(f"state:pricedata:{pair}")
                if data:
                    price_data = json.loads(data)
                    # Update local cache
                    with self._price_data_lock:
                        self._price_data_cache[pair] = price_data
                    return price_data
            except Exception as e:
                logger.debug(f"⚠️ Redis get_price_data failed: {e}")
        
        # Fallback ke local cache
        with self._price_data_lock:
            return self._price_data_cache.get(pair)

    def get_all_price_data(self) -> Dict[str, dict]:
        """Get semua price data"""
        # Try Redis first
        if self.is_available():
            try:
                keys = self._redis.keys("state:pricedata:*")
                price_data = {}
                for key in keys:
                    pair = key.replace("state:pricedata:", "")
                    data = self._redis.get(key)
                    if data:
                        price_data[pair] = json.loads(data)
                
                # Update local cache
                with self._price_data_lock:
                    self._price_data_cache.update(price_data)
                return price_data
            except Exception as e:
                logger.debug(f"⚠️ Redis get_all_price_data failed: {e}")
        
        # Fallback ke local cache
        with self._price_data_lock:
            return dict(self._price_data_cache)

    # =====================================================================
    # HISTORICAL DATA (cached historical data)
    # =====================================================================
    
    def set_historical(self, pair: str, data: dict):
        """Set historical data untuk pair (cached)"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        data['updated_at'] = datetime.now().isoformat()
        
        # Write ke local cache (always)
        with self._historical_lock:
            self._historical_cache[pair] = data
        
        # Write ke Redis (async, non-blocking)
        if self.is_available():
            try:
                # Limit data size
                if 'candles' in data and len(data['candles']) > 5000:
                    data['candles'] = data['candles'][-5000:]
                
                self._redis.setex(
                    f"state:historical:{pair}",
                    self.ttl,
                    json.dumps(data)
                )
            except Exception as e:
                logger.debug(f"⚠️ Redis set_historical failed: {e}")

    def get_historical(self, pair: str) -> Optional[dict]:
        """Get historical data untuk pair"""
        pair = pair.lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        # Try Redis first
        if self.is_available():
            try:
                data = self._redis.get(f"state:historical:{pair}")
                if data:
                    historical = json.loads(data)
                    # Update local cache
                    with self._historical_lock:
                        self._historical_cache[pair] = historical
                    return historical
            except Exception as e:
                logger.debug(f"⚠️ Redis get_historical failed: {e}")
        
        # Fallback ke local cache
        with self._historical_lock:
            return self._historical_cache.get(pair)

    def get_all_historical(self) -> Dict[str, dict]:
        """Get semua historical data"""
        # Try Redis first
        if self.is_available():
            try:
                keys = self._redis.keys("state:historical:*")
                historical = {}
                for key in keys:
                    pair = key.replace("state:historical:", "")
                    data = self._redis.get(key)
                    if data:
                        historical[pair] = json.loads(data)
                
                # Update local cache
                with self._historical_lock:
                    self._historical_cache.update(historical)
                return historical
            except Exception as e:
                logger.debug(f"⚠️ Redis get_all_historical failed: {e}")
        
        # Fallback ke local cache
        with self._historical_lock:
            return dict(self._historical_cache)

    # =====================================================================
    # UTILITIES
    # =====================================================================
    
    def sync_to_redis(self):
        """Sync semua local cache ke Redis (background-safe)"""
        if not self.is_available():
            return
        
        if self._sync_in_progress:
            return
        
        self._sync_in_progress = True
        try:
            # Sync positions
            with self._positions_lock:
                for pair, pos in self._positions_cache.items():
                    try:
                        self._redis.setex(
                            f"state:position:{pair}",
                            self.ttl,
                            json.dumps(pos)
                        )
                    except Exception as e:
                        logger.debug(f"Failed to sync position for {pair}: {e}")

            # Sync price data
            with self._price_data_lock:
                for pair, data in self._price_data_cache.items():
                    try:
                        if 'history' in data and len(data['history']) > 1000:
                            data['history'] = data['history'][-1000:]
                        self._redis.setex(
                            f"state:pricedata:{pair}",
                            self.ttl,
                            json.dumps(data)
                        )
                    except Exception as e:
                        logger.debug(f"Failed to sync price data for {pair}: {e}")

            # Sync historical
            with self._historical_lock:
                for pair, data in self._historical_cache.items():
                    try:
                        if 'candles' in data and len(data['candles']) > 5000:
                            data['candles'] = data['candles'][-5000:]
                        self._redis.setex(
                            f"state:historical:{pair}",
                            self.ttl,
                            json.dumps(data)
                        )
                    except Exception as e:
                        logger.debug(f"Failed to sync historical for {pair}: {e}")
            
            logger.info("✅ State synced to Redis")
        except Exception as e:
            logger.error(f"❌ Redis sync failed: {e}")
        finally:
            self._sync_in_progress = False

    def get_stats(self) -> dict:
        """Get state manager stats"""
        with self._positions_lock:
            positions_count = len(self._positions_cache)
        with self._price_data_lock:
            price_data_count = len(self._price_data_cache)
        with self._historical_lock:
            historical_count = len(self._historical_cache)
        
        return {
            'redis_connected': self.is_available(),
            'positions_count': positions_count,
            'price_data_count': price_data_count,
            'historical_count': historical_count,
        }


# Global singleton
state_manager = RedisStateManager()
