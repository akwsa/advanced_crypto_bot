from datetime import datetime, timedelta
from core.config import Config
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, db):
        self.db = db
    
    def check_daily_loss_limit(self, user_id):
        """Check if daily loss limit reached"""
        today = datetime.now().date()
        performance = self.db.get_performance(user_id, days=1)
        
        if performance:
            total_pnl = sum(p['total_profit_loss'] for p in performance)
            balance = self.db.get_balance(user_id)
            loss_pct = abs(total_pnl) / balance * 100 if balance > 0 else 0
            
            if loss_pct >= Config.MAX_DAILY_LOSS_PCT:
                return False, f"Daily loss limit reached: {loss_pct:.2f}%"
        
        return True, "Within daily loss limit"
    
    def check_drawdown(self, user_id):
        """Check maximum drawdown"""
        # Get all closed trades
        trade_history = self.db.get_trade_history(user_id, limit=100)
        
        if not trade_history:
            return True, "No trade history"
        
        # Calculate running balance
        balance = Config.INITIAL_BALANCE
        peak = balance
        max_dd = 0
        
        for trade in trade_history:
            if trade['profit_loss']:
                balance += trade['profit_loss']
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
        
        if max_dd >= Config.MAX_DRAWDOWN_PCT:
            return False, f"Max drawdown reached: {max_dd:.2f}%"
        
        return True, f"Current drawdown: {max_dd:.2f}%"
    
    def calculate_position_risk(self, position_value, portfolio_value):
        """Calculate position risk percentage"""
        if portfolio_value == 0:
            return 0
        return (position_value / portfolio_value) * 100
    
    def get_risk_metrics(self, user_id):
        """Get comprehensive risk metrics"""
        balance = self.db.get_balance(user_id)
        open_trades = self.db.get_open_trades(user_id)
        trade_history = self.db.get_trade_history(user_id, limit=50)
        
        # Calculate metrics
        total_trades = len(trade_history)
        winning_trades = len([t for t in trade_history if t['profit_loss'] and t['profit_loss'] > 0])
        losing_trades = len([t for t in trade_history if t['profit_loss'] and t['profit_loss'] <= 0])
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = sum(t['profit_loss'] for t in trade_history if t['profit_loss'])
        
        # Calculate Sharpe Ratio (simplified)
        if len(trade_history) > 1:
            returns = [t['profit_loss_pct'] for t in trade_history if t['profit_loss_pct']]
            if returns:
                avg_return = sum(returns) / len(returns)
                std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                sharpe = (avg_return / std_return) if std_return > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0
        
        # Open positions value
        open_value = sum(t['total'] for t in open_trades)
        
        metrics = {
            'balance': balance,
            'open_positions': len(open_trades),
            'open_value': open_value,
            'available_balance': balance - open_value,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'sharpe_ratio': sharpe,
            'risk_per_trade': Config.MAX_POSITION_SIZE * 100
        }
        
        return metrics
    
    def calculate_correlation(self, pair1_prices, pair2_prices):
        """Calculate correlation between two price series.
        
        Args:
            pair1_prices: List or Series of prices for pair 1
            pair2_prices: List or Series of prices for pair 2
            
        Returns:
            float: Correlation coefficient (-1 to 1)
        """
        if len(pair1_prices) < 10 or len(pair2_prices) < 10:
            return 0.0
        
        try:
            returns1 = pd.Series(pair1_prices).pct_change().dropna()
            returns2 = pd.Series(pair2_prices).pct_change().dropna()
            
            if len(returns1) < 5 or len(returns2) < 5:
                return 0.0
            
            correlation = returns1.corr(returns2)
            return correlation if not pd.isna(correlation) else 0.0
        except Exception as e:
            logger.warning(f"Correlation calculation error: {e}")
            return 0.0
    
    def get_portfolio_correlation_matrix(self, price_data_dict):
        """Get correlation matrix for multiple pairs.
        
        Args:
            price_data_dict: Dict of {pair: [prices]}
            
        Returns:
            dict: {pair_pair: correlation}
        """
        correlations = {}
        pairs = list(price_data_dict.keys())
        
        for i, pair1 in enumerate(pairs):
            for pair2 in pairs[i+1:]:
                corr = self.calculate_correlation(
                    price_data_dict[pair1],
                    price_data_dict[pair2]
                )
                correlations[f"{pair1}_{pair2}"] = corr
        
        return correlations
    
    def suggest_rebalance(self, user_id, target_allocation=None):
        """Suggest portfolio rebalancing based on current positions.
        
        Args:
            user_id: User ID
            target_allocation: Dict of {pair: target_pct} (optional)
            
        Returns:
            dict: Rebalance suggestions
        """
        if target_allocation is None:
            target_allocation = {
                'btcidr': 0.40,
                'ethidr': 0.25,
                'bridr': 0.15,
                'other': 0.20
            }
        
        open_trades = self.db.get_open_trades(user_id)
        balance = self.db.get_balance(user_id)
        
        if not open_trades:
            return {'action': 'HOLD', 'reason': 'No open positions'}
        
        current_value = sum(t['total'] for t in open_trades)
        total_portfolio = balance + current_value
        
        if total_portfolio == 0:
            return {'action': 'HOLD', 'reason': 'Zero portfolio value'}
        
        # Group by pair
        pair_values = {}
        for trade in open_trades:
            pair = trade['pair']
            pair_values[pair] = pair_values.get(pair, 0) + trade['total']
        
        # Calculate current allocation
        current_allocation = {
            pair: value / total_portfolio 
            for pair, value in pair_values.items()
        }
        
        suggestions = []
        for pair, target_pct in target_allocation.items():
            current_pct = current_allocation.get(pair, 0)
            diff = target_pct - current_pct
            
            if abs(diff) > 0.05:  # 5% threshold
                action = 'BUY' if diff > 0 else 'SELL'
                suggestions.append({
                    'pair': pair,
                    'action': action,
                    'current_pct': current_pct * 100,
                    'target_pct': target_pct * 100,
                    'diff_pct': diff * 100
                })
        
        return {
            'action': 'REBALANCE' if suggestions else 'HOLD',
            'current_allocation': current_allocation,
            'target_allocation': target_allocation,
            'suggestions': suggestions,
            'total_value': total_portfolio
        }