from datetime import datetime
from core.config import Config
import logging

logger = logging.getLogger(__name__)

# Tiered drop notification thresholds (percentage drop from entry)
DROP_ALERT_THRESHOLDS = [3, 5, 10, 15, 20, 25, 30]


class PriceMonitor:
    """
    Monitor price movements and trigger notifications when:
    - Price hits Stop Loss (Cut Loss)
    - Price hits Take Profit (Sell Target)
    - Price drops by tiered percentages (3%, 5%, 10%, 15%, 20%, 25%, 30%)
    - Trailing stop activation and triggers
    """

    def __init__(self, db, bot_app=None, subscribers=None):
        self.db = db
        self.bot_app = bot_app
        self.subscribers = subscribers or {}
        self.price_levels = {}  # Track SL/TP levels for each position
        self.notified_drops = {}  # Track which drop thresholds have been notified per trade
        self.trailing_stops = {}  # Track trailing stops: {key: {'highest': float, 'active': bool}}

    def set_price_level(self, user_id, trade_id, pair, entry_price, stop_loss, take_profit_1, take_profit_2=None, amount=0):
        """Set price levels to monitor for a trade with Partial Take Profit"""
        key = f"{user_id}_{trade_id}"
        self.price_levels[key] = {
            'user_id': user_id,
            'trade_id': trade_id,
            'pair': pair,
            'entry_price': entry_price,
            'amount': amount,
            'stop_loss': stop_loss,
            'take_profit_1': take_profit_1,  # First TP (lower)
            'take_profit_2': take_profit_2,   # Second TP (higher)
            'partial_1_triggered': False,    # Track if first partial TP hit
            'partial_2_triggered': False,    # Track if second partial TP hit
            'created_at': datetime.now(),
            'triggered': False
        }
        # Initialize drop notification tracking for this trade
        self.notified_drops[key] = set()
        
        # Initialize trailing stop tracking
        self.trailing_stops[key] = {
            'highest_price': entry_price,
            'trailing_stop_price': stop_loss,  # Start with initial SL
            'is_active': False  # Will activate when profit reaches threshold
        }
        
        logger.info(f"📊 Monitoring {pair}: SL={stop_loss:,.0f}, TP1={take_profit_1:,.0f}, TP2={take_profit_2 or 'N/A'}, Amount={amount}")

    def remove_price_level(self, user_id, trade_id):
        """Remove price level monitoring for closed trade"""
        key = f"{user_id}_{trade_id}"
        if key in self.price_levels:
            del self.price_levels[key]
            # Also clean up drop notification tracking
            if key in self.notified_drops:
                del self.notified_drops[key]
            # Clean up trailing stop tracking
            if key in self.trailing_stops:
                del self.trailing_stops[key]
            logger.info(f"❌ Removed monitoring for trade {trade_id}")
    
    async def check_price_levels(self, pair, current_price):
        """Check if price hits any SL/TP levels, trailing stop, and drop alerts"""
        triggered = []

        for key, level in list(self.price_levels.items()):
            if level['pair'] != pair:
                continue

            # Avoid duplicate triggers - check if already processed recently
            if level.get('triggered', False):
                continue

            # Update trailing stop tracking
            await self._update_trailing_stop(key, level, current_price)

            # Check tiered drop alerts BEFORE checking SL/TP
            await self._check_drop_alerts(key, level, current_price)

            hit_type = None

            # Check trailing stop (if active)
            if key in self.trailing_stops and self.trailing_stops[key]['is_active']:
                trailing_stop_price = self.trailing_stops[key]['trailing_stop_price']
                if current_price <= trailing_stop_price:
                    hit_type = 'TRAILING_STOP'

            # Check Stop Loss (if not already hit trailing stop)
            if not hit_type and current_price <= level['stop_loss']:
                hit_type = 'STOP_LOSS'
            # Check Partial Take Profit 1 (first target - sell 50%)
            elif not hit_type and not level.get('partial_1_triggered', False) and current_price >= level.get('take_profit_1', 0):
                hit_type = 'PARTIAL_TP_1'
                level['partial_1_triggered'] = True
            # Check Partial Take Profit 2 (final target - sell remaining 50%)
            elif not hit_type and level.get('partial_1_triggered', False) and not level.get('partial_2_triggered', False) and current_price >= level.get('take_profit_2', 0):
                hit_type = 'TAKE_PROFIT'  # Final exit
                level['partial_2_triggered'] = True

            if hit_type:
                # Mark as triggered to prevent duplicate
                level['triggered'] = True

                # Build message based on hit type
                if hit_type == 'TRAILING_STOP':
                    highest = self.trailing_stops[key]['highest_price']
                    pair_escaped = pair.replace('_', '\\_').replace('*', '\\*')
                    triggered.append({
                        'type': hit_type,
                        'level': level,
                        'price': current_price,
                        'message': f"🎯 **TRAILING STOP TRIGGERED!**\n\n"
                                  f"📊 Pair: {pair_escaped}\n"
                                  f"💰 Entry: `{level['entry_price']:,.0f}` IDR\n"
                                  f"📈 Highest: `{highest:,.0f}` IDR\n"
                                  f"📍 Exit: `{current_price:,.0f}` IDR\n\n"
                                  f"🔄 Executing auto-sell..."
                    })
                elif hit_type == 'PARTIAL_TP_1':
                    pair_escaped = pair.replace('_', '\\_').replace('*', '\\*')
                    triggered.append({
                        'type': hit_type,
                        'level': level,
                        'price': current_price,
                        'message': f"🎯 **PARTIAL TAKE PROFIT #1!**\n\n"
                                  f"📊 Pair: {pair_escaped}\n"
                                  f"💰 Entry: `{level['entry_price']:,.0f}` IDR\n"
                                  f"📍 Target 1: `{level.get('take_profit_1', 0):,.0f}` IDR\n"
                                  f"📈 Hit: `{current_price:,.0f}` IDR\n\n"
                                  f"✅ 50% position sold at profit!\n"
                                  f"📊 Remaining 50% continues to Target 2: `{level.get('take_profit_2', 0):,.0f}`"
                    })
                else:
                    pair_escaped = pair.replace('_', '\\_').replace('*', '\\*') if pair else 'N/A'
                    triggered.append({
                        'type': hit_type,
                        'level': level,
                        'price': current_price,
                        'message': f"{'🛑' if hit_type == 'STOP_LOSS' else '🎯'} **{hit_type.replace('_', ' ')} TRIGGERED!**\n\n"
                                  f"📊 Pair: {pair_escaped}\n"
                                  f"💰 Entry: `{level['entry_price']:,.0f}` IDR\n"
                                  f"📍 Hit: `{current_price:,.0f}` IDR\n\n"
                                  f"{'🔄 Executing auto-sell...' if hit_type == 'TAKE_PROFIT' else '🔄 Executing stop-loss sell...'}"
                    })

                # Execute auto-sell
                await self._execute_auto_sell(level, current_price, hit_type)

        # Send notifications
        for trigger in triggered:
            await self._send_notification(trigger)

        return triggered

    async def _update_trailing_stop(self, key, level, current_price):
        """Update trailing stop level if price is rising"""
        if key not in self.trailing_stops:
            return

        trailing_data = self.trailing_stops[key]
        entry_price = level['entry_price']
        
        # Calculate current profit percentage
        profit_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Update highest price seen so far
        if current_price > trailing_data['highest_price']:
            trailing_data['highest_price'] = current_price
        
        highest = trailing_data['highest_price']
        
        # Activate trailing stop if profit reaches activation threshold
        if not trailing_data['is_active'] and profit_pct >= Config.TRAILING_ACTIVATION_PCT:
            trailing_data['is_active'] = True
            # Set initial trailing stop at highest price - trailing %
            trailing_data['trailing_stop_price'] = highest * (1 - Config.TRAILING_STOP_PCT / 100)
            logger.info(f"🎯 Trailing stop ACTIVATED for {level['pair']} at {highest:,.0f}")
        
        # Update trailing stop if price is still rising
        if trailing_data['is_active']:
            new_trailing_stop = highest * (1 - Config.TRAILING_STOP_PCT / 100)
            # Only move trailing stop UP, never down
            if new_trailing_stop > trailing_data['trailing_stop_price']:
                trailing_data['trailing_stop_price'] = new_trailing_stop
                logger.debug(f"📈 Trailing stop updated for {level['pair']}: {new_trailing_stop:,.0f}")

    async def _check_drop_alerts(self, key, level, current_price):
        """Check if price has dropped by tiered percentages and send warnings"""
        entry_price = level['entry_price']
        if entry_price <= 0:
            return

        drop_pct = ((entry_price - current_price) / entry_price) * 100

        # Only alert if price is below entry (actual loss)
        if drop_pct <= 0:
            return

        # Check each threshold
        for threshold in DROP_ALERT_THRESHOLDS:
            if drop_pct >= threshold and threshold not in self.notified_drops.get(key, set()):
                # Mark as notified so we don't spam
                if key not in self.notified_drops:
                    self.notified_drops[key] = set()
                self.notified_drops[key].add(threshold)

                # Build alert message
                pair_escaped = level['pair'].replace('_', '\\_').replace('*', '\\*')
                drop_amount = entry_price - current_price

                # Severity-based emoji
                if threshold >= 20:
                    severity_emoji = "🚨"
                    severity_text = "CRITICAL"
                elif threshold >= 15:
                    severity_emoji = "⚠️"
                    severity_text = "WARNING"
                elif threshold >= 10:
                    severity_emoji = "📉"
                    severity_text = "ALERT"
                elif threshold >= 5:
                    severity_emoji = "📊"
                    severity_text = "NOTICE"
                else:
                    severity_emoji = "🔔"
                    severity_text = "INFO"

                message = (
                    f"{severity_emoji} **PRICE DROP {severity_text} - {threshold:.0f}%**\n\n"
                    f"📊 Pair: {pair_escaped}\n"
                    f"💰 Entry: `{entry_price:,.0f}` IDR\n"
                    f"📉 Current: `{current_price:,.0f}` IDR\n"
                    f"📉 Drop: `-{drop_pct:.1f}%` (-`{drop_amount:,.0f}` IDR)\n\n"
                    f"⚡ _Consider your strategy:_\n"
                    f"• {'🚨 Major drop! Review position carefully' if threshold >= 20 else '• Monitor closely'}\n"
f"• SL at `{level['stop_loss']:,.0f}` (-{((entry_price - level['stop_loss'])/entry_price)*100:.1f}%)\n"
                f"• TP1 at `{level.get('take_profit_1', 0):,.0f}` (+{((level.get('take_profit_1', 0) - entry_price)/entry_price)*100:.1f}%)\n"
                f"• TP2 at `{level.get('take_profit_2', 0):,.0f}` (+{((level.get('take_profit_2', 0) - entry_price)/entry_price)*100:.1f}%)"
                )

                await self._send_notification({
                    'type': f'DROP_{threshold}PCT',
                    'level': level,
                    'price': current_price,
                    'message': message
                })

                logger.warning(
                    f"📉 Drop alert {threshold}% for {level['pair']}: "
                    f"Entry={entry_price:,.0f}, Current={current_price:,.0f}, Drop=-{drop_pct:.1f}%"
                )

    async def _execute_auto_sell(self, level, current_price, hit_type):
        """Execute auto-sell when SL/TP is hit with partial take profit support"""
        try:
            from api.indodax_api import IndodaxAPI

            trade_id = level['trade_id']
            pair = level['pair']
            full_amount = level.get('amount', 0)

            if not full_amount:
                trade = self.db.get_trade(trade_id)
                if trade:
                    trade_dict = dict(trade) if hasattr(trade, 'keys') else trade
                    full_amount = trade_dict.get('amount', 0)
                else:
                    logger.error(f"Trade {trade_id} not found in database")
                    return

            if full_amount <= 0:
                logger.error(f"Invalid amount for auto-sell: {full_amount}")
                return

            # Calculate sell amount based on hit type
            if hit_type == 'PARTIAL_TP_1':
                amount = full_amount * 0.5  # 50% at TP1
            elif hit_type == 'TAKE_PROFIT':
                amount = full_amount * 0.5  # Remaining 50% at TP2
            else:
                amount = full_amount  # 100% for SL or trailing stop

            # Fetch fresh price for execution
            indodax = IndodaxAPI()
            fresh_ticker = indodax.get_ticker(pair)
            sell_price = fresh_ticker['bid'] if fresh_ticker else current_price

            logger.info(f"🤖 Auto-selling {pair}: {amount} (@{sell_price:,.0f}) ({hit_type})")

            # Execute sell order
            result = indodax.create_order(pair, 'sell', sell_price, amount)

            if result and result.get('success') == 1:
                order_id = result.get('return', {}).get('order_id', 'N/A')

                # Update trade in database
                self.db.close_trade(
                    trade_id=trade_id,
                    sell_price=sell_price,
                    sell_amount=amount,
                    order_id=order_id,
                    reason=hit_type
                )

                # For partial TP, keep monitoring remaining 50%
                if hit_type == 'PARTIAL_TP_1':
                    level['amount'] = full_amount * 0.5  # Update remaining amount
                    level['stop_loss'] = level.get('take_profit_1', level['entry_price'])  # Move SL to TP1
                    logger.info(f"✅ Partial TP1 executed: {pair} Trade #{trade_id}, remaining 50% continues")
                else:
                    # Full exit - remove from monitoring
                    self.remove_price_level(level['user_id'], trade_id)
                    logger.info(f"✅ Auto-sell executed: {pair} Trade #{trade_id} @ {sell_price:,.0f}")
            else:
                logger.error(f"❌ Auto-sell failed: {result}")

                # Unmark triggered so it can retry
                level['triggered'] = False

        except Exception as e:
            logger.error(f"❌ Auto-sell execution error: {e}")
            # Unmark triggered so it can retry
            if 'level' in dir():
                level['triggered'] = False
    
    async def _send_notification(self, trigger):
        """Send SL/TP notification to user"""
        if not self.bot_app:
            logger.warning("⚠️ Bot app not available, skipping notification")
            return
        
        level = trigger['level']
        user_id = level['user_id']
        
        try:
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=trigger['message'],
                parse_mode='Markdown'
            )
            logger.info(f"📱 Sent {trigger['type']} notification to user {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")
    
    def get_monitored_positions(self, user_id=None):
        """Get all monitored positions"""
        if user_id:
            return [v for k, v in self.price_levels.items() if v['user_id'] == user_id]
        return list(self.price_levels.values())

    def get_summary(self, user_id):
        """Get summary of monitored positions for user"""
        positions = self.get_monitored_positions(user_id)

        if not positions:
            return "📭 No active positions being monitored"

        text = f"📊 **Monitored Positions ({len(positions)})**\n\n"

        for pos in positions:
            sl_pct = ((pos['entry_price'] - pos['stop_loss']) / pos['entry_price']) * 100
            tp1_pct = ((pos.get('take_profit_1', 0) - pos['entry_price']) / pos['entry_price']) * 100
            tp2_pct = ((pos.get('take_profit_2', 0) - pos['entry_price']) / pos['entry_price']) * 100

            text += f"🔹 **{pos['pair']}**\n"
            text += f"• Entry: `{pos['entry_price']:,.0f}` IDR\n"
            text += f"• 🛑 Stop Loss: `{pos['stop_loss']:,.0f}` IDR (-{sl_pct:.1f}%)\n"
            text += f"• 🎯 TP1: `{pos.get('take_profit_1', 0):,.0f}` IDR (+{tp1_pct:.1f}%)\n"
            text += f"• 🎯 TP2: `{pos.get('take_profit_2', 0):,.0f}` IDR (+{tp2_pct:.1f}%)\n\n"

        return text

    def clear_all_levels(self, user_id=None):
        """
        🚨 HEDGE FUND: Clear all monitored price levels (used by emergency stop)
        """
        if user_id:
            keys_to_remove = [k for k, v in self.price_levels.items() if v['user_id'] == user_id]
            for k in keys_to_remove:
                del self.price_levels[k]
                self.notified_drops.pop(k, None)
                self.trailing_stops.pop(k, None)
            logger.info(f"🛑 Cleared {len(keys_to_remove)} price levels for user {user_id}")
        else:
            count = len(self.price_levels)
            self.price_levels.clear()
            self.notified_drops.clear()
            self.trailing_stops.clear()
            logger.info(f"🛑 Cleared ALL {count} price levels (emergency stop)")
