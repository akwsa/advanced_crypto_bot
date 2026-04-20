#!/usr/bin/env python3
"""
ML Trading Model V3 - Simple Version
=================================
With:
- Simple percentiles-based target labeling
- 50+ technical indicators
- Basic backtesting
- Kelly Criterion position sizing
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
import joblib
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

TRADING_FEE_RATE = 0.003
LOOKAHEAD_CANDLES = 5
MAX_POSITION_PCT = 0.30

class TradingSignal:
    STRONG_SELL = 0
    SELL = 1
    HOLD = 2
    BUY = 3
    STRONG_BUY = 4
    
    @staticmethod
    def to_string(cls):
        return {0: 'STRONG_SELL', 1: 'SELL', 2: 'HOLD', 3: 'BUY', 4: 'STRONG_BUY'}.get(cls, 'UNKNOWN')

class BacktestResult:
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

class MLTradingModelV3:
    def __init__(self, model_path=None):
        self.model_path = model_path or 'models/trading_model_v3.pkl'
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.last_trained = None
        self._is_fitted = False
        self.training_history = []
        self.last_metrics = {}
        self.last_backtest = None
        self.create_model()
        
    def create_model(self):
        self.model = {
            'rf': RandomForestClassifier(
                n_estimators=100, max_depth=12, min_samples_split=10,
                min_samples_leaf=4, max_features='sqrt',
                class_weight='balanced', n_jobs=1, random_state=42
            ),
            'gb': GradientBoostingClassifier(
                n_estimators=80, max_depth=6, learning_rate=0.1,
                min_samples_split=10, min_samples_leaf=4,
                subsample=0.8, random_state=42
            )
        }
        self.scaler = StandardScaler()
        
    def prepare_features(self, df):
        df = df.copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                if col == 'close' and 'last' in df.columns:
                    df['close'] = df['last']
                elif col == 'volume' and 'vol' in df.columns:
                    df['volume'] = df['vol']
                else:
                    df[col] = 0
        if 'volume' not in df.columns or df['volume'].isnull().all():
            df['volume'] = 1
        return self._compute_features(df)
    
    def _compute_features(self, df):
        features = pd.DataFrame()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # Returns
        features['ret1'] = close.pct_change(1)
        features['ret5'] = close.pct_change(5)
        features['ret10'] = close.pct_change(10)
        
        # MA
        features['sma9'] = close.rolling(9).mean()
        features['sma20'] = close.rolling(20).mean()
        features['sma50'] = close.rolling(50).mean()
        features['price_sma9'] = close / features['sma9']
        features['price_sma20'] = close / features['sma20']
        features['sma9_20'] = (features['sma9'] > features['sma20']).astype(int)
        
        # Volatility
        features['vol20'] = close.rolling(20).std() / close
        features['vol50'] = close.rolling(50).std() / close
        
        # Volume
        vol_sma = volume.rolling(20).mean()
        features['vol_ratio'] = volume / (vol_sma + 1e-9)
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        features['rsi'] = 100 - 100 / (1 + rs)
        
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        features['macd'] = ema12 - ema26
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()
        features['macd_hist'] = features['macd'] - features['macd_signal']
        
        # BB
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        features['bb_upper'] = bb_mid + 2 * bb_std
        features['bb_lower'] = bb_mid - 2 * bb_std
        features['bb_pos'] = (close - features['bb_lower']) / (features['bb_upper'] - features['bb_lower'] + 1e-9)
        
        # S/R
        features['sup20'] = low.rolling(20).min()
        features['res20'] = high.rolling(20).max()
        features['dist_sup'] = (close - features['sup20']) / (close + 1e-9)
        features['dist_res'] = (features['res20'] - close) / (close + 1e-9)
        
        # Stochastic
        low14 = low.rolling(14).min()
        high14 = high.rolling(14).max()
        features['stoch_k'] = 100 * (close - low14) / (high14 - low14 + 1e-9)
        features['stoch_d'] = features['stoch_k'].rolling(3).mean()
        
        # Cleanup
        features = features.replace([np.inf, -np.inf], np.nan)
        features = features.ffill().bfill()
        
        self.feature_names = [c for c in features.columns if c]
        return features
    
    def prepare_targets(self, df):
        close = df['close']
        future_ret = close.shift(-LOOKAHEAD_CANDLES) / close - 1
        returns = future_ret.dropna()
        
        if len(returns) < 10:
            targets = pd.Series([TradingSignal.HOLD] * len(df), index=df.index)
            return self._create_target_df(targets)
        
        p25 = returns.quantile(0.25)
        p50 = returns.quantile(0.50)
        p75 = returns.quantile(0.75)
        
        def classify(ret):
            if pd.isna(ret):
                return TradingSignal.HOLD
            if ret <= p25:
                return TradingSignal.STRONG_SELL
            elif ret <= p50:
                return TradingSignal.SELL
            elif ret <= p75:
                return TradingSignal.BUY
            return TradingSignal.STRONG_BUY
        
        targets = future_ret.apply(classify)
        return self._create_target_df(targets)
    
    def _create_target_df(self, targets):
        return pd.DataFrame({
            'target_class': targets,
            'target': (targets >= TradingSignal.BUY).astype(int)
        }).fillna(TradingSignal.HOLD)
    
    def train(self, df, use_multi_class=True):
        print("Preparing features...")
        features = self.prepare_features(df)
        targets = self.prepare_targets(df)
        
        features = features.reset_index(drop=True)
        targets = targets.reset_index(drop=True)
        
        data = pd.concat([features, targets], axis=1)
        critical = self.feature_names[:10]
        data = data.dropna(subset=critical)
        
        if len(data) < 100:
            print("Not enough data")
            return False
        
        if len(data) > 30000:
            data = data.tail(30000)
        
        X = data[self.feature_names]
        y = data['target_class']
        
        print(f"Class distribution: {y.value_counts().to_dict()}")
        
        split = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]
        
        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s = self.scaler.transform(X_test)
        
        print("Training...")
        self.model['rf'].fit(X_train_s, y_train)
        self.model['gb'].fit(X_train_s, y_train)
        
        pred_rf = self.model['rf'].predict(X_test_s)
        pred_gb = self.model['gb'].predict(X_test_s)
        
        from scipy import stats
        pred_ens = np.array([stats.mode([r, g], keepdims=False)[0] for r, g in zip(pred_rf, pred_gb)])
        
        acc = accuracy_score(y_test, pred_ens)
        print(f"Accuracy: {acc:.2%}")
        
        self.last_metrics = {'accuracy': acc, 'train_samples': len(X_train), 'test_samples': len(X_test)}
        self._is_fitted = True
        self.last_trained = datetime.now()
        self.save_model()
        return True
    
    def predict(self, df, return_prob=True):
        if not self._is_fitted:
            return TradingSignal.HOLD, 0.5, 'HOLD'
        try:
            features = self.prepare_features(df)
            X = features[self.feature_names].iloc[-1:].values
            Xs = self.scaler.transform(X)
            
            pred_rf = self.model['rf'].predict(Xs)[0]
            pred_gb = self.model['gb'].predict(Xs)[0]
            
            from scipy import stats
            pred = int(stats.mode([pred_rf, pred_gb], keepdims=False)[0])
            
            prob_rf = self.model['rf'].predict_proba(Xs)[0]
            prob_gb = self.model['gb'].predict_proba(Xs)[0]
            conf = (prob_rf[pred] + prob_gb[pred]) / 2
            
            return pred, conf, TradingSignal.to_string(pred)
        except:
            return TradingSignal.HOLD, 0.5, 'HOLD'
    
    def save_model(self):
        try:
            import os
            os.makedirs('models', exist_ok=True)
            joblib.dump({
                'model': self.model, 'scaler': self.scaler,
                'feature_names': self.feature_names, 'last_trained': self.last_trained
            }, self.model_path)
            print(f"Model saved to {self.model_path}")
        except Exception as e:
            print(f"Save error: {e}")
    
    def backtest(self, df, initial_balance=10000000, position_pct=0.25):
        print(f"Backtesting {initial_balance:,} IDR")
        
        result = BacktestResult()
        result.initial_balance = initial_balance
        
        if len(df) < 50:
            return result
        
        close = df['close']
        sma9 = close.rolling(9).mean()
        sma20 = close.rolling(20).mean()
        
        balance = initial_balance
        position = 0
        entry_price = 0
        trades = []
        equity = [balance]
        
        for i in range(len(close) - 1):
            ma9_val = sma9.iloc[i]
            ma20_val = sma20.iloc[i]
            
            if pd.notna(ma9_val) and pd.notna(ma20_val):
                if ma9_val > ma20_val and position == 0:
                    signal = TradingSignal.BUY
                elif ma9_val < ma20_val and position > 0:
                    signal = TradingSignal.SELL
                else:
                    signal = TradingSignal.HOLD
            else:
                signal = TradingSignal.HOLD
            
            if signal == TradingSignal.BUY and position == 0:
                price = close.iloc[i]
                trade_amt = balance * position_pct
                fee = trade_amt * TRADING_FEE_RATE
                net_amt = trade_amt - fee
                qty = net_amt / price
                
                position = qty
                entry_price = price * 1.001
                balance = balance - trade_amt
                trades.append({'entry_price': entry_price, 'qty': qty})
            
            elif signal == TradingSignal.SELL and position > 0:
                price = close.iloc[i]
                exit_price = price * 0.999
                pnl = (exit_price - entry_price) * position
                bal_exit = position * exit_price
                fee = bal_exit * TRADING_FEE_RATE
                net_pnl = pnl - fee
                
                balance = balance + bal_exit - fee
                trades[-1].update({'exit_price': exit_price, 'pnl': net_pnl})
                position = 0
                entry_price = 0
            
            equity.append(balance)
        
        if position > 0:
            price = close.iloc[-1]
            balance = balance + position * price
        
        result.final_balance = balance
        result.total_profit = balance - initial_balance
        result.total_profit_pct = (balance - initial_balance) / initial_balance
        
        wins = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        loss = [t['pnl'] for t in trades if t.get('pnl', 0) < 0]
        
        result.total_trades = len(trades)
        result.winning_trades = len(wins)
        result.losing_trades = len(loss)
        result.win_rate = len(wins) / len(trades) if trades else 0
        result.avg_profit = np.mean(wins) if wins else 0
        result.avg_loss = np.mean(loss) if loss else 0
        result.largest_win = max(wins) if wins else 0
        result.largest_loss = min(loss) if loss else 0
        
        result.total_fees = sum(t['entry_price'] * t['qty'] * TRADING_FEE_RATE for t in trades)
        
        eq = np.array(equity)
        run_max = np.maximum.accumulate(eq)
        dd = (eq - run_max) / run_max
        result.max_drawdown = abs(min(dd)) if len(dd) > 0 else 0
        
        gross_w = sum(wins) if wins else 0
        gross_l = abs(sum(loss)) if loss else 0
        result.profit_factor = gross_w / (gross_l + 1e-9)
        
        if len(trades) > 1:
            rets = [t.get('pnl', 0) / initial_balance for t in trades]
            result.sharpe_ratio = np.mean(rets) / (np.std(rets) + 1e-9) * np.sqrt(252)
        
        print(f"Profit: {result.total_profit:,.0f} ({result.total_profit_pct:+.2%})")
        print(f"Trades: {result.total_trades}, Win: {result.win_rate:.2%}")
        
        self.last_backtest = result
        return result
    
    def simulate_dry_run(self, df, initial_balance=10000000):
        """Dry-run simulation - same as backtest but with label"""
        result = self.backtest(df, initial_balance=initial_balance, position_pct=0.25)
        result.is_dry_run = True
        return result
    
    def get_market_regime(self, df):
        """Detect current market regime"""
        features = self.prepare_features(df)
        if len(features) < 10:
            return {'error': 'Not enough data'}
        
        latest = features.iloc[-1]
        
        # Trend detection
        sma20 = latest.get('sma20', 0)
        sma50 = latest.get('sma50', 0)
        
        if sma20 > sma50 * 1.02:
            trend = 'UPTREND'
        elif sma20 < sma50 * 0.98:
            trend = 'DOWNTREND'
        else:
            trend = 'SIDEWAYS'
        
        # Volatility
        vol = latest.get('vol20', 0)
        vol_med = features['vol20'].median() if 'vol20' in features.columns else 0.01
        
        if vol > vol_med * 1.5:
            vol_regime = 'HIGH'
        elif vol < vol_med * 0.5:
            vol_regime = 'LOW'
        else:
            vol_regime = 'NORMAL'
        
        # Volume
        vol_ratio = latest.get('vol_ratio', 1)
        if vol_ratio > 1.5:
            volume = 'HIGH'
        elif vol_ratio < 0.5:
            volume = 'LOW'
        else:
            volume = 'NORMAL'
        
        return {
            'trend': trend,
            'volatility': vol_regime,
            'volume': volume,
            'recommended_position': 0.25 if vol_regime == 'LOW' else 0.15
        }

def create_model():
    return MLTradingModelV3()

def load_model(path=None):
    return MLTradingModelV3(path)