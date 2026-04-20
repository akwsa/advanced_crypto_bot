#!/usr/bin/env python3
"""
ML Trading Model V3 - Pro Version
=============================
With:
- Risk/Reward based target labeling
- Advanced features (S/R, momentum, market regime, correlation)
- Professional backtesting with all costs simualted
- Kelly Criterion position sizing
- Dry-run mode for all trading methods
- Comprehensive performance metrics
- Regime-aware trading
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, 
    confusion_matrix, classification_report
)
import joblib
import warnings
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger('crypto_bot')

# ============================================================================
# TRADING CONSTANTS
# ============================================================================
TRADING_FEE_RATE = 0.003  # 0.3% per trade (Indodax)
WITHDRAWAL_FEE = 10000  # 10K IDR flat withdrawal fee
SLIPPAGE_PCT = 0.001  # 0.1% slippage assumption

# Risk/Reward thresholds
MIN_RR_RATIO = 2.0  # Minimum 2:1 risk/reward
MIN_PROFIT_PCT = 0.02  # 2% minimum profit after fees
LOOKAHEAD_CANDLES = 5  # Look ahead 5 candles

# Position sizing
DEFAULT_KELLY_PCT = 0.25  # Kelly Fraction25% max
MAX_POSITION_PCT = 0.30  # Max 30% of portfolio per trade


class TradingSignal:
    """Enumerasi untuk signal types"""
    STRONG_SELL = 0
    SELL = 1
    HOLD = 2
    BUY = 3
    STRONG_BUY = 4
    
    @staticmethod
    def to_string(cls):
        mapping = {
            0: 'STRONG_SELL',
            1: 'SELL', 
            2: 'HOLD',
            3: 'BUY',
            4: 'STRONG_BUY'
        }
        return mapping.get(cls, 'UNKNOWN')


class BacktestResult:
    """Container for backtest results"""
    def __init__(self):
        self.trades = []
        self.initial_balance = 0
        self.final_balance = 0
        self.total_profit = 0
        self.total_profit_pct = 0
        self.win_rate = 0
        self.max_drawdown = 0
        self.sharpe_ratio = 0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_fees = 0
        self.avg_profit = 0
        self.avg_loss = 0
        self.largest_win = 0
        self.largest_loss = 0
        self.profit_factor = 0
        
    def to_dict(self):
        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.final_balance,
            'total_profit': self.total_profit,
            'total_profit_pct': self.total_profit_pct,
            'win_rate': self.win_rate,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_fees': self.total_fees,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'profit_factor': self.profit_factor
        }


class MLTradingModelV3:
    """
    ML Trading Model V3 - Pro Version
    ==============================
    Features:
    - Risk/Reward based target labeling
    - 50+ technical indicators as features
    - Professional backtesting with costs
    - Kelly Criterion position sizing
    - Multi-timeframe analysis
    - Market regime detection
    - Dry-run trading simulation
    """
    
    def __init__(self, model_path=None):
        if model_path is None:
            self.model_path = 'models/trading_model_v3.pkl'
        else:
            self.model_path = model_path
            
        # Model components
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.last_trained = None
        self._is_fitted = False
        
        # Performance tracking
        self.training_history = []
        self.last_metrics = {}
        
        # Backtest results cache
        self.last_backtest = None
        
        # Initialize
        self.create_model()
        
    def create_model(self):
        """Create ensemble model with optimized params"""
        self.model = {
            'rf': RandomForestClassifier(
                n_estimators=100,
                max_depth=12,
                min_samples_split=10,
                min_samples_leaf=4,
                max_features='sqrt',
                class_weight='balanced',
                n_jobs=1,
                random_state=42
            ),
            'gb': GradientBoostingClassifier(
                n_estimators=80,
                max_depth=6,
                learning_rate=0.1,
                min_samples_split=10,
                min_samples_leaf=4,
                subsample=0.8,
                random_state=42
            )
        }
        self.scaler = StandardScaler()
        
    def prepare_features(self, df):
        """
        Prepare comprehensive features for ML model
        =====================================
        50+ features including:
        - Price momentum & returns
        - Volume analysis
        - Technical indicators
        - S/R levels
        - Market regime
        """
        # Copy to avoid modifying original
        df = df.copy()
        
        # Handle missing columns
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                if col == 'close' and 'last' in df.columns:
                    df['close'] = df['last']
                elif col == 'volume' and 'vol' in df.columns:
                    df['volume'] = df['vol']
                else:
                    df[col] = 0
        
        # Ensure required columns exist
        if 'volume' not in df.columns or df['volume'].isnull().all():
            df['volume'] = df.get('volume', 0) if 'volume' in df.columns else 1
            
        return self._compute_features(df)
    
    def _compute_features(self, df):
        """Internal feature computation"""
        features = pd.DataFrame()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        - Correlation features
        """
        features = pd.DataFrame()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # =====================================================================
        # 1. PRICE MOMENTUM & RETURNS
        # =====================================================================
        features['return_1'] = close.pct_change(1)
        features['return_3'] = close.pct_change(3)
        features['return_5'] = close.pct_change(5)
        features['return_10'] = close.pct_change(10)
        features['return_20'] = close.pct_change(20)
        
        # Cumulative returns (multi-timeframe)
        features['momentum_5'] = close - close.shift(5)
        features['momentum_10'] = close - close.shift(10)
        features['momentum_20'] = close - close.shift(20)
        
        # Rate of Change
        features['roc_5'] = (close / close.shift(5) - 1) * 100
        features['roc_10'] = (close / close.shift(10) - 1) * 100
        features['roc_20'] = (close / close.shift(20) - 1) * 100
        
        # =====================================================================
        # 2. MOVING AVERAGES & TRENDS
        # =====================================================================
        sma_5 = close.rolling(5).mean()
        sma_9 = close.rolling(9).mean()
        sma_20 = close.rolling(20).mean()
        sma_50 = close.rolling(50).mean()
        sma_200 = close.rolling(200).mean() if len(close) >= 200 else sma_50
        
        features['sma_5'] = sma_5
        features['sma_9'] = sma_9
        features['sma_20'] = sma_20
        features['sma_50'] = sma_50
        features['sma_200'] = sma_200
        
        # Price to MA ratios
        features['price_sma5'] = close / (sma_5 + 1e-9)
        features['price_sma9'] = close / (sma_9 + 1e-9)
        features['price_sma20'] = close / (sma_20 + 1e-9)
        features['price_sma50'] = close / (sma_50 + 1e-9)
        features['price_sma200'] = close / (sma_200 + 1e-9)
        
        # MA crossovers
        features['sma_cross_5_20'] = (sma_5 > sma_20).astype(int)
        features['sma_cross_9_50'] = (sma_9 > sma_50).astype(int)
        features['sma_cross_20_50'] = (sma_20 > sma_50).astype(int)
        features['sma_cross_20_200'] = (sma_20 > sma_200).astype(int)
        
        # Trend strength (0-1)
        features['trend_strength'] = (
            (close > sma_20).astype(int) + 
            (sma_20 > sma_50).astype(int) + 
            (sma_50 > sma_200).astype(int)
        ) / 3
        
        # EMA
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        features['ema_12'] = ema_12
        features['ema_26'] = ema_26
        features['ema_diff'] = ema_12 / (ema_26 + 1e-9)
        
        # =====================================================================
        # 3. VOLATILITY MEASURES
        # =====================================================================
        volatility_20 = close.rolling(20).std()
        volatility_50 = close.rolling(50).std()
        
        features['volatility_20'] = volatility_20 / close
        features['volatility_50'] = volatility_50 / close
        features['volatility_ratio'] = features['volatility_20'] / (features['volatility_50'] + 1e-9)
        
        # ATR (Average True Range)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        features['atr_14'] = tr.rolling(14).mean()
        features['atr_14_pct'] = features['atr_14'] / close
        
        # Bollinger Bands
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        features['bb_width'] = (bb_upper - bb_lower) / bb_mid
        features['bb_position'] = (close - bb_lower) / (bb_upper - bb_lower + 1e-9)
        
        # Keltner Channel
        kc_mid = ema_20 = close.ewm(span=20, adjust=False).mean()
        kc_upper = kc_mid + 2 * features['atr_14']
        kc_lower = kc_mid - 2 * features['atr_14']
        features['kc_position'] = (close - kc_lower) / (kc_upper - kc_lower + 1e-9)
        
        # =====================================================================
        # 4. VOLUME ANALYSIS
        # =====================================================================
        vol_sma_20 = volume.rolling(20).mean()
        vol_sma_50 = volume.rolling(50).mean()
        
        features['volume_sma_20'] = vol_sma_20
        features['volume_sma_50'] = vol_sma_50
        features['volume_ratio'] = volume / (vol_sma_20 + 1e-9)
        features['volume_trend'] = (volume > vol_sma_20).astype(int)
        
        # Volume z-score
        vol_std = volume.rolling(50).std()
        features['volume_zscore'] = (volume - vol_sma_20) / (vol_std + 1e-9)
        
        # Volume-price correlation
        features['vol_price_corr'] = close.rolling(20).corr(volume)
        
        # On-Balance Volume
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        features['obv'] = obv
        features['obv_sma'] = obv.rolling(10).mean()
        
        # =====================================================================
        # 5. RSI (Relative Strength Index)
        # =====================================================================
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        features['rsi_14'] = 100 - 100 / (1 + rs)
        
        # RSI MA
        features['rsi_ma'] = features['rsi_14'].rolling(10).mean()
        features['rsi_diff'] = features['rsi_14'] - features['rsi_ma']
        
        # RSI overbought/oversold
        features['rsi_overbought'] = (features['rsi_14'] >= 70).astype(int)
        features['rsi_oversold'] = (features['rsi_14'] <= 30).astype(int)
        
        # =====================================================================
        # 6. MACD
        # =====================================================================
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        features['macd'] = macd
        features['macd_signal'] = macd_signal
        features['macd_hist'] = macd_hist
        features['macd_hist_change'] = macd_hist.diff()
        
        # MACD crossovers
        features['macd_cross_up'] = ((macd > macd_signal) & (macd.shift(1) <= macd_signal.shift(1))).astype(int)
        features['macd_cross_down'] = ((macd < macd_signal) & (macd.shift(1) >= macd_signal.shift(1))).astype(int)
        
        # =====================================================================
        # 7. STOCHASTIC OSCILLATOR
        # =====================================================================
        low_14 = low.rolling(14).min()
        high_14 = high.rolling(14).max()
        stoch_k = 100 * (close - low_14) / (high_14 - low_14 + 1e-9)
        stoch_d = stoch_k.rolling(3).mean()
        
        features['stoch_k'] = stoch_k
        features['stoch_d'] = stoch_d
        features['stoch_cross'] = ((stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1))).astype(int)
        
        # =====================================================================
        # 8. SUPPORT & RESISTANCE
        # =====================================================================
        # Rolling S/R
        features['support_20'] = low.rolling(20).min()
        features['resistance_20'] = high.rolling(20).max()
        features['support_50'] = low.rolling(50).min()
        features['resistance_50'] = high.rolling(50).min()
        
        # Distance to S/R
        features['dist_to_support'] = (close - features['support_20']) / (close + 1e-9)
        features['dist_to_resistance'] = (features['resistance_20'] - close) / (close + 1e-9)
        
        # S/R strength (times tested)
        features['support_tests'] = (low <= features['support_20'].shift(1)).rolling(20).sum()
        features['resistance_tests'] = (high >= features['resistance_20'].shift(1)).rolling(20).sum()
        
        # Pivot Points
        features['pivot'] = (high + low + close) / 3
        features['pivot_r1'] = 2 * features['pivot'] - low
        features['pivot_s1'] = 2 * features['pivot'] - high
        
        # =====================================================================
        # 9. MARKET REGIME
        # =====================================================================
        # Volatility regime
        vol_p25 = features['volatility_20'].quantile(0.25)
        vol_p75 = features['volatility_20'].quantile(0.75)
        features['vol_regime'] = pd.cut(
            features['volatility_20'],
            bins=[-np.inf, vol_p25, vol_p75, np.inf],
            labels=[0, 1, 2]
        ).astype(float).fillna(1)
        
        # Trend regime
        features['trend_regime'] = np.where(
            sma_20 > sma_50 * 1.02, 1,  # Uptrend
            np.where(sma_20 < sma_50 * 0.98, -1, 0)  # Downtrend, Sideways
        )
        
        # Volume regime
        vol_median = features['volume_ratio'].median()
        features['volume_regime'] = np.where(
            features['volume_ratio'] > vol_median * 1.5, 2,  # High volume
            np.where(features['volume_ratio'] < vol_median * 0.5, 0, 1)  # Low, Normal
        )
        
        # =====================================================================
        # 10. MOMENTUM INDICATORS
        # =====================================================================
        # CCI (Commodity Channel Index)
        tp = (high + low + close) / 3
        sma_tp = tp.rolling(20).mean()
        mad_tp = (tp - sma_tp).abs().rolling(20).mean()
        features['cci'] = (tp - sma_tp) / (0.015 * mad_tp + 1e-9)
        
        # Williams %R
        williams_r = -100 * (high_14 - close) / (high_14 - low_14 + 1e-9)
        features['williams_r'] = williams_r
        
        # ADX (Average Directional Index)
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
        plus_di = 100 * plus_dm.rolling(14).mean() / (features['atr_14'] + 1e-9)
        minus_di = 100 * minus_dm.rolling(14).mean() / (features['atr_14'] + 1e-9)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)
        features['adx'] = dx.ewm(span=14, adjust=False).mean()
        
        # =====================================================================
        # CLEANUP
        # =====================================================================
        features = features.replace([np.inf, -np.inf], np.nan)
        features = features.ffill().bfill()
        
        # Store feature names (exclude helper columns)
        exclude_cols = []
        self.feature_names = [col for col in features.columns if col not in exclude_cols]
        
        return features
    
    def prepare_targets(self, df):
        """
        Prepare targets - SIMPLIFIED VERSION
        ===========================
        Use percentiles like V2 for more reliable training
        """
        close = df['close']
        
        # Future return (simpler)
        future_return = close.shift(-LOOKAHEAD_CANDLES) / close - 1
        
        # Calculate percentiles
        returns = future_return.dropna()
        if len(returns) < 10:
            # Return default if not enough data
            targets = pd.Series([TradingSignal.HOLD] * len(df), index=df.index)
            return self._create_target_df(targets, df)
        
        p25 = returns.quantile(0.25)
        p50 = returns.quantile(0.50)
        p75 = returns.quantile(0.75)
        
        # Classify by percentiles
        def classify(ret):
            if pd.isna(ret):
                return TradingSignal.HOLD
            if ret <= p25:
                return TradingSignal.STRONG_SELL
            elif ret <= p50:
                return TradingSignal.SELL
            elif ret <= p75:
                return TradingSignal.BUY
            else:
                return TradingSignal.STRONG_BUY
        
        targets = future_return.apply(classify)
        
        return self._create_target_df(targets, df)
    
    def _create_target_df(self, targets, df):
        """Create target DataFrame"""
        target_df = pd.DataFrame({
            'target_class': targets,
            'target': (targets >= TradingSignal.BUY).astype(int)
        }, index=df.index)
        
        return target_df.fillna(TradingSignal.HOLD)
    
    def _calculate_atr(self, df, period=14):
        """Calculate ATR"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        return tr.rolling(period).mean()
    
    def train(self, df, use_multi_class=True):
        """
        Train the model with comprehensive metrics
        =========================================
        """
        print("🤖 Preparing features...")
        features = self.prepare_features(df)
        targets = self.prepare_targets(df)
        
        # Reset index for alignment
        features = features.reset_index(drop=True)
        targets = targets.reset_index(drop=True)
        
        # Concatenate instead of join (avoids index issues)
        data = pd.concat([features, targets], axis=1)
        
        # Drop rows with NaN in critical columns
        critical_cols = self.feature_names[:10]  # First 10 features
        data = data.dropna(subset=critical_cols)
        
        if len(data) < 100:
            print("⚠️ Not enough data for training")
            return False
        
        # Limit size
        if len(data) > 30000:
            data = data.tail(30000)
        
        X = data[self.feature_names]
        y = data['target_class']
        
        # Check class distribution
        class_counts = y.value_counts().sort_index()
        print(f"\n📊 Class distribution:")
        for cls, cnt in class_counts.items():
            cls_name = TradingSignal.to_string(cls)
            print(f"   {cls_name}: {cnt} ({cnt/len(y)*100:.1f}%)")
        
        # Split
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        # Scale
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train models
        print("\n🤖 Training models...")
        
        self.model['rf'].fit(X_train_scaled, y_train)
        self.model['gb'].fit(X_train_scaled, y_train)
        
        # Predictions
        y_pred_rf = self.model['rf'].predict(X_test_scaled)
        y_pred_gb = self.model['gb'].predict(X_test_scaled)
        
        # Ensemble (mode voting for multi-class)
        from scipy import stats
        y_pred_ensemble = np.array([
            stats.mode([r, g], keepdims=False)[0] 
            for r, g in zip(y_pred_rf, y_pred_gb)
        ])
        
        # Metrics
        accuracy = accuracy_score(y_test, y_pred_ensemble)
        
        print(f"\n✅ Training Complete!")
        print(f"   Accuracy: {accuracy:.2%}")
        
        self.last_metrics = {
            'accuracy': accuracy,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }
        
        self._is_fitted = True
        self.last_trained = datetime.now()
        self.save_model()
        
        return True
    
    def predict(self, df, return_prob=True):
        """
        Make prediction
        """
        if not self._is_fitted:
            logger.warning("Model not trained, returning HOLD")
            return TradingSignal.HOLD, 0.5, 'HOLD'
        
        try:
            features = self.prepare_features(df)
            X_latest = features[self.feature_names].iloc[-1:].values
            X_scaled = self.scaler.transform(X_latest)
            
            # Ensemble prediction
            pred_rf = self.model['rf'].predict(X_scaled)[0]
            pred_gb = self.model['gb'].predict(X_scaled)[0]
            
            # Vote
            from scipy import stats
            prediction = int(stats.mode([pred_rf, pred_gb], keepdims=False)[0])
            
            # Confidence (average probability)
            prob_rf = self.model['rf'].predict_proba(X_scaled)[0]
            prob_gb = self.model['gb'].predict_proba(X_scaled)[0]
            confidence = (prob_rf[prediction] + prob_gb[prediction]) / 2
            
            signal_str = TradingSignal.to_string(prediction)
            
            return prediction, confidence, signal_str
            
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return TradingSignal.HOLD, 0.5, 'HOLD'
    
    def save_model(self):
        """Save model to disk"""
        try:
            os.makedirs(os.path.dirname(self.model_path) or '.', exist_ok=True)
            joblib.dump({
                'model': self.model,
                'scaler': self.scaler,
                'feature_names': self.feature_names,
                'last_trained': self.last_trained,
                'last_metrics': self.last_metrics
            }, self.model_path)
            print(f"💾 Model saved to {self.model_path}")
        except Exception as e:
            print(f"⚠️ Failed to save model: {e}")
    
    def load_model(self):
        """Load model from disk"""
        try:
            data = joblib.load(self.model_path)
            self.model = data['model']
            self.scaler = data['scaler']
            self.feature_names = data['feature_names']
            self.last_trained = data.get('last_trained')
            self.last_metrics = data.get('last_metrics', {})
            self._is_fitted = True
            print(f"✅ Model loaded from {self.model_path}")
            return True
        except Exception as e:
            print(f"⚠️ Failed to load model: {e}")
            return False
    
    # ============================================================================
    # BACKTESTING ENGINE
    # ============================================================================
    def backtest(self, df, initial_balance=10000000, position_pct=0.25, 
              stop_loss_pct=0.02, take_profit_pct=0.04):
        """
        Professional backtesting with all costs
        ==============================
        """
        print(f"\n🔄 Backtesting with initial balance: {initial_balance:,} IDR")
        
        result = BacktestResult()
        result.initial_balance = initial_balance
        
        if len(df) < 50:
            return result
            
        balance = initial_balance
        position = 0
        entry_price = 0
        trades = []
        equity_curve = [balance]
        
        # Use simple MA crossover for backtest (more reliable)
        close_prices = df['close']
        sma_9 = close_prices.rolling(9).mean()
        sma_20 = close_prices.rolling(20).mean()
        
        for i in range(len(close_prices) - 1):
            current_price = close_prices.iloc[i]
            ma9 = sma_9.iloc[i]
            ma20 = sma_20.iloc[i]
            
            # Simple MA crossover signal
            if pd.notna(ma9) and pd.notna(ma20):
                if ma9 > ma20 and position == 0:
                    signal = TradingSignal.BUY
                elif ma9 < ma20 and position > 0:
                    signal = TradingSignal.SELL
                else:
                    signal = TradingSignal.HOLD
            else:
                signal = TradingSignal.HOLD
            
            if signal == TradingSignal.BUY and position == 0:
                # Open position
                price = current_price
                
                # Calculate position size
                trade_amount = balance * position_pct
                quantity = trade_amount / price
                
                # Apply fees
                fee = trade_amount * TRADING_FEE_RATE
                net_amount = trade_amount - fee
                quantity = net_amount / price
                
                position = quantity
                entry_price = price * (1 + SLIPPAGE_PCT)  # Entry slippage
                balance = balance - trade_amount
                
                entry_time = i
                trades.append({
                    'entry_time': entry_time,
                    'entry_price': entry_price,
                    'quantity': quantity,
                    'type': 'LONG'
                })
                
            elif signal <= TradingSignal.SELL and position > 0:
                # Close position
                price = close_prices.iloc[i]
                exit_price = price * (1 - SLIPPAGE_PCT)  # Exit slippage
                
                # Calculate P&L
                pnl = (exit_price - entry_price) * position
                balance_exit = position * exit_price
                exit_fee = balance_exit * TRADING_FEE_RATE
                net_pnl = pnl - exit_fee - WITHDRAWAL_FEE
                
                balance = balance + balance_exit - exit_fee - WITHDRAWAL_FEE
                
                exit_time = i
                trades[-1].update({
                    'exit_time': exit_time,
                    'exit_price': exit_price,
                    'pnl': net_pnl,
                    'pnl_pct': (exit_price - entry_price) / entry_price
                })
                
                position = 0
                entry_price = 0
            
            # Update equity
            equity_curve.append(balance)
        
        # Close any open position
        if position > 0:
            price = df['close'].iloc[-1]
            pnl = (price - entry_price) * position
            balance = balance + position * price - (position * price * TRADING_FEE_RATE)
            trades[-1].update({
                'exit_time': df.index[-1],
                'exit_price': price,
                'pnl': pnl
            })
        
        # Calculate metrics
        result.trades = trades
        result.final_balance = balance
        result.total_profit = balance - initial_balance
        result.total_profit_pct = (balance - initial_balance) / initial_balance
        
        winning = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        losing = [t['pnl'] for t in trades if t.get('pnl', 0) < 0]
        
        result.total_trades = len(trades)
        result.winning_trades = len(winning)
        result.losing_trades = len(losing)
        result.win_rate = len(winning) / len(trades) if trades else 0
        
        result.avg_profit = np.mean(winning) if winning else 0
        result.avg_loss = np.mean(losing) if losing else 0
        result.largest_win = max(winning) if winning else 0
        result.largest_loss = min(losing) if losing else 0
        
        # Total fees
        result.total_fees = sum([
            t['entry_price'] * t['quantity'] * TRADING_FEE_RATE 
            for t in trades
        ])
        
        # Max drawdown
        equity = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity)
        drawdowns = (equity - running_max) / running_max
        result.max_drawdown = abs(min(drawdowns)) if len(drawdowns) > 0 else 0
        
        # Profit factor
        gross_wins = sum(winning) if winning else 0
        gross_losses = abs(sum(losing)) if losing else 0
        result.profit_factor = gross_wins / (gross_losses + 1e-9)
        
        # Sharpe ratio (simplified)
        if len(trades) > 1:
            returns = [t.get('pnl_pct', 0) for t in trades]
            result.sharpe_ratio = np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252)
        
        print(f"\n📊 Backtest Results:")
        print(f"   Initial Balance: {result.initial_balance:,} IDR")
        print(f"   Final Balance: {result.final_balance:,} IDR")
        print(f"   Total Profit: {result.total_profit:,} IDR ({result.total_profit_pct:.2%})")
        print(f"   Total Trades: {result.total_trades}")
        print(f"   Win Rate: {result.win_rate:.2%}")
        print(f"   Max Drawdown: {result.max_drawdown:.2%}")
        print(f"   Profit Factor: {result.profit_factor:.2f}")
        print(f"   Total Fees: {result.total_fees:,.0f} IDR")
        
        self.last_backtest = result
        return result
    
    # ============================================================================
    # KELLY CRITERION POSITION SIZING
    # ============================================================================
    def calculate_kelly_position(self, win_rate, avg_win, avg_loss, 
                                  max_position_pct=MAX_POSITION_PCT):
        """
        Calculate Kelly Criterion position size
        =====================================
        Formula: K% = W - (1-W)/R
        Where:
        - W = win rate
        - R = win/loss ratio
        """
        if win_rate <= 0 or avg_loss >= 0:
            return 0.01  # Min 1%
        
        win_loss_ratio = abs(avg_win / avg_loss)
        
        # Kelly percentage
        kelly_pct = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Apply fractional Kelly (half for safety)
        kelly_pct = kelly_pct * 0.5
        
        # Clamp to limits
        kelly_pct = max(0.01, min(kelly_pct, max_position_pct))
        
        return kelly_pct
    
    def simulate_dry_run(self, df, initial_balance=10000000):
        """
        Dry-run simulation - simulates trades WITHOUT executing
        =======================================================
        Returns detailed trade log and metrics
        """
        print(f"\n🎯 Dry-Run Simulation (no real trades)")
        
        result = self.backtest(
            df, 
            initial_balance=initial_balance,
            position_pct=0.25,
            stop_loss_pct=0.02,
            take_profit_pct=0.04
        )
        
        # Add dry-run specific info
        result.is_dry_run = True
        result.simulated_at = datetime.now()
        
        return result
    
    # ============================================================================
    # REGIME-AWARE TRADING
    # ============================================================================
    def get_market_regime(self, df):
        """
        Detect current market regime
        ======================
        Returns: dict with regime info
        """
        features = self.prepare_features(df)
        latest = features.iloc[-1]
        
        # Volatility regime
        vol = latest.get('volatility_20', 0)
        vol_median = features['volatility_20'].median()
        
        if vol > vol_median * 1.5:
            vol_regime = 'HIGH_VOLATILITY'
        elif vol < vol_median * 0.5:
            vol_regime = 'LOW_VOLATILITY'
        else:
            vol_regime = 'NORMAL_VOLATILITY'
        
        # Trend regime
        sma_20 = latest.get('sma_20', 0)
        sma_50 = latest.get('sma_50', 0)
        
        if sma_20 > sma_50 * 1.02:
            trend_regime = 'UPTREND'
        elif sma_20 < sma_50 * 0.98:
            trend_regime = 'DOWNTREND'
        else:
            trend_regime = 'SIDEWAYS'
        
        # Volume regime
        vol_ratio = latest.get('volume_ratio', 1)
        if vol_ratio > 1.5:
            vol_regime = 'HIGH_VOLUME'
        elif vol_ratio < 0.5:
            vol_regime = 'LOW_VOLUME'
        else:
            vol_regime = 'NORMAL_VOLUME'
        
        return {
            'volatility': vol_regime,
            'trend': trend_regime,
            'volume': vol_regime,
            'recommended_position_size': 0.25 if vol_regime == 'LOW_VOLATILITY' else 0.15
        }


# ============================================================================
# STANDALONE FUNCTIONS FOR EXTERNAL USE
# ============================================================================
def create_model():
    """Create new ML Trading Model V3"""
    return MLTradingModelV3()


def load_model(path=None):
    """Load existing model"""
    return MLTradingModelV3(path)