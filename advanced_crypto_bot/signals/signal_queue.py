# Tujuan: Queue dan scheduler signal untuk menghindari spam/rate limit.
# Caller: bot.py background signal notifications.
# Dependensi: asyncio/threading, scheduler state, Telegram sender caller.
# Main Functions: signal_queue; scheduler.
# Side Effects: Background task state; may trigger Telegram sends via caller.
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
import copy
import uuid
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
        self.inflight_name = "signal_queue:inflight"
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

        signal_id = f"{pair}_{signal_type}_{uuid.uuid4().hex}"

        # Keep a deep copy: callers often reuse/mutate indicator dictionaries
        # after enqueueing.  The queue is the execution boundary and therefore
        # owns an immutable semantic snapshot.
        payload_data = copy.deepcopy(data or {})
        semantic = dict(payload_data.get("signal") or payload_data)
        semantic.setdefault("pair", pair)
        semantic.setdefault("recommendation", signal_type)
        semantic.setdefault("ml_confidence", confidence)
        semantic.setdefault("price", price)
        source_user_id=payload_data.get("source_user_id") or payload_data.get("user_id")
        signal = {
            "version": 1,
            "signal_id": signal_id,
            "pair": pair,
            "signal_type": signal_type,
            "confidence": confidence,
            "price": price,
            "data": {**payload_data, "signal": semantic},
            "priority": priority,
            "created_at": time.time(),
            "status": "pending"  # pending → executing → done → skipped
        }
        if source_user_id is not None:
            signal["source_user_id"] = int(source_user_id)

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
            # Redis sorted sets cannot atomically move with blocking semantics;
            # claim via Lua so a crash leaves the envelope recoverable inflight.
            script = """
            local x=redis.call('ZRANGE',KEYS[1],0,0,'WITHSCORES')
            if #x==0 then return nil end
            redis.call('ZREM',KEYS[1],x[1]); redis.call('HSET',KEYS[2],x[1],ARGV[1]); return x[1]
            """
            signal_json = self._redis.eval(script, 2, self.queue_name, self.inflight_name, time.time())
            result = (self.queue_name, signal_json, 0) if signal_json else None
            if result:
                _, signal_json, _ = result
                try:
                    signal = json.loads(signal_json)
                except Exception as exc:
                    malformed = {"signal_id": f"malformed-{uuid.uuid4().hex}", "raw": signal_json}
                    self.mark_skipped(malformed, f"MALFORMED_ENVELOPE: {exc}")
                    self._redis.hdel(self.inflight_name, signal_json)
                    return None
                signal["status"] = "executing"
                signal["_raw_envelope"] = signal_json
                logger.info(f"🔨 Processing signal: {signal['signal_type']} {signal['pair']}")
                return signal
            return None
        except Exception as exc:
            logger.warning(f"⚠️ Signal Queue claim failed: {exc}")
            return None

    def mark_done(self, signal_id: str):
        """Mark signal as executed"""
        # Signal removed from queue, log completion
        logger.debug(f"✅ Signal done: {signal_id}")

    def ack(self, signal: Dict):
        if self._connected:
            raw = signal.get("_raw_envelope")
            if raw: self._redis.hdel(self.inflight_name, raw)

    def recover_inflight(self, min_age_seconds=0):
        if not self._connected:
            return 0
        now, recovered = time.time(), 0
        for raw, claimed in self._redis.hgetall(self.inflight_name).items():
            if now - float(claimed) >= min_age_seconds:
                try:
                    priority = int(json.loads(raw).get("priority", 0))
                    script="redis.call('ZADD',KEYS[1],ARGV[1],ARGV[2]); return redis.call('HDEL',KEYS[2],ARGV[2])"
                    self._redis.eval(script,2,self.queue_name,self.inflight_name,-priority,raw)
                    recovered += 1
                except Exception as exc:
                    self.mark_skipped({"raw": raw}, f"MALFORMED_INFLIGHT: {exc}")
                    self._redis.hdel(self.inflight_name, raw)
        return recovered

    def settle(self, signal: Dict, decision: Dict) -> str:
        """Persist outcome and either requeue retryable or ack terminal work."""
        self.mark_decision(signal, decision)
        if decision.get("status") == "ERROR_RETRYABLE":
            self.recover_inflight(min_age_seconds=0)
            return "REQUEUED"
        self.mark_done(signal.get("signal_id"))
        self.ack(signal)
        return "ACKED"

    def mark_decision(self, signal: Dict, decision: Dict):
        """Persist terminal/pending queue outcome; never silently discard work."""
        if not self._connected:
            return
        record = copy.deepcopy(signal)
        record["status"] = str(decision.get("status", "UNKNOWN")).lower()
        record["decision"] = copy.deepcopy(decision)
        raw=json.dumps(record,default=str)
        key=str(decision.get("idempotency_key") or signal.get("signal_id"))
        terminal=str(decision.get("status")) != "ERROR_RETRYABLE"
        script="""local old=redis.call('HGET',KEYS[1],ARGV[1]); if (not old) or ARGV[3]=='1' then redis.call('HSET',KEYS[1],ARGV[1],ARGV[2]); redis.call('LPUSH',KEYS[2],ARGV[2]); redis.call('LTRIM',KEYS[2],0,999); return 1 end return 0"""
        self._redis.eval(script,2,"signal_queue:decision_by_key","signal_queue:decisions",key,raw,"1" if terminal else "0")

    def mark_skipped(self, signal: Dict, reason: str):
        """Mark signal as skipped (e.g., insufficient balance)"""
        if not self._connected:
            return

        try:
            signal["status"] = "skipped"
            signal["skip_reason"] = reason
            self._redis.lpush("signal_queue:skipped", json.dumps(signal))
            self._redis.ltrim("signal_queue:skipped", 0, 99)  # Keep last 100
            logger.info(f"⏭️ Signal skipped: {signal.get('pair', 'UNKNOWN')} - {reason}")
            self.ack(signal)
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
                "decision_count": self._redis.llen("signal_queue:decisions"),
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
            return 0

        try:
            cleared = self._redis.zremrangebyrank(self.queue_name, 0, -1)
            logger.info(f"🛑 Cleared {cleared} pending signals (emergency stop)")
            return cleared
        except Exception as e:
            logger.error(f"Failed to clear signal queue: {e}")
            return 0

    def purge_pair(self, pair: str) -> int:
        """Remove pending queued signals for one pair."""
        if not self._connected:
            return 0

        pair_norm = str(pair or "").lower().replace("/", "").replace("_", "")
        if not pair_norm:
            return 0

        try:
            removed = 0
            for signal_json in self._redis.zrange(self.queue_name, 0, -1):
                try:
                    signal = json.loads(signal_json)
                except Exception:
                    continue
                signal_pair = str(signal.get("pair", "")).lower().replace("/", "").replace("_", "")
                if signal_pair == pair_norm:
                    removed += self._redis.zrem(self.queue_name, signal_json)

            if removed:
                logger.info(f"🧹 Purged {removed} queued signal(s) for {pair_norm}")
            return removed
        except Exception as e:
            logger.error(f"Failed to purge queued signals for {pair}: {e}")
            return 0

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
