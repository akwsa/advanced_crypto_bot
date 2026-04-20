#!/usr/bin/env python3
"""
Smart Hunter Integration Module
Wraps smart_profit_hunter.py for use within the main bot
"""

import asyncio
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Any

from autohunter.smart_profit_hunter import SmartProfitHunter, TAKE_PROFIT_LEVELS, STOP_LOSS, TRAILING_STOP, INDODAX_API_URL

logger = logging.getLogger('crypto_bot')


class SmartHunterBotIntegration:
    """
    Integrates SmartProfitHunter into the main bot
    - Runs in background thread
    - Controlled via Telegram commands
    - Uses main bot's Telegram bot for notifications
    - Respects DRY RUN / REAL TRADE settings from main bot config
    """

    def __init__(self, main_bot=None, db=None, indodax_api=None):
        self.main_bot = main_bot
        self.db = db
        self.indodax_api = indodax_api

        # Get DRY RUN setting from main bot config
        dry_run = True  # Default to safe mode
        if main_bot and hasattr(main_bot, 'config'):
            dry_run = main_bot.config.AUTO_TRADE_DRY_RUN
        else:
            # Try to get from Config directly
            try:
                from core.config import Config
                dry_run = Config.AUTO_TRADE_DRY_RUN
            except Exception:
                dry_run = True

        # Smart Hunter instance with DRY RUN mode
        self.hunter = SmartProfitHunter(dry_run=dry_run)

        # State
        self.is_running = False
        self._thread = None
        self._stop_event = threading.Event()

        # Replace hunter's bot with main bot's app for unified notifications
        if main_bot and hasattr(main_bot, 'app'):
            self.hunter.bot = main_bot.app.bot

        mode_label = "🧪 DRY RUN" if dry_run else "🔴 REAL TRADING"
        logger.info(f"✅ Smart Hunter integration initialized ({mode_label})")
    
    async def start(self):
        """Start Smart Hunter background task"""
        if self.is_running:
            logger.warning("⚠️ Smart Hunter already running")
            return False
        
        self.is_running = True
        self._stop_event.clear()
        
        # Start in background thread
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        logger.info("🚀 Smart Hunter started")
        return True
    
    async def stop(self):
        """Stop Smart Hunter background task"""
        if not self.is_running:
            logger.warning("⚠️ Smart Hunter not running")
            return False
        
        self.is_running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        logger.info("🛑 Smart Hunter stopped")
        return True
    
    def _run_loop(self):
        """Background loop for Smart Hunter (runs in separate thread)"""
        import asyncio
        
        # Create event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger.info("🔄 Smart Hunter background loop started")
        
        try:
            while not self._stop_event.is_set():
                try:
                    # Get balance
                    self.hunter.get_balance()
                    
                    # Get tickers
                    tickers = self.hunter.session.get(
                        f"{INDODAX_API_URL}/api/tickers",
                        timeout=10
                    ).json().get('tickers', {})
                    
                    if tickers:
                        # Find opportunities
                        opportunities = self.hunter.find_best_opportunity(tickers)
                        
                        if opportunities and not self.hunter.active_trades:
                            top = opportunities[0]
                            logger.info(f"🎯 Opportunity found: {top['pair']} (Score: {top['score']})")
                            
                            if self.hunter.balance_idr > self.hunter.MAX_POSITION_SIZE:
                                loop.run_until_complete(
                                    self.hunter.execute_smart_trade(top)
                                )
                        
                        # Monitor positions
                        loop.run_until_complete(
                            self.hunter.monitor_positions_smart()
                        )
                    
                    # Sleep until next scan
                    self._stop_event.wait(timeout=30)  # Scan every 30 seconds
                    
                except Exception as e:
                    logger.error(f"❌ Smart Hunter loop error: {e}")
                    self._stop_event.wait(timeout=30)
        
        finally:
            loop.close()
            logger.info("🛑 Smart Hunter background loop ended")
    
    def get_status(self) -> Dict[str, Any]:
        """Get Smart Hunter status for /smarthunter_status command"""
        return {
            'is_running': self.is_running,
            'active_trades': len(self.hunter.active_trades),
            'daily_trades': self.hunter.daily_trades,
            'daily_pnl': self.hunter.daily_pnl,
            'balance': self.hunter.balance_idr,
            'trades': list(self.hunter.active_trades.items())
        }
    
    async def send_status_message(self, update, context) -> str:
        """Send detailed status message to Telegram"""
        status = self.get_status()
        
        status_emoji = "🟢" if status['is_running'] else "⚪"
        status_text = "RUNNING" if status['is_running'] else "STOPPED"
        
        text = f"🤖 **SMART HUNTER STATUS**\n\n"
        text += f"📊 **Status:** {status_emoji} {status_text}\n"
        text += f"💰 **Balance:** `{self.hunter.balance_idr:,.0f}` IDR\n"
        text += f"📈 **Active Positions:** {status['active_trades']}\n"
        text += f"📅 **Today's Trades:** {status['daily_trades']}\n"
        text += f"💵 **Daily P&L:** `{status['daily_pnl']:,.0f}` IDR\n\n"
        
        if status['active_trades'] > 0:
            text += "📊 **Open Positions:**\n"
            for pair, trade in status['trades'][:3]:
                entry = trade['entry_price']
                coin_amt = trade['coin_amount']
                text += f"🔹 `{pair}`: Entry `{entry:,.0f}` IDR, Amount `{coin_amt:.2f}`\n"
        else:
            text += "📊 No open positions\n"
        
        text += "\n💡 **Commands:**\n"
        text += "• `/smarthunter on` - Start Smart Hunter\n"
        text += "• `/smarthunter off` - Stop Smart Hunter\n"
        text += "• `/smarthunter_status` - This message\n"
        
        return text
