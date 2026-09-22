# Tujuan: Risk gate, drawdown, exposure, dan validasi trade.
# Caller: bot.py dan TradingEngine.
# Dependensi: Database, Config risk limits.
# Main Functions: class RiskManager.
# Side Effects: DB read/write risk/trade stats.
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from core.config import Config
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, db):
        self.db = db
    
    def check_var_cvar_gate(
        self,
        returns_pct,
        confidence: float = 0.95,
        max_var: float = -5.0,
        max_cvar: float = -8.0,
    ):
        """
        VaR/CVaR hard gate — tolak trade jika risiko historis terlalu tinggi.

        Args:
            returns_pct : List return per candle (%) dari harga historis pair
            confidence  : Confidence level (default 0.95)
            max_var     : Batas VaR maksimal (default -5.0%). Trade ditolak jika VaR < max_var.
            max_cvar    : Batas CVaR maksimal (default -8.0%). Trade ditolak jika CVaR < max_cvar.

        Returns:
            (allowed: bool, reason: str)
        """
        if not returns_pct or len(returns_pct) < 20:
            return True, "VaR gate skipped (data tidak cukup)"

        try:
            from quant.risk_metrics import RiskMetrics
            rm = RiskMetrics(mc_simulations=500, random_seed=42)
            result = rm.calculate(returns_pct[-100:], confidence=confidence)
            if result is None:
                return True, "VaR gate skipped (kalkulasi gagal)"

            if result.var_historical < max_var:
                reason = (
                    f"VaR gate: VaR95={result.var_historical:.2f}% < batas {max_var:.1f}% "
                    f"— risiko terlalu tinggi untuk entry"
                )
                logger.warning(f"🛡️ [VAR GATE] {reason}")
                return False, reason

            if result.cvar_historical < max_cvar:
                reason = (
                    f"CVaR gate: CVaR95={result.cvar_historical:.2f}% < batas {max_cvar:.1f}% "
                    f"— tail risk terlalu tinggi untuk entry"
                )
                logger.warning(f"🛡️ [CVAR GATE] {reason}")
                return False, reason

            return True, (
                f"VaR gate OK: VaR={result.var_historical:.2f}% CVaR={result.cvar_historical:.2f}%"
            )

        except Exception as e:
            logger.debug(f"[VAR GATE] Error: {e}")
            return True, "VaR gate skipped (error)"

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
                dd = (peak - balance) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
        
        if max_dd >= Config.MAX_DRAWDOWN_PCT:
            return False, f"Max drawdown reached: {max_dd:.1%}"
        
        return True, f"Current drawdown: {max_dd:.1%}"
    
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
        open_value = sum((t['total'] or 0) for t in open_trades)
        
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
        
        current_value = sum((t['total'] or 0) for t in open_trades)
        total_portfolio = balance + current_value
        
        if total_portfolio == 0:
            return {'action': 'HOLD', 'reason': 'Zero portfolio value'}
        
        # Group by pair
        pair_values = {}
        for trade in open_trades:
            pair = trade['pair']
            pair_values[pair] = pair_values.get(pair, 0) + (trade['total'] or 0)
        
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


    # =================================================================
    # QUANT: Bayesian Kelly dynamic position sizing (Phase 3,
    # docs/HERMES_HANDOVER.md). Replaces static 3%/5% sizing with
    # per-pair adaptive sizing; falls back to the legacy fixed size
    # whenever the quant engine is unavailable or has no edge.
    # =================================================================

    # Indodax minimum order (IDR). Safety clamp bawah dari blueprint Phase 3.
    KELLY_MIN_ORDER_IDR = 50000.0
    # Hard cap atas: tidak pernah alokasi lebih dari 25% balance.
    KELLY_MAX_BALANCE_FRACTION = 0.25

    def bayesian_kelly_position_size(
        self,
        pair: str,
        balance: float,
        entry_price: float,
        ml_confidence: float = 0.65,
        volatility_pct: float = 2.0,
        current_drawdown_pct: float = 0.0,
        kelly_engine: Optional["BayesianKellyEngine"] = None,
    ) -> Tuple[float, float, Dict]:
        """Dynamic position sizing via quant Bayesian Kelly + safety clamps.

        Args:
            pair: Trading pair (e.g. 'btcidr').
            balance: Available balance (IDR).
            entry_price: Entry price per unit.
            ml_confidence: ML model confidence (0..1).
            volatility_pct: Current ATR/GARCH volatility as % of price.
            current_drawdown_pct: Current drawdown from peak (0-100).
            kelly_engine: Optional injected ``BayesianKellyEngine`` instance
                (tests). ``None`` = best-effort lazy init from quant module.

        Returns:
            ``(position_value_idr, position_amount, meta)``.
            ``(0.0, 0.0, meta)`` bila sizing tidak layak (negative edge,
            input invalid). ``meta`` selalu berisi keys:
            ``method``, ``kelly_fraction``, ``position_value``, ``position_amount``,
            ``clamped`` (bool), ``reason``.
        """
        meta: Dict = {
            "method": "disabled", "kelly_fraction": 0.0,
            "position_value": 0.0, "position_amount": 0.0,
            "clamped": False, "reason": "",
        }

        # --- 0. Fail-safe: invalid input -> zero allocation
        try:
            balance = float(balance or 0)
            entry_price = float(entry_price or 0)
        except (TypeError, ValueError):
            meta["reason"] = "invalid_input"
            return 0.0, 0.0, meta
        if balance <= 0 or entry_price <= 0:
            meta["reason"] = "invalid_input"
            return 0.0, 0.0, meta

        # --- 1. Resolve engine
        engine = kelly_engine
        if engine is None:
            try:
                from quant.bayesian_kelly import BayesianKellyEngine
                engine = BayesianKellyEngine()
            except Exception as exc:
                meta["method"] = "unavailable"
                meta["reason"] = f"quant engine unavailable: {exc}"
                logger.debug(f"[KELLY SIZE] {pair}: engine unavailable: {exc}")
                return 0.0, 0.0, meta

        # --- 2. Bayesian Kelly sizing (quant module)
        try:
            result = engine.calculate_position_size(
                pair=pair,
                balance=balance,
                entry_price=entry_price,
                ml_confidence=float(ml_confidence),
                volatility_pct=float(volatility_pct),
                current_drawdown_pct=float(current_drawdown_pct),
                max_position_pct=self.KELLY_MAX_BALANCE_FRACTION,
            )
        except Exception as exc:
            meta["method"] = "engine_error"
            meta["reason"] = f"engine error: {exc}"
            logger.debug(f"[KELLY SIZE] {pair}: engine error: {exc}")
            return 0.0, 0.0, meta

        method = getattr(result, "method", "unknown")
        position_value = float(getattr(result, "position_value", 0.0) or 0.0)
        kelly_fraction = float(getattr(result, "kelly_fraction", 0.0) or 0.0)

        # --- 3. Negative edge / empty allocation -> let caller fall back
        if position_value <= 0 or method in ("negative_edge", "invalid_input"):
            meta.update({
                "method": method, "kelly_fraction": kelly_fraction,
                "position_value": 0.0, "position_amount": 0.0,
                "reason": method,
            })
            return 0.0, 0.0, meta

        clamped = False

        # --- 4. Safety clamp: minimum Indodax order (Rp 50.000)
        if 0 < position_value < self.KELLY_MIN_ORDER_IDR:
            # Jika balance sendiri di bawah minimum, jangan dipaksakan.
            if balance >= self.KELLY_MIN_ORDER_IDR:
                position_value = self.KELLY_MIN_ORDER_IDR
                clamped = True
            else:
                meta.update({
                    "method": method, "kelly_fraction": kelly_fraction,
                    "position_value": 0.0, "position_amount": 0.0,
                    "reason": "balance_below_min_order",
                })
                return 0.0, 0.0, meta

        # --- 5. Safety clamp: maksimum 25% balance
        max_value = balance * self.KELLY_MAX_BALANCE_FRACTION
        if position_value > max_value:
            position_value = max_value
            clamped = True

        position_amount = position_value / entry_price

        meta.update({
            "method": method,
            "kelly_fraction": kelly_fraction,
            "position_value": position_value,
            "position_amount": position_amount,
            "clamped": clamped,
            "reason": "ok" if not clamped else "safety_clamp_applied",
        })

        logger.info(
            f"📊 [KELLY SIZE] {pair}: value={position_value:,.0f} IDR "
            f"amount={position_amount:.8f} fraction={kelly_fraction:.2%} "
            f"method={method} clamped={clamped}"
        )
        return position_value, position_amount, meta

    def clamp_position_size(
        self,
        position_value: float,
        balance: float,
        min_order_idr: Optional[float] = None,
        max_fraction: Optional[float] = None,
    ) -> Tuple[float, bool, str]:
        """Standalone safety clamp (pure, reusable).

        Menerapkan dua guardrail blueprint Phase 3 pada nilai posisi apapun:
        minimum order exchange dan maksimum fraksi balance.

        Returns:
            ``(clamped_value, was_clamped, reason)``
        """
        try:
            position_value = float(position_value or 0)
            balance = float(balance or 0)
        except (TypeError, ValueError):
            return 0.0, False, "invalid_input"

        if position_value <= 0 or balance <= 0:
            return position_value, False, "non_positive_input"

        floor = float(min_order_idr) if min_order_idr is not None else self.KELLY_MIN_ORDER_IDR
        cap_fraction = float(max_fraction) if max_fraction is not None else self.KELLY_MAX_BALANCE_FRACTION
        cap = balance * cap_fraction

        if balance < floor:
            # Balance tidak cukup untuk order minimum - jangan naikkan.
            return position_value, False, "balance_below_min_order"

        if position_value < floor:
            return floor, True, "raised_to_min_order"

        if position_value > cap:
            return cap, True, "capped_at_max_fraction"

        return position_value, False, "within_bounds"
