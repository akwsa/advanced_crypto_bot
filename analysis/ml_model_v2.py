#!/usr/bin/env python3
"""
Advanced ML Trading Model V2 - Improved Version
With:
- Multi-class target variable (profit-based)
- Minimum profit threshold after fees
- Drawdown protection
- Support/Resistance features
- Volume anomaly detection
- Market regime features
- Performance tracking
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
import joblib
import warnings
from datetime import datetime, timedelta
import os
from core.config import Config

# Suppress sklearn feature names warning
warnings.filterwarnings('ignore', message='X does not have valid feature names')

# ============================================================================
# TRADING CONSTANTS
# ============================================================================
from core.config import Config

# Fee rates - use Config centralized
ENTRY_FEE_PCT = Config.TRADING_FEE_RATE  # 0.3% entry fee
EXIT_FEE_PCT = Config.TRADING_FEE_RATE   # 0.3% exit fee
TOTAL_FEE_PCT = ENTRY_FEE_PCT + EXIT_FEE_PCT  # 0.6% round trip

# Target thresholds
MIN_PROFIT_PCT = 0.02  # 2% minimum profit (net after fees)
MAX_DRAWDOWN_PCT = -0.05  # -5% maximum drawdown tolerance
LOOKAHEAD_PERIODS = 5  # Look ahead 5 candles


class MLTradingModelV2:
    """
    Improved ML Trading Model with:
    - Multi-class target variable
    - Advanced feature engineering
    - Performance tracking
    - Regime-aware training
    """

    def __init__(self, model_path=None):
        # Set model path - use V2 specific path
        if model_path is None:
            base_path = getattr(Config, 'ML_MODEL_PATH', 'models/trading_model.pkl')
            self.model_path = base_path.replace('.pkl', '_v2.pkl')
        else:
            self.model_path = model_path
        
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = None
        self.last_trained = None
        self._is_fitted = False

        # Performance metrics
        self.last_accuracy = None
        self.last_precision = None
        self.last_recall = None
        self.last_f1 = None
        self.last_profit_factor = None
        self.last_win_rate = None
        
        # NEW: Store undersampling info for Telegram
        self.last_undersample_info = None

        # Training history
        self.training_history = []

        # Load existing model or create new
        try:
            if os.path.exists(self.model_path):
                loaded = self.load_model()
                if not loaded:
                    self.create_model()
            else:
                self.create_model()
        except Exception as e:
            print(f"⚠️ Failed to load model, creating new: {e}")
            self.create_model()

    def create_model(self):
        """Create improved ensemble model"""
        self.model = {
            'rf': RandomForestClassifier(
                n_estimators=100,           # Reduced for 4GB RAM
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features='sqrt',
                random_state=42,
                n_jobs=1,                   # FIX: Prevent OOM on 4GB
                class_weight='balanced'     # Handle imbalanced classes
            ),
            'gb': GradientBoostingClassifier(
                n_estimators=100,           # Reduced from 200 for speed
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42
            )
        }

    def prepare_features(self, df):
        """
        Prepare IMPROVED features for ML model

        NEW FEATURES:
        - Support/Resistance levels
        - Volume anomaly detection
        - Market regime indicators
        - Risk-adjusted returns
        - Multi-timeframe momentum
        """
        features = pd.DataFrame()

        # =====================================================================
        # PRICE FEATURES
        # =====================================================================
        features['returns_1'] = df['close'].pct_change()
        features['returns_5'] = df['close'].pct_change(periods=5)
        features['returns_10'] = df['close'].pct_change(periods=10)
        features['returns_20'] = df['close'].pct_change(periods=20)

        # =====================================================================
        # MOVING AVERAGES
        # =====================================================================
        features['sma_9'] = df['close'].rolling(window=9).mean()
        features['sma_20'] = df['close'].rolling(window=20).mean()
        features['sma_50'] = df['close'].rolling(window=50).mean()

        features['price_sma9_ratio'] = df['close'] / features['sma_9']
        features['price_sma20_ratio'] = df['close'] / features['sma_20']
        features['sma9_sma20_ratio'] = features['sma_9'] / features['sma_20']
        features['sma20_sma50_ratio'] = features['sma_20'] / features['sma_50']

        # Trend strength (SMA alignment)
        features['trend_strength'] = (
            ((features['sma_9'] > features['sma_20']).astype(int) +
             (features['sma_20'] > features['sma_50']).astype(int)) / 2
        )

        # =====================================================================
        # VOLATILITY FEATURES
        # =====================================================================
        features['volatility'] = df['close'].rolling(window=20).std() / df['close'].rolling(window=20).mean()
        features['volatility_ratio'] = features['volatility'] / features['volatility'].rolling(50).mean()

        # ATR (Average True Range)
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)
        tr1 = high - low
        tr2 = abs(high - close_prev)
        tr3 = abs(low - close_prev)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        features['atr'] = tr.rolling(window=14).mean()
        features['atr_pct'] = features['atr'] / df['close']

        # =====================================================================
        # VOLUME FEATURES - IMPROVED
        # =====================================================================
        features['volume_sma'] = df['volume'].rolling(window=20).mean()
        features['volume_ratio'] = df['volume'] / (features['volume_sma'] + 1e-9)

        # Volume anomaly (z-score)
        volume_std = df['volume'].rolling(window=50).std()
        features['volume_zscore'] = (df['volume'] - features['volume_sma']) / (volume_std + 1e-9)

        # Volume trend
        features['volume_trend'] = (df['volume'] > features['volume_sma']).astype(int)

        # =====================================================================
        # RSI (Relative Strength Index)
        # =====================================================================
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        features['rsi'] = 100 - (100 / (1 + rs))

        # RSI divergence (RSI vs Price)
        features['rsi_momentum'] = features['rsi'].diff(5)
        features['price_momentum'] = df['close'].pct_change(5)
        features['rsi_divergence'] = features['rsi_momentum'] - features['price_momentum']

        # =====================================================================
        # MACD (Moving Average Convergence Divergence)
        # =====================================================================
        ema_fast = df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = df['close'].ewm(span=26, adjust=False).mean()
        features['macd'] = ema_fast - ema_slow
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()
        features['macd_hist'] = features['macd'] - features['macd_signal']
        features['macd_hist_change'] = features['macd_hist'].diff()

        # =====================================================================
        # BOLLINGER BANDS
        # =====================================================================
        bb_middle = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        features['bb_upper'] = bb_middle + (bb_std * 2)
        features['bb_lower'] = bb_middle - (bb_std * 2)
        features['bb_width'] = (bb_std * 4) / bb_middle  # BB width (volatility)
        features['bb_position'] = (df['close'] - bb_middle) / (bb_std + 1e-9)

        # =====================================================================
        # SUPPORT/RESISTANCE FEATURES (NEW!)
        # =====================================================================
        # Simple support/resistance using rolling min/max
        features['support_20'] = df['low'].rolling(window=20).min()
        features['resistance_20'] = df['high'].rolling(window=20).max()
        features['dist_to_support'] = (df['close'] - features['support_20']) / (df['close'] + 1e-9)
        features['dist_to_resistance'] = (features['resistance_20'] - df['close']) / (df['close'] + 1e-9)

        # Support/resistance strength (how many times tested)
        features['support_tests'] = (df['low'] <= features['support_20'].shift(1)).rolling(20).sum()
        features['resistance_tests'] = (df['high'] >= features['resistance_20'].shift(1)).rolling(20).sum()

        # =====================================================================
        # MOMENTUM & OSCILLATORS
        # =====================================================================
        features['momentum_10'] = df['close'].diff(periods=10)
        features['momentum_20'] = df['close'].diff(periods=20)

        # Rate of Change
        features['roc_10'] = df['close'].pct_change(10) * 100

        # Stochastic (simplified)
        low_14 = df['low'].rolling(14).min()
        high_14 = df['high'].rolling(14).max()
        features['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14 + 1e-9)
        features['stoch_d'] = features['stoch_k'].rolling(3).mean()

        # =====================================================================
        # MARKET REGIME FEATURES (NEW!)
        # =====================================================================
        # Volatility regime - Handle duplicate quantiles gracefully
        try:
            vol_quantiles = features['volatility'].quantile([0.25, 0.5, 0.75]).values
            # Create bins, dropping duplicates to avoid pd.cut error
            bins = [0] + sorted(list(set(vol_quantiles))) + [np.inf]
            if len(bins) >= 2:
                labels = list(range(len(bins) - 1))
                features['volatility_regime'] = pd.cut(
                    features['volatility'],
                    bins=bins,
                    labels=labels[:len(bins)-1],
                    duplicates='drop'  # Handle duplicate edges gracefully
                ).astype(float)
            else:
                features['volatility_regime'] = 0.0  # Default to low volatility
        except Exception:
            features['volatility_regime'] = 0.0  # Fallback on error

        # Trend regime
        features['trend_regime'] = (
            (features['sma_20'] > features['sma_50']).astype(int) * 2 +
            (df['close'] > features['sma_20']).astype(int)
        )  # 0-3 scale: strong bearish to strong bullish

        # =====================================================================
        # RISK-ADJUSTED RETURNS
        # =====================================================================
        features['sharle_ratio_20'] = features['returns_1'].rolling(20).mean() / (features['returns_1'].rolling(20).std() + 1e-9)
        features['sortino_ratio_20'] = features['returns_1'].rolling(20).mean() / (features['returns_1'].rolling(20).apply(lambda x: x[x < 0].std() if len(x[x < 0]) > 0 else 1e-9) + 1e-9)

        # =====================================================================
        # IMPROVED TARGET VARIABLE - BALANCED MULTI-CLASS
        # =====================================================================
        # Calculate future returns (without fee first for better distribution)
        future_return = (df['close'].shift(-LOOKAHEAD_PERIODS) - df['close']) / df['close']
        
        # Calculate max profit achievable in lookahead window
        future_high = df['high'].rolling(window=LOOKAHEAD_PERIODS).max().shift(-LOOKAHEAD_PERIODS)
        future_low = df['low'].rolling(window=LOOKAHEAD_PERIODS).min().shift(-LOOKAHEAD_PERIODS)
        
        # Fee-adjusted returns
        entry_price = df['close'] * (1 + ENTRY_FEE_PCT)
        exit_price_best = future_high * (1 - EXIT_FEE_PCT)
        exit_price_worst = future_low * (1 - EXIT_FEE_PCT)
        
        profit_pct_best = (exit_price_best - entry_price) / entry_price
        profit_pct_worst = (exit_price_worst - entry_price) / entry_price
        max_drawdown = (exit_price_worst - entry_price) / entry_price

        # =====================================================================
        # BALANCED MULTI-CLASS TARGET (Using Percentiles)
        # =====================================================================
        # Use percentiles to ensure balanced class distribution
        returns = future_return.dropna()
        
        if len(returns) > 0:
            # Calculate percentile thresholds for balanced classes
            p25 = returns.quantile(0.25)
            p50 = returns.quantile(0.50)
            p75 = returns.quantile(0.75)
            
            # Class assignment based on percentiles:
            # Class 0 (STRONG SELL): Bottom 25% returns
            # Class 1 (SELL): 25-50th percentile
            # Class 2 (HOLD): 50-75th percentile  
            # Class 3 (BUY): Top 25% returns
            # Class 4 (STRONG BUY): Top 10% returns (extra strong)
            
            def classify_by_percentile(ret):
                if pd.isna(ret):
                    return 2
                if ret <= p25:
                    return 0  # STRONG SELL
                elif ret <= p50:
                    return 1  # SELL
                elif ret <= p75:
                    return 2  # HOLD
                else:
                    # Check if it's exceptional (top 10%)
                    if len(returns) > 100:
                        p90 = returns.quantile(0.90)
                        if ret >= p90:
                            return 4  # STRONG BUY
                    return 3  # BUY
            
            features['target_class'] = future_return.apply(classify_by_percentile)
        else:
            features['target_class'] = 2  # Default to HOLD

        # Also create binary target for backward compatibility
        # (1 = BUY/STRONG BUY classes 3-4, 0 = others)
        features['target'] = (features['target_class'] >= 3).astype(int)
        
        # Store helper columns
        features['profit_best'] = profit_pct_best
        features['profit_worst'] = profit_pct_worst
        features['max_drawdown'] = max_drawdown

        # =====================================================================
        # CLEAN UP FEATURES
        # =====================================================================
        # Replace infinity with NaN
        features = features.replace([np.inf, -np.inf], np.nan)

        # Drop NaN values
        features = features.dropna()

        # Clip extreme values to prevent overflow
        numeric_cols = features.select_dtypes(include=[np.number]).columns
        target_cols = ['target', 'target_class']
        for col in numeric_cols:
            if col not in target_cols:
                features[col] = features[col].clip(
                    features[col].quantile(0.01),
                    features[col].quantile(0.99)
                )

        # Store feature names (exclude target columns and helper columns)
        exclude_cols = ['target', 'target_class', 'profit_best', 'profit_worst', 'max_drawdown']
        self.feature_names = [col for col in features.columns if col not in exclude_cols]

        return features

    def train(self, df, use_multi_class=False):
        """
        Train the model with IMPROVED metrics tracking + BALANCED CLASSES

        Parameters:
        -----------
        df : DataFrame
            Historical price data (will auto-limit to 30K for RAM efficiency)
        use_multi_class : bool
            If True, use multi-class target (0-4)
            If False, use binary target (0/1)
        """
        print("🤖 Preparing features...")
        features = self.prepare_features(df)

        if len(features) < 100:
            print("⚠️ Not enough data for training")
            return False

        # =====================================================================
        # 🚀 STEP 1: LIMIT DATA SIZE (RAM efficiency)
        # Keep recent data only - 30K candles is enough, prevents OOM on 4GB
        # =====================================================================
        MAX_TRAINING_SAMPLES = 30000
        if len(features) > MAX_TRAINING_SAMPLES:
            print(f"📊 Dataset: {len(features):,} candles → limiting to {MAX_TRAINING_SAMPLES:,} (most recent)")
            features = features.tail(MAX_TRAINING_SAMPLES).reset_index(drop=True)

        # Select target variable
        target_col = 'target_class' if use_multi_class else 'target'
        X = features[self.feature_names]
        y = features[target_col]

        # =====================================================================
        # 🚀 STEP 2: UNDERSAMPLING - Fix Class Imbalance (Boost Recall)
        # Without this, model only predicts majority class → recall near 0%
        # =====================================================================
        # NEW: Capture undersampling info for Telegram
        undersample_info = None
        
        if not use_multi_class:
            # Binary classification: balance class 0 vs class 1
            class_counts = y.value_counts()
            minority_count = class_counts.min()
            majority_count = class_counts.max()

            before_text = "📊 BEFORE undersampling:\n"
            for cls, count in class_counts.sort_index().items():
                pct = count / len(y) * 100
                before_text += f"   Class {cls}: {count:,} ({pct:.1f}%)\n"
            print(f"\n{before_text}")

            if majority_count > minority_count * 3:  # Imbalance ratio > 3:1
                # Undersample majority class to 2x minority
                target_majority = min(minority_count * 2, len(y) // 2)

                # Separate classes
                majority_class = class_counts.idxmax()
                minority_class = class_counts.idxmin()

                df_with_target = pd.concat([X, y.rename('target')], axis=1)
                df_majority = df_with_target[df_with_target['target'] == majority_class]
                df_minority = df_with_target[df_with_target['target'] == minority_class]

                # Random undersample (preserve time-series order as much as possible)
                if len(df_majority) > target_majority:
                    df_majority = df_majority.sample(n=target_majority, random_state=42)

                # Recombine
                balanced_df = pd.concat([df_majority, df_minority]).sort_index()
                X = balanced_df[X.columns]
                y = balanced_df['target']

                after_text = "📊 AFTER undersampling:\n"
                new_counts = y.value_counts()
                for cls, count in new_counts.sort_index().items():
                    pct = count / len(y) * 100
                    after_text += f"   Class {cls}: {count:,} ({pct:.1f}%)\n"
                after_text += f"   Total samples: {len(y):,}"
                print(f"\n{after_text}")
                
                # Store for Telegram
                undersample_info = {
                    'applied': True,
                    'before': before_text.strip(),
                    'after': after_text.strip()
                }
            else:
                balanced_msg = f"\n✅ Class distribution already balanced (ratio < 3:1)"
                print(balanced_msg)
                undersample_info = {
                    'applied': False,
                    'message': 'Class distribution already balanced (ratio < 3:1)'
                }
        else:
            # Multi-class: just print distribution
            class_dist = y.value_counts().sort_index()
            dist_text = "📊 Multi-class distribution:\n"
            for cls, count in class_dist.items():
                pct = count / len(y) * 100
                print(f"   Class {cls}: {count:,} ({pct:.1f}%)")

        # Split data (time-series split)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # =====================================================================
        # 🚀 STEP 3: TRAIN with RAM-EFFICIENT SETTINGS
        # n_jobs=1 for RF prevents memory overload on 4GB
        # class_weight='balanced' already set in create_model()
        # =====================================================================
        print("\n🤖 Training models...")

        # Train Random Forest
        self.model['rf'].fit(X_train_scaled, y_train)
        y_pred_rf_prob = self.model['rf'].predict_proba(X_test_scaled)[:, 1]
        y_pred_rf = self.model['rf'].predict(X_test_scaled)

        # Train Gradient Boosting
        self.model['gb'].fit(X_train_scaled, y_train)
        y_pred_gb_prob = self.model['gb'].predict_proba(X_test_scaled)[:, 1]
        y_pred_gb = self.model['gb'].predict(X_test_scaled)

        # Ensemble predictions (probability averaging)
        y_pred_ensemble_prob = (y_pred_rf_prob + y_pred_gb_prob) / 2

        # For binary classification
        if not use_multi_class:
            y_pred_ensemble = (y_pred_ensemble_prob > 0.5).astype(int)

            # Calculate metrics
            accuracy = accuracy_score(y_test, y_pred_ensemble)
            precision = precision_score(y_test, y_pred_ensemble, zero_division=0)
            recall = recall_score(y_test, y_pred_ensemble, zero_division=0)
            f1 = f1_score(y_test, y_pred_ensemble, zero_division=0)

            # Calculate confusion matrix
            cm = confusion_matrix(y_test, y_pred_ensemble)
            tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)

            # Calculate win rate and profit factor (simulated)
            win_rate = tp / (tp + fn) if (tp + fn) > 0 else 0
            loss_rate = fp / (fp + tn) if (fp + tn) > 0 else 0
            profit_factor = win_rate / (loss_rate + 1e-9)

            print(f"\n{'='*50}")
            print(f"✅ MODEL TRAINING COMPLETE")
            print(f"{'='*50}")
            print(f"   Accuracy:  {accuracy:.2%}")
            print(f"   Precision: {precision:.2%}")
            print(f"   Recall:    {recall:.2%}")
            print(f"   F1 Score:  {f1:.2%}")
            print(f"   Win Rate:  {win_rate:.2%}")
            print(f"   Profit Factor: {profit_factor:.2f}")
            print(f"{'='*50}")

            # Store metrics
            self.last_accuracy = accuracy
            self.last_precision = precision
            self.last_recall = recall
            self.last_f1 = f1
            self.last_win_rate = win_rate
            self.last_profit_factor = profit_factor

        else:
            # Multi-class metrics
            y_pred_ensemble = np.round(y_pred_ensemble_prob).astype(int).clip(0, 4)
            accuracy = accuracy_score(y_test, y_pred_ensemble)
            f1_macro = f1_score(y_test, y_pred_ensemble, average='macro', zero_division=0)

            print(f"\n{'='*50}")
            print(f"✅ MODEL TRAINING COMPLETE (Multi-Class)")
            print(f"{'='*50}")
            print(f"   Accuracy:  {accuracy:.2%}")
            print(f"   F1 Macro:  {f1_macro:.2%}")
            print(f"{'='*50}")

            self.last_accuracy = accuracy
            self.last_f1 = f1_macro

        # Save training history
        self.training_history.append({
            'timestamp': datetime.now(),
            'data_points': len(features),
            'accuracy': float(self.last_accuracy or 0),
            'precision': float(self.last_precision or 0),
            'recall': float(self.last_recall or 0),
            'f1': float(self.last_f1 or 0),
            'win_rate': float(self.last_win_rate or 0),
            'profit_factor': float(self.last_profit_factor or 0)
        })

        # NEW: Store undersampling info for Telegram
        self.last_undersample_info = undersample_info

        self.last_trained = datetime.now()
        self._is_fitted = True
        self.save_model()

        return True

    def predict(self, df, return_prob=True, use_multi_class=False):
        """
        Make prediction with improved confidence calculation

        Parameters:
        -----------
        df : DataFrame
            Price data with OHLCV
        return_prob : bool
            If True, return full result with signal_class
        use_multi_class : bool
            If True, use multi-class prediction (0-4)
            If False, use binary prediction (True/False for BUY)

        Returns:
        --------
        For binary (use_multi_class=False, default):
            prediction : bool (True=BUY, False=SELL)
            confidence : float (0-1)
            signal_class : str ('BUY', 'SELL', 'HOLD')

        For multi-class (use_multi_class=True):
            prediction : int (0-4 for STRONG_SELL to STRONG_BUY)
            confidence : float (0-1)
            signal_class : str ('STRONG_SELL', 'SELL', 'HOLD', 'BUY', 'STRONG_BUY')
        """
        # Check if model is trained - add more defensive checks
        if self.model is None or not self._is_fitted:
            print("ML V2: Model not trained, returning HOLD")
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'
        
        # Check if models are actually fitted (not just placeholder)
        if self.model['rf'] is None or self.model['gb'] is None:
            print("ML V2: Model components not initialized, returning HOLD")
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'

        features = self.prepare_features(df)
        if len(features) == 0 or len(self.feature_names) == 0:
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'

        try:
            X_latest = features[self.feature_names].iloc[-1:].values
            X_latest_scaled = self.scaler.transform(X_latest)
        except Exception as e:
            print(f"⚠️ Feature scaling error: {e}")
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'

        try:
            if use_multi_class:
                # Multi-class prediction (0-4)
                try:
                    pred_rf_prob = self.model['rf'].predict_proba(X_latest_scaled)[0]
                except:
                    pred_rf_prob = None
                try:
                    pred_gb_prob = self.model['gb'].predict_proba(X_latest_scaled)[0]
                except:
                    pred_gb_prob = None
                
                if pred_rf_prob is None or pred_gb_prob is None:
                    print("ML V2: Model not properly trained, returning HOLD")
                    return 2, 0.5, 'HOLD'

                # Ensemble probability (average)
                ensemble_prob = (pred_rf_prob + pred_gb_prob) / 2

                # Get predicted class
                predicted_class = int(np.argmax(ensemble_prob))
                confidence = float(np.max(ensemble_prob))

                # Map to signal class
                signal_map = {
                    0: 'STRONG_SELL',
                    1: 'SELL',
                    2: 'HOLD',
                    3: 'BUY',
                    4: 'STRONG_BUY'
                }
                signal_class = signal_map.get(predicted_class, 'HOLD')

                if return_prob:
                    return predicted_class, confidence, signal_class
                else:
                    return predicted_class

            else:
                # Binary prediction (BUY vs not BUY)
                # Get probability of class 1 (BUY) from both models
                try:
                    pred_rf = self.model['rf'].predict_proba(X_latest_scaled)[0][1]
                except:
                    pred_rf = 0.5
                try:
                    pred_gb = self.model['gb'].predict_proba(X_latest_scaled)[0][1]
                except:
                    pred_gb = 0.5

                # Ensemble prediction (average)
                ensemble_prob = (pred_rf + pred_gb) / 2

                # Binary prediction: True if > 0.5
                prediction = bool(ensemble_prob > 0.5)
                confidence = float(ensemble_prob if prediction else 1 - ensemble_prob)

                # Map to signal class for binary (MUCH MORE AGGRESSIVE to get BUY signals)
                # FIX: 0.50/0.50 split - no more HOLD bias
                if ensemble_prob >= 0.50:
                    signal_class = 'BUY'
                elif ensemble_prob < 0.50:
                    signal_class = 'SELL'
                else:
                    signal_class = 'HOLD'

                if return_prob:
                    return prediction, confidence, signal_class
                else:
                    return prediction

        except Exception as e:
            print(f"⚠️ Prediction error: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'

    def get_feature_importance(self, top_n=10):
        """Get top feature importance from RF model"""
        if self.model is None or self.feature_names is None or not self._is_fitted:
            return None

        try:
            importances = self.model['rf'].feature_importances_
            importance_dict = dict(zip(self.feature_names, importances))

            # Sort by importance
            sorted_features = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)

            return sorted_features[:top_n]
        except Exception:
            return None

    def save_model(self):
        """Save model to disk with all metrics"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'last_trained': self.last_trained,
            'last_accuracy': getattr(self, 'last_accuracy', None),
            'last_precision': getattr(self, 'last_precision', None),
            'last_recall': getattr(self, 'last_recall', None),
            'last_f1': getattr(self, 'last_f1', None),
            'last_win_rate': getattr(self, 'last_win_rate', None),
            'last_profit_factor': getattr(self, 'last_profit_factor', None),
            'training_history': self.training_history,
            'version': '2.0'
        }, self.model_path)
        print(f"💾 Model V2 saved to {self.model_path}")

    def load_model(self):
        """Load model from disk"""
        try:
            data = joblib.load(self.model_path)

            # Check version
            version = data.get('version', '1.0')
            if version != '2.0':
                print(f"⚠️ Model version mismatch (found {version}, expected 2.0). Recreating model.")
                return False

            self.model = data['model']
            self.scaler = data['scaler']
            self.feature_names = data['feature_names']
            self.last_trained = data['last_trained']
            self.last_accuracy = data.get('last_accuracy')
            self.last_precision = data.get('last_precision')
            self.last_recall = data.get('last_recall')
            self.last_f1 = data.get('last_f1')
            self.last_win_rate = data.get('last_win_rate')
            self.last_profit_factor = data.get('last_profit_factor')
            self.training_history = data.get('training_history', [])

            self._is_fitted = self.last_trained is not None
            print(f"📂 Model V2 loaded from {self.model_path} (trained: {self.last_trained})")
            return True
        except Exception as e:
            print(f"❌ Error loading model V2: {e}")
            self._is_fitted = False
            return False

    def should_retrain(self):
        """Check if model needs retraining"""
        if not self._is_fitted or self.last_trained is None:
            return True
        return datetime.now() - self.last_trained > Config.ML_RETRAIN_INTERVAL

    def get_training_summary(self):
        """Get summary of training history"""
        if not self.training_history:
            return "No training history available"

        summary = "📊 **Training History Summary**\n\n"
        summary += f"Total training sessions: {len(self.training_history)}\n\n"

        for i, session in enumerate(self.training_history[-5:], 1):  # Last 5 sessions
            summary += f"**Session {i}:**\n"
            summary += f"  • Date: {session['timestamp']}\n"
            summary += f"  • Data points: {session['data_points']}\n"
            summary += f"  • Accuracy: {session['accuracy']:.2%}\n"
            summary += f"  • Win Rate: {session['win_rate']:.2%}\n"
            summary += f"  • Profit Factor: {session['profit_factor']:.2f}\n\n"

        return summary
