"""
Redis Task Queue - Phase 3: Async Workers
==========================================
Task queue system for heavy commands. Push tasks to Redis queue,
background worker picks them up and processes them asynchronously.

KEUNTUNGAN:
  ⚡ Bot utama tidak pernah hang (instant reply "Processing...")
  🔒 Task survive bot restart (tersimpan di Redis)
  📊 Multiple workers bisa scale horizontal

CARA PAKAI:
    from redis_task_queue import task_queue
    
    # Push task to queue
    task_id = task_queue.push_task("s_posisi", user_id=123, data={...})
    
    # Worker picks up task
    task = task_queue.pop_task()  # Blocking wait
    
    # Worker marks complete
    task_queue.mark_complete(task_id, result={...})
    
    # Bot checks result
    result = task_queue.get_result(task_id)
"""

import os
import json
import uuid
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger('crypto_bot')

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ redis package not installed. Task queue disabled.")


class RedisTaskQueue:
    """
    Redis-backed task queue with result storage.
    Tasks are processed by background workers.
    """

    def __init__(self, host: str = None, port: int = None, db: int = None):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", port or 6379))
        self.db_num = int(os.getenv("REDIS_DB", db or 0))
        self.queue_name = "task_queue:tasks"
        self.result_prefix = "task_queue:result:"
        self.ttl = 3600  # Results expire after 1 hour

        self._redis = None
        self._connected = False

        # Try connect to Redis
        self._connect_redis()

    def _connect_redis(self):
        """Try connect to Redis server"""
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis package not available, task queue disabled")
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
            logger.info(f"✅ Task Queue connected at {self.host}:{self.port}")
        except Exception as e:
            logger.warning(f"⚠️ Task Queue unavailable ({e}), tasks will run sync")
            self._connected = False
            self._redis = None

    def push_task(self, task_type: str, user_id: int, chat_id: int = None,
                  message_id: int = None, data: Dict = None, priority: int = 0) -> str:
        """
        Push task to queue. Returns task_id.
        
        task_type: "s_posisi", "s_menu", "signal", etc.
        user_id: Telegram user ID
        chat_id: Telegram chat ID (for sending result)
        message_id: Original message ID (for editing)
        data: Task-specific data
        priority: Higher = processed first
        """
        if not self._connected:
            logger.warning("⚠️ Task queue unavailable, running sync")
            return None

        task_id = str(uuid.uuid4())[:8]

        task = {
            "task_id": task_id,
            "task_type": task_type,
            "user_id": user_id,
            "chat_id": chat_id or user_id,
            "message_id": message_id,
            "data": data or {},
            "priority": priority,
            "created_at": time.time(),
            "status": "pending"  # pending → processing → complete → error
        }

        try:
            # Push to sorted set (priority queue)
            self._redis.zadd(self.queue_name, {json.dumps(task): -priority})
            logger.debug(f"📦 Task queued: {task_type} (ID: {task_id}, Priority: {priority})")
            return task_id
        except Exception as e:
            logger.error(f"❌ Failed to queue task: {e}")
            self._connected = False
            return None

    def pop_task(self, timeout: int = 5) -> Optional[Dict]:
        """
        Pop highest priority task from queue. Blocking wait.
        Returns task dict or None if timeout.
        """
        if not self._connected:
            return None

        try:
            # Blocking wait for task (with timeout)
            result = self._redis.bzpopmin(self.queue_name, timeout=timeout)
            if result:
                _, task_json, _ = result
                task = json.loads(task_json)
                task["status"] = "processing"
                task["started_at"] = time.time()
                logger.debug(f"🔄 Task picked up: {task['task_type']} (ID: {task['task_id']})")
                return task
            return None
        except Exception as e:
            logger.debug(f"Pop task error: {e}")
            return None

    def mark_complete(self, task_id: str, result: Dict):
        """Mark task as complete with result"""
        if not self._connected:
            return

        try:
            key = f"{self.result_prefix}{task_id}"
            result_data = {
                "task_id": task_id,
                "status": "complete",
                "result": result,
                "completed_at": time.time()
            }
            self._redis.setex(key, self.ttl, json.dumps(result_data))
            logger.debug(f"✅ Task completed: {task_id}")
        except Exception as e:
            logger.error(f"❌ Failed to mark task complete: {e}")

    def mark_error(self, task_id: str, error: str):
        """Mark task as failed with error"""
        if not self._connected:
            return

        try:
            key = f"{self.result_prefix}{task_id}"
            result_data = {
                "task_id": task_id,
                "status": "error",
                "error": error,
                "completed_at": time.time()
            }
            self._redis.setex(key, self.ttl, json.dumps(result_data))
            logger.debug(f"❌ Task failed: {task_id}")
        except Exception as e:
            logger.error(f"❌ Failed to mark task error: {e}")

    def get_result(self, task_id: str) -> Optional[Dict]:
        """Get task result. Returns None if not ready."""
        if not self._connected:
            return None

        try:
            key = f"{self.result_prefix}{task_id}"
            data = self._redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.debug(f"Get result error: {e}")
            return None

    def is_available(self) -> bool:
        """Check if task queue is available"""
        if not self._connected and self._redis:
            try:
                self._redis.ping()
                self._connected = True
            except Exception:
                self._connected = False
        return self._connected

    def get_queue_size(self) -> int:
        """Get number of pending tasks"""
        if not self._connected:
            return 0
        try:
            return self._redis.zcard(self.queue_name)
        except Exception:
            return 0


# Global instance
task_queue = RedisTaskQueue()
