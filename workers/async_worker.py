"""
Background Worker - Phase 3: Async Workers
===========================================
Background process that picks up tasks from Redis queue and processes them.
Sends results back to users via Telegram API.

CARA JALANKAN:
    python worker.py
    
    Atau otomatis start dari bot.py saat init
"""

import asyncio
import time
import threading
import logging
import requests
from typing import Dict, Any

from cache.redis_task_queue import task_queue
from core.config import Config

logger = logging.getLogger('crypto_bot')


class BackgroundWorker:
    """
    Background worker that processes tasks from Redis queue.
    Runs in a separate thread.
    """

    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self._thread = None
        self._running = False
        self._telegram_token = Config.TELEGRAM_BOT_TOKEN

    def start(self):
        """Start worker thread"""
        if not task_queue.is_available():
            logger.warning("⚠️ Redis not available, worker not started")
            return

        if self._running:
            logger.warning("⚠️ Worker already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AsyncWorker")
        self._thread.start()
        logger.info("✅ Background worker started")

    def stop(self):
        """Stop worker thread"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("🛑 Background worker stopped")

    def _worker_loop(self):
        """Main worker loop - pick tasks and process them"""
        logger.info("🔄 Worker loop started")

        while self._running:
            try:
                # Pick task from queue (blocking wait with 5s timeout)
                task = task_queue.pop_task(timeout=5)

                if task is None:
                    continue  # Timeout, try again

                task_type = task.get("task_type", "unknown")
                task_id = task.get("task_id", "unknown")

                logger.info(f"🔨 Processing task: {task_type} (ID: {task_id})")

                # Execute task based on type
                result = self._execute_task(task)

                # Mark complete
                task_queue.mark_complete(task_id, result)

                # Send result to user via Telegram
                self._send_result(task, result)

                logger.info(f"✅ Task completed: {task_type} (ID: {task_id})")

            except Exception as e:
                logger.error(f"❌ Worker error: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")

                # Mark current task as error if we have it
                try:
                    if 'task_id' in locals():
                        task_queue.mark_error(task_id, str(e))
                        self._send_error(task, str(e))
                except Exception as send_error:
                    logger.error(f"Failed to send error notification: {send_error}")

    def _execute_task(self, task: Dict) -> Dict:
        """Execute task based on type"""
        task_type = task.get("task_type")
        data = task.get("data", {})

        if task_type == "s_posisi":
            return self._handle_s_posisi(task)
        elif task_type == "s_menu":
            return self._handle_s_menu(task)
        elif task_type == "signal":
            return self._handle_signal(task)
        elif task_type == "position":
            return self._handle_position(task)
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def _handle_s_posisi(self, task: Dict) -> Dict:
        """Handle s_posisi task"""
        # This is a placeholder - actual implementation will call scalper module
        # For now, return success and let the existing scalper code handle rendering
        return {
            "status": "ready",
            "message": "Position data fetched and cached in Redis",
            "pairs_count": task.get("data", {}).get("pairs_count", 0)
        }

    def _handle_s_menu(self, task: Dict) -> Dict:
        """Handle s_menu task"""
        return {
            "status": "ready",
            "message": "Menu data fetched and cached in Redis"
        }

    def _handle_signal(self, task: Dict) -> Dict:
        """Handle signal task"""
        pair = task.get("data", {}).get("pair", "")
        return {
            "status": "ready",
            "message": f"Signal for {pair} ready",
            "pair": pair
        }

    def _handle_position(self, task: Dict) -> Dict:
        """Handle position task"""
        pair = task.get("data", {}).get("pair", "")
        return {
            "status": "ready",
            "message": f"Position analysis for {pair} ready",
            "pair": pair
        }

    def _send_result(self, task: Dict, result: Dict):
        """Send task result to user via Telegram"""
        chat_id = task.get("chat_id")
        message_id = task.get("message_id")
        task_type = task.get("task_type")

        if not chat_id:
            logger.warning(f"No chat_id for task {task.get('task_id')}")
            return

        message = result.get("message", "✅ Task completed")

        # Build reply text based on task type
        if task_type == "s_posisi":
            reply_text = f"📦 {message}\n\n💡 Gunakan /s_posisi untuk melihat detail posisi."
        elif task_type == "s_menu":
            reply_text = f"📊 {message}\n\n💡 Gunakan /s_menu untuk melihat menu."
        elif task_type == "signal":
            pair = result.get("pair", "unknown")
            reply_text = f"🤖 Signal untuk {pair} siap.\n\n💡 Gunakan /signal {pair} untuk melihat detail."
        elif task_type == "position":
            pair = result.get("pair", "unknown")
            reply_text = f"📊 Analisis untuk {pair} siap.\n\n💡 Gunakan /position {pair} untuk melihat detail."
        else:
            reply_text = f"✅ {message}"

        # Send via Telegram API
        try:
            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": reply_text,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.debug(f"📤 Result sent to user {chat_id}")
            else:
                logger.warning(f"Failed to send result: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send result via Telegram: {e}")

    def _send_error(self, task: Dict, error: str):
        """Send error notification to user"""
        chat_id = task.get("chat_id")
        if not chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": f"❌ Task gagal:\n`{error}`\n\n💡 Coba lagi nanti.",
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")


# Global instance (set by bot.py)
worker = None
