# Tujuan: Ringkasan portfolio, positions, dan performa aset.
# Caller: bot.py command portfolio/balance.
# Dependensi: Database, Indodax API optional.
# Main Functions: class Portfolio.
# Side Effects: DB read; optional HTTP balance/price.
from datetime import datetime
from core.config import Config
from core.utils import Utils
import logging

logger = logging.getLogger(__name__)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_value(trade, key, default=None):
    if hasattr(trade, "keys"):
        return trade[key] if key in trade.keys() else default
    if isinstance(trade, dict):
        return trade.get(key, default)
    return default


class Portfolio:
    def __init__(self, db):
        self.db = db
    
    def get_portfolio_summary(self, user_id):
        """Get complete portfolio summary"""
        balance = self.db.get_balance(user_id)
        open_trades = self.db.get_open_trades(user_id)
        
        # Calculate total value in positions
        positions_value = sum(_safe_float(_trade_value(trade, 'total')) for trade in open_trades)
        
        # Get current values
        positions = []
        total_unrealized_pnl = 0
        
        for trade in open_trades:
            # Get current price (from latest price data)
            pair = _trade_value(trade, 'pair')
            current_price_data = self.db.get_price_history(pair, limit=1)
            
            if not current_price_data.empty:
                current_price = _safe_float(current_price_data.iloc[-1]['close'])
                entry_price = _safe_float(_trade_value(trade, 'price'))
                amount = _safe_float(_trade_value(trade, 'amount'))
                invested_total = _safe_float(_trade_value(trade, 'total'))

                if current_price <= 0 or entry_price <= 0 or amount <= 0:
                    logger.warning(f"Skipping invalid open trade in portfolio summary: {trade}")
                    continue
                
                # Calculate unrealized PnL
                trade_type = _trade_value(trade, 'type', '')
                if trade_type in ['BUY', 'STRONG_BUY']:
                    unrealized_pnl = (current_price - entry_price) * amount
                else:
                    unrealized_pnl = (entry_price - current_price) * amount
                
                unrealized_pnl_pct = (unrealized_pnl / invested_total) * 100 if invested_total > 0 else 0
                total_unrealized_pnl += unrealized_pnl
                
                positions.append({
                    'pair': pair,
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'amount': amount,
                    'value': current_price * amount,
                    'unrealized_pnl': unrealized_pnl,
                    'unrealized_pnl_pct': unrealized_pnl_pct,
                    'opened_at': _trade_value(trade, 'opened_at')
                })
        
        total_value = balance + positions_value + total_unrealized_pnl
        
        summary = {
            'user_id': user_id,
            'available_balance': balance,
            'positions_value': positions_value,
            'unrealized_pnl': total_unrealized_pnl,
            'total_value': total_value,
            'positions': positions,
            'num_positions': len(positions),
            'timestamp': datetime.now()
        }
        
        return summary
    
    def get_portfolio_allocation(self, user_id):
        """Get portfolio allocation by pair"""
        summary = self.get_portfolio_summary(user_id)
        
        if summary['total_value'] == 0:
            return []
        
        allocation = []
        for position in summary['positions']:
            pct = (position['value'] / summary['total_value']) * 100
            allocation.append({
                'pair': position['pair'],
                'value': position['value'],
                'percentage': pct
            })
        
        # Add cash allocation
        cash_pct = (summary['available_balance'] / summary['total_value']) * 100
        allocation.append({
            'pair': 'CASH (IDR)',
            'value': summary['available_balance'],
            'percentage': cash_pct
        })
        
        return sorted(allocation, key=lambda x: x['percentage'], reverse=True)
    
    def get_portfolio_performance(self, user_id, days=30):
        """Get portfolio performance over time"""
        # Get all closed trades in period
        trade_history = self.db.get_trade_history(user_id, limit=1000)
        
        # Calculate cumulative PnL
        cumulative_pnl = 0
        performance_data = []
        
        for trade in reversed(trade_history):
            if trade['profit_loss']:
                cumulative_pnl += trade['profit_loss']
                performance_data.append({
                    'timestamp': trade['closed_at'],
                    'cumulative_pnl': cumulative_pnl,
                    'trade_pnl': trade['profit_loss'],
                    'pair': trade['pair']
                })
        
        return performance_data
    
    def rebalance_portfolio(self, user_id, target_allocations):
        """
        Rebalance portfolio to target allocations
        target_allocations: dict like {'BTC/IDR': 0.4, 'ETH/IDR': 0.3, 'CASH': 0.3}
        """
        summary = self.get_portfolio_summary(user_id)
        
        recommendations = []
        
        for pair, target_pct in target_allocations.items():
            if pair == 'CASH':
                continue
            
            # Find current position
            current_position = next((p for p in summary['positions'] if p['pair'] == pair), None)
            
            target_value = summary['total_value'] * target_pct
            
            if current_position:
                current_value = current_position['value']
                diff = target_value - current_value
                
                if diff > 0:
                    recommendations.append({
                        'pair': pair,
                        'action': 'BUY',
                        'amount': diff,
                        'reason': f"Increase position by {Utils.format_currency(diff)}"
                    })
                elif diff < 0:
                    recommendations.append({
                        'pair': pair,
                        'action': 'SELL',
                        'amount': abs(diff),
                        'reason': f"Reduce position by {Utils.format_currency(abs(diff))}"
                    })
            else:
                # No position, need to buy
                recommendations.append({
                    'pair': pair,
                    'action': 'BUY',
                    'amount': target_value,
                    'reason': f"Open new position with {Utils.format_currency(target_value)}"
                })
        
        return recommendations
