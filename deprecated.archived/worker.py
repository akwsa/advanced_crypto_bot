#!/usr/bin/env python3
"""
Background Worker for Docker Deployment
=========================================
Process heavy tasks from Redis queue.
Run by docker-compose as 'worker' service.

Compatible with redis_task_queue.py (Phase 3: Async Workers)
"""

import asyncio
import time
import json
import logging
import sys
import os
import requests
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import Config
from cache.redis_task_queue import task_queue

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, 'INFO'),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/worker.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('worker')


def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    """Send message to Telegram user via Bot API"""
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.debug(f"📤 Message sent to user {chat_id}")
            return True
        else:
            logger.warning(f"Failed to send message: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def process_s_posisi(task_data):
    """
    Heavy task: Calculate positions for all pairs
    This is the slow /s_posisi command
    """
    start = time.time()
    user_id = task_data.get('user_id')
    chat_id = task_data.get('chat_id')

    logger.info(f"🔨 Processing s_posisi for user {user_id}")

    # TODO: Import actual position calculation logic from scalper_module
    # For now, return placeholder
    result = {
        'status': 'success',
        'message': 'Position calculation completed',
        'positions': [],
        'total_pnl': 0,
        'processing_time': time.time() - start
    }

    logger.info(f"✅ s_posisi completed in {result['processing_time']:.2f}s")

    # Send result to user
    if chat_id:
        msg = f"""
📦 **Position Report**

⏱️ Processing time: {result['processing_time']:.2f}s
📊 Positions: {len(result['positions'])}
💰 Total P&L: {result['total_pnl']:,.0f} IDR

_Detail position data akan ditampilkan setelah integrasi dengan scalper module._
"""
        send_telegram_message(chat_id, msg)

    return result


def process_s_menu(task_data):
    """
    Heavy task: Fetch prices for all pairs + generate menu
    This is the slow /s_menu command
    """
    start = time.time()
    user_id = task_data.get('user_id')
    chat_id = task_data.get('chat_id')

    logger.info(f"🔨 Processing s_menu for user {user_id}")

    # TODO: Import actual menu generation logic
    result = {
        'status': 'success',
        'message': 'Menu generation completed',
        'pairs': [],
        'processing_time': time.time() - start
    }

    logger.info(f"✅ s_menu completed in {result['processing_time']:.2f}s")

    if chat_id:
        msg = f"""
📊 **Scalper Menu**

⏱️ Processing time: {result['processing_time']:.2f}s
📈 Pairs scanned: {len(result['pairs'])}

_Menu data akan ditampilkan setelah integrasi._
"""
        send_telegram_message(chat_id, msg)

    return result


def process_signal(task_data):
    """
    Heavy task: Generate trading signal (TA + ML)
    This is the slow /signal command
    """
    start = time.time()
    user_id = task_data.get('user_id')
    chat_id = task_data.get('chat_id')
    pair = task_data.get('data', {}).get('pair', '')

    logger.info(f"🔨 Processing signal for {pair}")

    # TODO: Import actual signal generation logic
    result = {
        'status': 'success',
        'message': f'Signal for {pair} ready',
        'pair': pair,
        'processing_time': time.time() - start
    }

    logger.info(f"✅ Signal completed in {result['processing_time']:.2f}s")

    if chat_id:
        msg = f"""
🤖 **Signal: {pair}**

⏱️ Analysis time: {result['processing_time']:.2f}s

_Signal detail akan dikirim setelah integrasi._
"""
        send_telegram_message(chat_id, msg)

    return result


# Task handler mapping
TASK_HANDLERS = {
    's_posisi': process_s_posisi,
    's_menu': process_s_menu,
    'signal': process_signal,
}


def worker_loop():
    """Main worker loop - pick tasks from Redis queue using task_queue module"""
    if not task_queue.is_available():
        logger.error("❌ Worker cannot start without Redis / task_queue unavailable")
        sys.exit(1)

    logger.info("🚀 Worker started - waiting for tasks...")
    logger.info(f"📋 Registered handlers: {list(TASK_HANDLERS.keys())}")

    while True:
        try:
            # Pop task from queue (blocking wait with timeout)
            task = task_queue.pop_task(timeout=5)

            if task is None:
                continue  # Timeout, try again

            task_type = task.get('task_type', 'unknown')
            task_id = task.get('task_id', 'unknown')

            logger.info(f"📥 Picked task: {task_type} (ID: {task_id})")

            # Execute task
            handler = TASK_HANDLERS.get(task_type)
            if handler:
                try:
                    result = handler(task)

                    # Mark complete via task_queue
                    task_queue.mark_complete(task_id, result)

                    logger.info(f"✅ Task completed: {task_type} (ID: {task_id})")

                except Exception as e:
                    logger.error(f"❌ Task failed: {task_type} (ID: {task_id}): {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")

                    # Mark error via task_queue
                    task_queue.mark_error(task_id, str(e))

                    # Notify user
                    chat_id = task.get('chat_id')
                    if chat_id:
                        send_telegram_message(
                            chat_id,
                            f"❌ Task `{task_type}` failed:\n`{str(e)}`\n\n💡 Try again later.",
                            parse_mode='Markdown'
                        )
            else:
                logger.warning(f"⚠️ Unknown task type: {task_type}")
                task_queue.mark_error(task_id, f"Unknown task type: {task_type}")

        except KeyboardInterrupt:
            logger.info("🛑 Worker shutdown requested")
            break
        except Exception as e:
            logger.error(f"❌ Worker error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            time.sleep(5)  # Backoff on error

    logger.info("👋 Worker stopped")


if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)

    logger.info("=" * 60)
    logger.info("🚀 Crypto Trading Bot - Background Worker")
    logger.info(f"   Python:   {sys.version}")
    logger.info(f"   Redis:    {task_queue.host}:{task_queue.port}")
    logger.info(f"   Queue:    {task_queue.is_available()}")
    logger.info("=" * 60)

    worker_loop()
