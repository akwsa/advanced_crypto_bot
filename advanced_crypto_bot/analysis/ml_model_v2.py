#!/usr/bin/env python3
# Tujuan: Model ML V2 multi-class dengan target labeling lebih seimbang.
# Caller: bot.py dan signal pipeline sebagai model utama/fallback.
# Dependensi: scikit-learn/joblib, pandas/numpy.
# Main Functions: class MLTradingModelV2.
# Side Effects: File I/O model; CPU-heavy training.
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
from sklearn.utils.class_weight import compute_sample_weight
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
LOOKAHEAD_PERIODS = 5  # Look ahead 5 candles


def _default_v2_model_path(base_path):
    """Return a stable V2 model path without repeatedly appending _v2."""
    base_path = str(base_path or 'models/trading_model.pkl')
    root, ext = os.path.splitext(base_path)
    ext = ext or '.pkl'
    if root.endswith('_v2'):
        return f"{root}{ext}"
    return f"{root}_v2{ext}"


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
            self.model_path = _default_v2_model_path(base_path)
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

    @staticmethod
    def _probability_for_class(model, probabilities, class_label, default=0.0):
        """Return probability for a class label, handling models trained without that class."""
        classes = list(getattr(model, 'classes_', []))
        if class_label not in classes:
            return np.full(probabilities.shape[0], default, dtype=float)
        class_idx = classes.index(class_label)
        return probabilities[:, class_idx]

    @classmethod
    def _align_probabilities(cls, model, probabilities, class_labels):
        """Align sklearn predict_proba output to the requested class label order."""
        aligned = np.zeros((probabilities.shape[0], len(class_labels)), dtype=float)
        classes = list(getattr(model, 'classes_', []))
        for out_idx, label in enumerate(class_labels):
            if label in classes:
                aligned[:, out_idx] = probabilities[:, classes.index(label)]
        row_sums = aligned.sum(axis=1, keepdims=True)
        return np.divide(
            aligned,
            row_sums,
            out=np.full_like(aligned, 1 / len(class_labels), dtype=float),
            where=row_sums > 0,
        )

    @staticmethod
    def _balanced_sample_weight(y):
        """Return per-sample weights so models without class_weight learn minority classes."""
        return compute_sample_weight(class_weight='balanced', y=y)

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
        # MOVING AVERAGES (SMA — existing, preserved for backward compat)
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
        # EMA SCALPING SUITE (NEW — Exponential Moving Averages for scalping)
        # EMA lebih responsif daripada SMA, cocok untuk scalping Indodax.
        # Period: 5 (ultra-fast), 9 (scalping), 20 (short-term support).
        # =====================================================================
        features['ema_5'] = df['close'].ewm(span=5, adjust=False).mean()
        features['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        features['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

        # Price-to-EMA ratios (posisi harga relatif terhadap EMA)
        features['price_ema9_ratio'] = df['close'] / features['ema_9']
        features['price_ema20_ratio'] = df['close'] / features['ema_20']

        # EMA crossover signal (EMA9 × EMA20) — strategi crossover paling populer
        # +1 = bullish crossover (EMA9 memotong ke atas EMA20)
        # -1 = bearish crossover (EMA9 memotong ke bawah EMA20)
        #  0 = no crossover
        ema9_above_ema20 = features['ema_9'] > features['ema_20']
        ema9_above_ema20_prev = ema9_above_ema20.shift(1)
        features['ema9_ema20_crossover'] = 0.0
        features.loc[(ema9_above_ema20 == True) & (ema9_above_ema20_prev == False),
                'ema9_ema20_crossover'] = 1.0   # bullish cross
        features.loc[(ema9_above_ema20 == False) & (ema9_above_ema20_prev == True),
                'ema9_ema20_crossover'] = -1.0  # bearish cross

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

        # Fast RSI for scalping. Period 7 is intentionally more reactive than
        # the existing RSI-14, but remains feature-only: it does not execute or
        # relax any trading gate by itself.
        gain_7 = (delta.where(delta > 0, 0)).rolling(window=7).mean()
        loss_7 = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
        rs_7 = gain_7 / (loss_7 + 1e-9)
        features['rsi_7'] = 100 - (100 / (1 + rs_7))

        # Crypto-aggressive RSI levels. These are binary model features only;
        # no runtime order path consumes them directly.
        features['rsi_overbought_crypto'] = (features['rsi'] > 80).astype(float)
        features['rsi_oversold_crypto'] = (features['rsi'] < 20).astype(float)

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

        # Stochastic RSI (scalping oscillator). Uses RSI as the input series,
        # not price, so it can surface momentum turns earlier than standard
        # stochastic while staying feature-only for the ML model.
        rsi_min_14 = features['rsi'].rolling(14).min()
        rsi_max_14 = features['rsi'].rolling(14).max()
        features['stochrsi_k'] = 100 * (features['rsi'] - rsi_min_14) / (rsi_max_14 - rsi_min_14 + 1e-9)
        features['stochrsi_d'] = features['stochrsi_k'].rolling(3).mean()

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
        # FIX LOOKAHEAD BIAS: Percentile thresholds dulu dihitung dari seluruh
        # dataset (termasuk test set), sehingga label test set 'tahu' distribusi
        # training. Sekarang hanya simpan future_return mentah di sini —
        # percentile thresholds dihitung di train() hanya dari training portion.
        # =====================================================================
        # Future return: close[t+N] / close[t] - 1 (murni forward-looking, tidak bias)
        future_return = (df['close'].shift(-LOOKAHEAD_PERIODS) - df['close']) / df['close']

        # Calculate max profit achievable in lookahead window (untuk referensi saja,
        # TIDAK dipakai sebagai feature — exclude_cols di bawah)
        future_high = df['high'].shift(-1).rolling(window=LOOKAHEAD_PERIODS, min_periods=1).max()
        future_low  = df['low'].shift(-1).rolling(window=LOOKAHEAD_PERIODS, min_periods=1).min()

        # Fee-adjusted helper columns (reference only, excluded from features)
        entry_price = df['close'] * (1 + ENTRY_FEE_PCT)
        exit_price_best  = future_high * (1 - EXIT_FEE_PCT)
        exit_price_worst = future_low  * (1 - EXIT_FEE_PCT)

        profit_pct_best  = (exit_price_best  - entry_price) / entry_price
        profit_pct_worst = (exit_price_worst - entry_price) / entry_price
        max_drawdown     = (exit_price_worst - entry_price) / entry_price

        # Simpan future_return sebagai raw kolom — label aktual dihitung di train()
        # menggunakan percentile dari training set saja (bukan full dataset).
        features['future_return_raw'] = future_return

        # Placeholder target — akan di-overwrite oleh train() dengan thresholds
        # yang dihitung hanya dari training data (anti-lookahead).
        features['target_class'] = 2   # HOLD default
        features['target']       = 0   # non-BUY default
        
        # Store helper columns
        features['profit_best']  = profit_pct_best
        features['profit_worst'] = profit_pct_worst
        features['max_drawdown'] = max_drawdown

        # =====================================================================
        # CLEAN UP FEATURES
        # =====================================================================
        # Replace infinity with NaN
        features = features.replace([np.inf, -np.inf], np.nan)

        # Drop NaN values
        features = features.dropna()

        # Clip extreme values to prevent overflow (kecuali target dan raw return)
        numeric_cols = features.select_dtypes(include=[np.number]).columns
        no_clip_cols = ['target', 'target_class', 'future_return_raw']
        for col in numeric_cols:
            if col not in no_clip_cols:
                q01 = features[col].quantile(0.01)
                q99 = features[col].quantile(0.99)
                features[col] = features[col].clip(q01, q99)

        # Store feature names — exclude target, helpers, dan raw return
        exclude_cols = ['target', 'target_class', 'future_return_raw',
                        'profit_best', 'profit_worst', 'max_drawdown']
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

        # =====================================================================
        # FIX LOOKAHEAD BIAS: Hitung percentile thresholds HANYA dari training
        # portion (80% pertama dari data), lalu apply ke seluruh dataset.
        # Sebelumnya thresholds dihitung dari full dataset → test set 'tahu'
        # distribusi training → evaluasi model tidak realistis.
        # =====================================================================
        train_cutoff = int(len(features) * 0.8)
        train_returns = features['future_return_raw'].iloc[:train_cutoff].dropna()

        if len(train_returns) > 50:
            median = train_returns.quantile(0.50)
            # Symmetric thresholds: use min distance from median to ensure
            # BUY and SELL classes get equal opportunity (fixes BUY bias).
            dist_lower = median - train_returns.quantile(0.25)
            dist_upper = train_returns.quantile(0.75) - median
            sym_dist = min(dist_lower, dist_upper)

            sell_thr = median - sym_dist
            buy_thr = median + sym_dist

            if len(train_returns) > 100:
                dist_strong_lower = median - train_returns.quantile(0.10)
                dist_strong_upper = train_returns.quantile(0.90) - median
                sym_strong_dist = min(dist_strong_lower, dist_strong_upper)
            else:
                sym_strong_dist = sym_dist

            strong_sell_thr = median - sym_strong_dist
            strong_buy_thr = median + sym_strong_dist

            def _classify(ret):
                if pd.isna(ret): return 2
                if ret <= strong_sell_thr: return 0   # STRONG SELL
                if ret <= sell_thr:        return 1   # SELL
                if ret >= strong_buy_thr:  return 4   # STRONG BUY
                if ret >= buy_thr:         return 3   # BUY
                return 2                                # HOLD

            features['target_class'] = features['future_return_raw'].apply(_classify)
            features['target'] = (features['target_class'] >= 3).astype(int)
            print(f"✅ Symmetric thresholds from training set only (n={len(train_returns):,}): "
                  f"strong_sell={strong_sell_thr:.4f}, sell={sell_thr:.4f}, "
                  f"buy={buy_thr:.4f}, strong_buy={strong_buy_thr:.4f}")
        else:
            # Fallback: threshold absolut jika data training terlalu sedikit
            features['target_class'] = features['future_return_raw'].apply(
                lambda r: 0 if r < -0.02 else (4 if r >= 0.03 else (3 if r >= 0.015 else (1 if r < 0 else 2)))
            )
            features['target'] = (features['target_class'] >= 3).astype(int)
            print("⚠️ Insufficient training data for percentile — using absolute thresholds")

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
        train_sample_weight = self._balanced_sample_weight(y_train)
        self.model['rf'].fit(X_train_scaled, y_train, sample_weight=train_sample_weight)
        rf_probabilities = self.model['rf'].predict_proba(X_test_scaled)

        # Train Gradient Boosting
        self.model['gb'].fit(X_train_scaled, y_train, sample_weight=train_sample_weight)
        gb_probabilities = self.model['gb'].predict_proba(X_test_scaled)

        # For binary classification
        if not use_multi_class:
            # Ensemble predictions (probability averaging)
            y_pred_rf_prob = self._probability_for_class(self.model['rf'], rf_probabilities, 1, default=0.0)
            y_pred_gb_prob = self._probability_for_class(self.model['gb'], gb_probabilities, 1, default=0.0)
            y_pred_ensemble_prob = (y_pred_rf_prob + y_pred_gb_prob) / 2
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
            class_labels = [0, 1, 2, 3, 4]
            rf_aligned = self._align_probabilities(self.model['rf'], rf_probabilities, class_labels)
            gb_aligned = self._align_probabilities(self.model['gb'], gb_probabilities, class_labels)
            y_pred_ensemble_prob = (rf_aligned + gb_aligned) / 2
            y_pred_ensemble = np.argmax(y_pred_ensemble_prob, axis=1).astype(int)
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

        features = self.prepare_features(df)
        if len(features) == 0 or len(self.feature_names) == 0:
            if use_multi_class:
                return 2, 0.5, 'HOLD'
            else:
                return False, 0.5, 'HOLD'

        # Restore trained feature names (prepare_features overwrites self.feature_names)
        _trained = getattr(self, '_trained_feature_names', None)
        if _trained is not None:
            self.feature_names = _trained

        try:
            # Align features to what the model/scaler expects — fill missing with 0
            import numpy as np
            X_aligned = np.zeros((1, len(self.feature_names)))
            for i, col in enumerate(self.feature_names):
                if col in features.columns:
                    X_aligned[0, i] = features[col].iloc[-1]
            X_latest_scaled = self.scaler.transform(X_aligned)
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
                class_labels = [0, 1, 2, 3, 4]
                rf_aligned = self._align_probabilities(self.model['rf'], np.array([pred_rf_prob]), class_labels)[0]
                gb_aligned = self._align_probabilities(self.model['gb'], np.array([pred_gb_prob]), class_labels)[0]
                ensemble_prob = (rf_aligned + gb_aligned) / 2

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
                    pred_rf_prob = self.model['rf'].predict_proba(X_latest_scaled)
                    pred_rf = self._probability_for_class(self.model['rf'], pred_rf_prob, 1, default=0.5)[0]
                except:
                    pred_rf = 0.5
                try:
                    pred_gb_prob = self.model['gb'].predict_proba(X_latest_scaled)
                    pred_gb = self._probability_for_class(self.model['gb'], pred_gb_prob, 1, default=0.5)[0]
                except:
                    pred_gb = 0.5

                # Ensemble prediction (average)
                ensemble_prob = (pred_rf + pred_gb) / 2

                # FIX BUG #3: Use signal_class thresholds consistently
                # FIX BIAS: Perlebar zona HOLD ke arah SELL.
                # ensemble_prob = probabilitas BUY (0.0 = sangat SELL, 1.0 = sangat BUY)
                # Sebelum: BUY >= 0.40, SELL <= 0.35, HOLD 0.35-0.40 (terlalu sempit)
                # Sesudah: BUY >= 0.40, SELL <= 0.25, HOLD 0.25-0.40 (lebih lebar)
                # Efek: SELL hanya lolos jika model sangat yakin bearish (prob < 0.25)
                if ensemble_prob >= 0.40:
                    signal_class = 'BUY'
                    prediction = True
                    confidence = ensemble_prob
                elif ensemble_prob <= 0.25:
                    signal_class = 'SELL'
                    prediction = False
                    confidence = 1 - ensemble_prob
                else:
                    signal_class = 'HOLD'
                    prediction = None
                    confidence = 0.5

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
            self._trained_feature_names = data['feature_names']  # Preserve for inference alignment
            self.last_trained = data['last_trained']
            self.last_accuracy = data.get('last_accuracy')
            self.last_precision = data.get('last_precision')
            self.last_recall = data.get('last_recall')
            self.last_f1 = data.get('last_f1')
            self.last_win_rate = data.get('last_win_rate')
            self.last_profit_factor = data.get('last_profit_factor')
            self.training_history = data.get('training_history', [])

            self._is_fitted = self.last_trained is not None

            # Integrity guard: scaler.n_features_in_ harus selaras dengan feature_names.
            # Mismatch berarti model rusak (mis. setelah refactor prepare_features yang
            # menambah kolom tanpa retrain). Tanpa guard ini predict() akan silent fallback
            # ke (False, 0.5, 'HOLD') untuk SEMUA pair (lihat audit 2026-06-09).
            try:
                scaler_n = getattr(self.scaler, 'n_features_in_', None)
                names_n = len(self.feature_names) if self.feature_names else 0
                if scaler_n is not None and names_n and scaler_n != names_n:
                    print(
                        f"⚠️ Model V2 INTEGRITY MISMATCH: scaler expects {scaler_n} features "
                        f"but feature_names has {names_n}. Predict will fail silently to HOLD. "
                        f"Forcing _is_fitted=False — please retrain via "
                        f"scripts/retrain_ml_v2_v4_once.py."
                    )
                    self._is_fitted = False
            except Exception as guard_err:
                print(f"⚠️ Model V2 integrity check failed: {guard_err}")

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
