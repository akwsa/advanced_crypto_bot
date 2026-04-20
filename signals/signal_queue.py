"""
Signal Queue + Scheduler - Phase 4
===================================
Periodic signal scanning, auto-trade queue, and cleanup scheduler.

FITUR:
  📊 Signal Scanner: Scan semua pairs setiap 5 menit
  🤖 Auto-Trade Queue: Queue BUY/SELL signals untuk diproses worker
  🧹 Cleanup: Hapus data lama, compact database
  📈 Market Scanner: Detect opportunities di luar watchlist
  🔔 Smart Alerts: Notify hanya signal kuat (STRONG_BUY/STRONG_SELL)

CARA KERJA:
  1. Scheduler trigger setiap X menit
  2. Signal scanner scan semua pairs
  3. Signal kuat → masuk Redis queue
  4. Worker proses signal → execute trade atau notify
  5. Cleanup hapus data >30 hari
"""

import time
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger('crypto_bot')

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ redis package not installed. Signal Queue disabled.")


class SignalQueue:
    """
    Redis-backed signal queue for auto-trading.
    Strong signals are queued and processed by worker.
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.queue_name = "signal_queue:signals"
        self.stats_prefix = "signal_queue:stats:"
        self._redis = None
        self._connected = False

        if not REDIS_AVAILABLE:
            return

        try:
            self._redis = redis.Redis(
                host=host, port=port, db=db,
                decode_responses=True,
                socket_connect_timeout=2
            )
            self._redis.ping()
            self._connected = True
            logger.info(f"✅ Signal Queue connected at {host}:{port}")
        except Exception as e:
            logger.warning(f"⚠️ Signal Queue unavailable: {e}")

    def push_signal(self, pair: str, signal_type: str, confidence: float,
                   price: float, data: Dict = None, priority: int = 0) -> str:
        """
        Push trading signal to queue.
        signal_type: STRONG_BUY, BUY, STRONG_SELL, SELL
        priority: STRONG_BUY/STRONG_SELL = 10, BUY/SELL = 5
        """
        if not self._connected:
            return None

        signal_id = f"{pair}_{signal_type}_{int(time.time())}"

        signal = {
            "signal_id": signal_id,
            "pair": pair,
            "signal_type": signal_type,
            "confidence": confidence,
            "price": price,
            "data": data or {},
            "priority": priority,
            "created_at": time.time(),
            "status": "pending"  # pending → executing → done → skipped
        }

        try:
            self._redis.zadd(self.queue_name, {json.dumps(signal): -priority})

            # Update stats
            stat_key = f"{self.stats_prefix}{signal_type}"
            self._redis.incr(stat_key)
            self._redis.expire(stat_key, 86400)  # Reset daily

            logger.info(f"📊 Signal queued: {signal_type} {pair} @ {price:,.0f} (conf: {confidence:.0%})")
            return signal_id
        except Exception as e:
            logger.error(f"❌ Failed to queue signal: {e}")
            return None

    def pop_signal(self, timeout: int = 2) -> Optional[Dict]:
        """Pop highest priority signal from queue"""
        if not self._connected:
            return None

        try:
            result = self._redis.bzpopmin(self.queue_name, timeout=timeout)
            if result:
                _, signal_json, _ = result
                signal = json.loads(signal_json)
                signal["status"] = "executing"
                logger.info(f"🔨 Processing signal: {signal['signal_type']} {signal['pair']}")
                return signal
            return None
        except Exception:
            return None

    def mark_done(self, signal_id: str):
        """Mark signal as executed"""
        # Signal removed from queue, log completion
        logger.debug(f"✅ Signal done: {signal_id}")

    def mark_skipped(self, signal: Dict, reason: str):
        """Mark signal as skipped (e.g., insufficient balance)"""
        if not self._connected:
            return

        try:
            signal["status"] = "skipped"
            signal["skip_reason"] = reason
            self._redis.lpush("signal_queue:skipped", json.dumps(signal))
            self._redis.ltrim("signal_queue:skipped", 0, 99)  # Keep last 100
            logger.info(f"⏭️ Signal skipped: {signal['pair']} - {reason}")
        except Exception as e:
            logger.error(f"❌ Failed to mark skipped: {e}")

    def get_stats(self) -> Dict:
        """Get signal statistics (last 24h)"""
        if not self._connected:
            return {"error": "Signal Queue unavailable"}

        try:
            stats = {
                "pending": self._redis.zcard(self.queue_name),
                "skipped_count": self._redis.llen("signal_queue:skipped"),
            }

            for signal_type in ["STRONG_BUY", "BUY", "SELL", "STRONG_SELL"]:
                key = f"{self.stats_prefix}{signal_type}"
                count = self._redis.get(key)
                stats[signal_type] = int(count) if count else 0

            return stats
        except Exception as e:
            return {"error": str(e)}

    def clear_all(self):
        """
        🚨 HEDGE FUND: Clear all pending signals (used by emergency stop)
        """
        if not self._connected:
            return

        try:
            cleared = self._redis.zremrangebyrank(self.queue_name, 0, -1)
            logger.info(f"🛑 Cleared {cleared} pending signals (emergency stop)")
        except Exception as e:
            logger.error(f"Failed to clear signal queue: {e}")

    def is_available(self) -> bool:
        """Check if Signal Queue is available"""
        return self._connected


class TaskScheduler:
    """
    Scheduler for periodic background tasks.
    Replaces manual threading with cleaner task management.
    """

    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self._running = False
        self._thread = None

    def add_task(self, name: str, interval_seconds: int, func, description: str = ""):
        """
        Add scheduled task.

        name: Unique task name
        interval_seconds: How often to run (seconds)
        func: Callable to execute
        description: Human-readable description
        """
        self.tasks[name] = {
            "func": func,
            "interval": interval_seconds,
            "last_run": 0,
            "run_count": 0,
            "last_error": None,
            "description": description or name
        }
        logger.info(f"📅 Task scheduled: {name} (every {interval_seconds}s)")

    def start(self):
        """Start scheduler thread"""
        if self._running:
            logger.warning("⚠️ Scheduler already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="TaskScheduler")
        self._thread.start()
        logger.info(f"🔄 Scheduler started ({len(self.tasks)} tasks)")

    def stop(self):
        """Stop scheduler"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            logger.info("🛑 Scheduler stopped")

    def _scheduler_loop(self):
        """Main scheduler loop"""
        logger.info("🔄 Scheduler loop started")

        while self._running:
            now = time.time()

            for name, task in self.tasks.items():
                if (now - task["last_run"]) >= task["interval"]:
                    try:
                        logger.debug(f"⏰ Running task: {name}")
                        task["func"]()
                        task["last_run"] = now
                        task["run_count"] += 1
                        task["last_error"] = None
                    except Exception as e:
                        logger.error(f"❌ Task failed: {name} - {e}")
                        task["last_error"] = str(e)

            # Sleep 1 second before next check
            time.sleep(1)

    def get_status(self) -> Dict:
        """Get scheduler status"""
        now = time.time()
        status = {"running": self._running, "tasks": {}}

        for name, task in self.tasks.items():
            status["tasks"][name] = {
                "description": task["description"],
                "interval_seconds": task["interval"],
                "run_count": task["run_count"],
                "last_run": datetime.fromtimestamp(task["last_run"]).strftime("%H:%M:%S") if task["last_run"] > 0 else "Never",
                "next_run_in": max(0, task["interval"] - (now - task["last_run"])),
                "last_error": task["last_error"]
            }

        return status


# Global instances
signal_queue = SignalQueue()
scheduler = TaskScheduler()
