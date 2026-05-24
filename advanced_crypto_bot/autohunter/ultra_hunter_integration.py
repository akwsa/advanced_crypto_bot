#!/usr/bin/env python3
# Tujuan: Integrasi Ultra Hunter untuk hunting peluang agresif.
# Caller: bot.py startup dan command ultra hunter.
# Dependensi: UltraHunter engine, Telegram context, Config.
# Main Functions: class UltraHunterBotIntegration.
# Side Effects: Background tasks, DB/cache reads, possible HTTP order path.
"""
Ultra Hunter Integration Module
Wraps autohunter.ultra_hunter for use within the main bot.
"""

import asyncio
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Any

from autohunter.ultra_hunter import UltraConservativeHunter, INDODAX_API_URL

logger = logging.getLogger('crypto_bot')


class UltraHunterBotIntegration:
    """
    Integrates UltraConservativeHunter into the main bot.
    - Runs in background thread
    - Controlled via Telegram commands
    - Uses main bot's Telegram bot for notifications
    - Respects DRY RUN / REAL TRADE settings from main bot config
    """

    def __init__(self, main_bot=None, db=None, dry_run=None):
        self.main_bot = main_bot
        self.db = db

        if dry_run is not None:
            dry_run = bool(dry_run)
        else:
            dry_run = True
            if main_bot and hasattr(main_bot, 'config'):
                dry_run = main_bot.config.AUTO_TRADE_DRY_RUN
            else:
                try:
                    from core.config import Config
                    dry_run = Config.AUTO_TRADE_DRY_RUN
                except Exception:
                    dry_run = True

        self.hunter = UltraConservativeHunter(dry_run=dry_run, db=db)

        self.is_running = False
        self._thread = None
        self._stop_event = threading.Event()

        if main_bot and hasattr(main_bot, 'app'):
            self.hunter.bot = main_bot.app.bot

        if main_bot:
            self.hunter.main_bot = main_bot

        mode_label = "🧪 DRY RUN" if dry_run else "🔴 REAL TRADING"
        logger.info(f"✅ Ultra Hunter integration initialized ({mode_label})")

    async def start(self):
        if self.is_running:
            logger.warning("⚠️ Ultra Hunter already running")
            return False

        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("🚀 Ultra Hunter started")
        return True

    async def stop(self):
        if not self.is_running:
            logger.warning("⚠️ Ultra Hunter not running")
            return False

        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("🛑 Ultra Hunter stopped")
        return True

    def _run_loop(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("🔄 Ultra Hunter background loop started")

        try:
            while not self._stop_event.is_set():
                try:
                    self.hunter.get_balance()
                    tickers = self.hunter.session.get(
                        f"{INDODAX_API_URL}/api/tickers",
                        timeout=10
                    ).json().get('tickers', {})

                    if tickers:
                        loop.run_until_complete(self.hunter.scan_and_trade(tickers))
                        loop.run_until_complete(self.hunter.monitor_positions(tickers))

                    self._stop_event.wait(timeout=30)
                except Exception as e:
                    logger.error(f"❌ Ultra Hunter loop error: {e}")
                    self._stop_event.wait(timeout=30)
        finally:
            loop.close()
            logger.info("🛑 Ultra Hunter background loop ended")

    def get_status(self) -> Dict[str, Any]:
        return {
            'is_running': self.is_running,
            'active_trades': len(self.hunter.active_trades),
            'daily_trades': self.hunter.daily_trades,
            'daily_pnl': self.hunter.daily_pnl,
            'balance': self.hunter.balance_idr,
            'trades': list(self.hunter.active_trades.items())
        }

    async def send_status_message(self, update, context) -> str:
        status = self.get_status()
        status_emoji = "🟢" if status['is_running'] else "⚪"
        status_text = "JALAN" if status['is_running'] else "STOP"
        mode_text = "DRY RUN" if self.hunter.dry_run else "REAL"
        pnl_icon = "🟢" if status['daily_pnl'] >= 0 else "🔴"

        text = "🛡️ **Ultra Hunter**\n\n"
        text += f"Status: {status_emoji} **{status_text}**\n"
        text += f"Mode: `{mode_text}`\n"
        text += f"Saldo kerja: `{self.hunter.balance_idr:,.0f}` IDR\n"
        text += f"Posisi aktif: `{status['active_trades']}`\n"
        text += f"Trade hari ini: `{status['daily_trades']}`\n"
        text += f"{pnl_icon} P&L hari ini: `{status['daily_pnl']:,.0f}` IDR\n\n"

        if status['active_trades'] > 0:
            text += "**Posisi terbuka:**\n"
            for pair, trade in status['trades'][:3]:
                entry = trade['entry_price']
                coin_amt = trade['coin_amount']
                text += f"• `{pair}` entry `{entry:,.0f}` IDR, sisa `{coin_amt:.8f}` coin\n"
        else:
            text += "Belum ada posisi terbuka.\n"

        text += "\n**Kontrol cepat:**\n"
        text += "• `/ultrahunter start` - nyalakan\n"
        text += "• `/ultrahunter stop` - matikan\n"
        text += "• `/hunter_status` - ringkasan semua hunter\n"
        return text
