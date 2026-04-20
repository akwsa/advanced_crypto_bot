import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score
import joblib
import warnings
from datetime import datetime, timedelta
import os
from core.config import Config

# Suppress sklearn feature names warning
warnings.filterwarnings('ignore', message='X does not have valid feature names')

class MLTradingModel:
    def __init__(self, model_path=None):
        self.model_path = model_path or Config.ML_MODEL_PATH
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = None
        self.last_trained = None
        self._is_fitted = False  # Track whether model has been trained

        # Load existing model or create new
        if os.path.exists(self.model_path):
            loaded = self.load_model()
            if not loaded:
                self.create_model()
        else:
            self.create_model()
    
    def create_model(self):
        """Create ensemble model"""
        self.model = {
            'rf': RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42,
                n_jobs=2  # FIX: Limit to 2 cores to prevent OOM (was -1)
            ),
            'gb': GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        }
    
    def prepare_features(self, df):
        """Prepare features for ML model"""
        features = pd.DataFrame()
        
        # Price features
        features['returns_1'] = df['close'].pct_change()
        features['returns_5'] = df['close'].pct_change(periods=5)
        features['returns_10'] = df['close'].pct_change(periods=10)
        
        # Moving averages
        features['sma_9'] = df['close'].rolling(window=9).mean()
        features['sma_20'] = df['close'].rolling(window=20).mean()
        features['sma_50'] = df['close'].rolling(window=50).mean()
        
        features['price_sma9_ratio'] = df['close'] / features['sma_9']
        features['price_sma20_ratio'] = df['close'] / features['sma_20']
        features['sma9_sma20_ratio'] = features['sma_9'] / features['sma_20']
        
        # Volatility
        features['volatility'] = df['close'].rolling(window=20).std() / df['close'].rolling(window=20).mean()
        
        # Volume
        features['volume_sma'] = df['volume'].rolling(window=20).mean()
        # Avoid division by zero for volume
        features['volume_ratio'] = df['volume'] / (features['volume_sma'] + 1e-9)
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        features['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_fast = df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = df['close'].ewm(span=26, adjust=False).mean()
        features['macd'] = ema_fast - ema_slow
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()
        features['macd_hist'] = features['macd'] - features['macd_signal']
        
        # Bollinger Bands
        bb_middle = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        features['bb_upper'] = bb_middle + (bb_std * 2)
        features['bb_lower'] = bb_middle - (bb_std * 2)
        # Avoid division by zero for BB position
        features['bb_position'] = (df['close'] - bb_middle) / (bb_std + 1e-9)
        
        # Momentum
        features['momentum'] = df['close'].diff(periods=10)
        
        # ATR
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)
        tr1 = high - low
        tr2 = abs(high - close_prev)
        tr3 = abs(low - close_prev)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        features['atr'] = tr.rolling(window=14).mean()
        
        # Target: 1 if price will go up in next 5 candles, 0 otherwise
        features['target'] = (df['close'].shift(-5) > df['close']).astype(int)

        # Replace infinity with NaN
        features = features.replace([np.inf, -np.inf], np.nan)
        
        # Drop NaN values
        features = features.dropna()
        
        # Clip extreme values to prevent overflow
        numeric_cols = features.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if col != 'target':
                features[col] = features[col].clip(
                    features[col].quantile(0.01), 
                    features[col].quantile(0.99)
                )

        self.feature_names = [col for col in features.columns if col != 'target']
        
        return features
    
    def train(self, df):
        """Train the model"""
        print("🤖 Preparing features...")
        features = self.prepare_features(df)
        
        if len(features) < 100:
            print("⚠️ Not enough data for training")
            return False
        
        X = features[self.feature_names]
        y = features['target']
        
        # Split data
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        print("🤖 Training models...")
        # Train Random Forest
        self.model['rf'].fit(X_train_scaled, y_train)
        y_pred_rf = self.model['rf'].predict(X_test_scaled)
        
        # Train Gradient Boosting
        self.model['gb'].fit(X_train_scaled, y_train)
        y_pred_gb = self.model['gb'].predict(X_test_scaled)
        
        # Ensemble predictions
        y_pred_ensemble = (y_pred_rf + y_pred_gb) / 2
        y_pred_ensemble = (y_pred_ensemble > 0.5).astype(int)
        
        # Calculate metrics
        accuracy = accuracy_score(y_test, y_pred_ensemble)
        precision = precision_score(y_test, y_pred_ensemble, zero_division=0)
        recall = recall_score(y_test, y_pred_ensemble, zero_division=0)
        
        print(f"✅ Model trained!")
        print(f"   Accuracy: {accuracy:.2%}")
        print(f"   Precision: {precision:.2%}")
        print(f"   Recall: {recall:.2%}")

        # Store metrics for display
        self.last_accuracy = accuracy
        self.last_precision = precision
        self.last_recall = recall

        self.last_trained = datetime.now()
        self._is_fitted = True  # Mark model as trained
        self.save_model()

        return True
    
    def predict(self, df):
        """
        Make prediction

        Returns:
        --------
        prediction : bool or None
            True = BUY, False = SELL, None = not enough data
        confidence : float (0-1)
            Confidence score for the prediction
        signal_class : str
            'BUY', 'SELL', or 'HOLD'
        """
        # Check if model is actually trained (not just initialized)
        # TEMPORARY FIX: If model not fitted, return HOLD with moderate confidence
        # This allows TA-only signals to work
        if self.model is None or not self._is_fitted:
            logger.warning(f"ML model not trained yet (_is_fitted={self._is_fitted}) - returning HOLD")
            return None, 0.65, 'HOLD'  # Changed from 0.5 to 0.65

        # Check if we have feature names
        if self.feature_names is None or len(self.feature_names) == 0:
            return None, 0.5, 'HOLD'

        try:
            features = self.prepare_features(df)
        except Exception as e:
            print(f"⚠️ Feature preparation error: {e}")
            return None, 0.5, 'HOLD'

        if len(features) == 0:
            return None, 0.5, 'HOLD'

        try:
            X_latest = features[self.feature_names].iloc[-1:].values
            X_latest_scaled = self.scaler.transform(X_latest)
        except Exception as e:
            print(f"⚠️ Feature scaling error: {e}")
            return None, 0.5, 'HOLD'

        try:
            # Get predictions from both models
            pred_rf = self.model['rf'].predict_proba(X_latest_scaled)[0][1]
            pred_gb = self.model['gb'].predict_proba(X_latest_scaled)[0][1]

            # Ensemble prediction
            prediction = (pred_rf + pred_gb) / 2

            # Determine signal class
            if prediction > 0.7:
                signal_class = 'BUY'
            elif prediction < 0.3:
                signal_class = 'SELL'
            else:
                signal_class = 'HOLD'

            return bool(prediction > 0.5), float(prediction), signal_class

        except Exception as e:
            # Catch any unexpected errors (e.g. shape mismatch)
            print(f"⚠️ Prediction error: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            return None, 0.5, 'HOLD'
    
    def get_feature_importance(self):
        """Get feature importance from RF model"""
        if self.model is None or self.feature_names is None or not self._is_fitted:
            return None

        try:
            importances = self.model['rf'].feature_importances_
            return dict(zip(self.feature_names, importances))
        except Exception:
            return None
    
    def save_model(self):
        """Save model to disk"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'last_trained': self.last_trained,
            'last_accuracy': getattr(self, 'last_accuracy', None),
            'last_precision': getattr(self, 'last_precision', None),
            'last_recall': getattr(self, 'last_recall', None)
        }, self.model_path)
        print(f"💾 Model saved to {self.model_path}")

    def load_model(self):
        """Load model from disk. Returns True if successful."""
        try:
            data = joblib.load(self.model_path)
            self.model = data['model']
            self.scaler = data['scaler']
            self.feature_names = data['feature_names']
            self.last_trained = data['last_trained']
            # Load metrics if available
            self.last_accuracy = data.get('last_accuracy')
            self.last_precision = data.get('last_precision')
            self.last_recall = data.get('last_recall')
            # Mark as fitted if loaded successfully
            self._is_fitted = self.last_trained is not None
            print(f"📂 Model loaded from {self.model_path}")
            return True
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            self._is_fitted = False
            self.create_model()
            return False
    
    def should_retrain(self):
        """Check if model needs retraining"""
        if not self._is_fitted or self.last_trained is None:
            return True
        return datetime.now() - self.last_trained > Config.ML_RETRAIN_INTERVAL