#!/usr/bin/env python3
# Tujuan: Model ML V4 berbasis outcome signal/trade.
# Caller: bot.py startup auto-train dan signal summary.
# Dependensi: scikit-learn/joblib, pandas/numpy, signal outcomes.
# Main Functions: class MLTradingModelV4.
# Side Effects: File I/O model; CPU-heavy training.
"""
ML Trading Model V4 - Trade Outcome Based
=========================================
Model ML yang belajar dari hasil trade historis (signal outcomes),
bukan dari harga future.

Features:
- Trade-outcome labels (GOOD_BUY, BAD_BUY, GOOD_SELL, BAD_SELL, NEUTRAL)
- Per-pair model training
- Evaluation: win rate, profit factor, expectancy (bukan cuma accuracy)
- Online learning ready (incremental update dari signal baru)

Usage:
    from analysis.ml_model_v4 import MLTradingModelV4
    model = MLTradingModelV4()
    model.train_from_outcomes(outcomes)  # outcomes dari SignalOutcomeLabeler
    prediction, confidence = model.predict(features_dict)
"""

import os
import pickle
import logging
import hashlib
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight

logger = logging.getLogger("crypto_bot")

# Trade outcome classes
CLASSES = ['BAD_BUY', 'GOOD_BUY', 'NEUTRAL_BUY', 'BAD_SELL', 'GOOD_SELL', 'NEUTRAL_SELL']


@dataclass
class MLEvaluation:
    """Evaluation metrics focused on trading performance"""
    accuracy: float
    win_rate: float  # % of GOOD vs (GOOD + BAD)
    profit_factor: float  # avg profit / avg loss (absolute)
    expectancy: float  # expected return per trade
    precision_good_buy: float
    precision_bad_buy: float
    confusion_matrix: np.ndarray
    report: str


class MLTradingModelV4:
    """
    ML Model V4 - Trade Outcome Based.
    Belajar dari hasil trade historis, bukan harga future.
    """

    MODEL_PATH = "models/trading_model_v4.pkl"

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or self.MODEL_PATH
        self.rf_model = None
        self.gb_model = None
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.feature_names: List[str] = []
        self.is_fitted = False
        self.last_eval: Optional[MLEvaluation] = None
        self.last_trained: Optional[datetime] = None
        self.pair_models: Dict[str, Any] = {}  # Per-pair models
        self.last_class_distribution: Dict[str, int] = {}
        self.last_balance_info: Dict[str, Any] = {}

        # Load existing if available
        if os.path.exists(self.model_path):
            self.load_model()
        else:
            self._init_models()

    def _init_models(self):
        """Initialize fresh models"""
        self.rf_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=4,
            class_weight='balanced',
            n_jobs=1,
            random_state=42
        )
        self.gb_model = GradientBoostingClassifier(
            n_estimators=80,
            max_depth=6,
            learning_rate=0.1,
            min_samples_split=10,
            min_samples_leaf=4,
            random_state=42
        )
        self.is_fitted = False

    @staticmethod
    def _count_labels(df: pd.DataFrame) -> Dict[str, int]:
        return {str(k): int(v) for k, v in df['label'].value_counts().sort_index().items()}

    def _balance_training_frame(
        self,
        df: pd.DataFrame,
        neutral_ratio: int = 3,
        min_neutral_per_side: int = 20,
    ) -> pd.DataFrame:
        """
        Keep all GOOD/BAD labels and cap NEUTRAL labels per direction.

        Historical outcomes can be overwhelmingly NEUTRAL, which makes V4 report
        high accuracy while predicting NEUTRAL for almost every live signal.
        """
        before = self._count_labels(df)
        parts = []

        for side in ('BUY', 'SELL'):
            side_df = df[df['label'].str.endswith(f'_{side}')]
            neutral = side_df[side_df['label'].str.startswith('NEUTRAL')]
            directional = side_df[~side_df['label'].str.startswith('NEUTRAL')]

            parts.append(directional)
            if neutral.empty:
                continue

            if directional.empty:
                parts.append(neutral)
                continue

            cap = max(len(directional) * neutral_ratio, min_neutral_per_side)
            if len(neutral) > cap:
                neutral = neutral.sample(n=cap, random_state=42).sort_index()
            parts.append(neutral)

        balanced = pd.concat(parts).sort_index() if parts else df
        after = self._count_labels(balanced)
        self.last_class_distribution = after
        self.last_balance_info = {
            'applied': len(balanced) < len(df),
            'before': before,
            'after': after,
            'neutral_ratio': neutral_ratio,
            'min_neutral_per_side': min_neutral_per_side,
        }
        return balanced

    @staticmethod
    def _probability_for_encoded_class(model, probabilities: np.ndarray, encoded_label: int) -> float:
        classes = list(getattr(model, 'classes_', []))
        if encoded_label not in classes:
            return 0.0
        return float(probabilities[classes.index(encoded_label)])

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Build feature matrix dari DataFrame signal.
        Expected columns: signal_price, ml_confidence, rec_encoded, hour, dayofweek, symbol
        """
        features = pd.DataFrame()

        # Price features
        features['price_log'] = np.log1p(df['signal_price'].astype(float))

        # ML confidence (0-1)
        features['ml_confidence'] = df['ml_confidence'].astype(float).fillna(0.5)

        # Signal type (BUY=0, STRONG_BUY=1, SELL=2, STRONG_SELL=3)
        features['rec_encoded'] = df['rec_encoded'].astype(int)

        # Time features
        features['hour'] = df['hour'].astype(int)
        features['hour_sin'] = np.sin(2 * np.pi * features['hour'] / 24)
        features['hour_cos'] = np.cos(2 * np.pi * features['hour'] / 24)
        features['dayofweek'] = df['dayofweek'].astype(int)

        # Interactions
        features['conf_x_rec'] = features['ml_confidence'] * features['rec_encoded']
        features['conf_squared'] = features['ml_confidence'] ** 2

        # Symbol encoding (simplified: hash to 0-9)
        if 'symbol' in df.columns:
            features['symbol_hash'] = df['symbol'].apply(self._stable_symbol_hash)
        else:
            features['symbol_hash'] = 0

        self.feature_names = list(features.columns)
        return features

    @staticmethod
    def _stable_symbol_hash(symbol: Any) -> int:
        """Deterministic hash bucket for symbol feature."""
        text = str(symbol or "").upper()
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 10

    def train_from_outcomes(self, outcomes: List[Any], test_size: float = 0.2) -> bool:
        """
        Train model dari list SignalOutcome.

        Args:
            outcomes: List SignalOutcome dari SignalOutcomeLabeler
            test_size: Fraction untuk test set

        Returns:
            bool: True jika training sukses
        """
        if not outcomes:
            logger.warning("⚠️ No outcomes provided for training")
            return False

        # Convert ke DataFrame
        records = []
        for o in outcomes:
            records.append({
                'signal_price': o.signal_price,
                'ml_confidence': o.ml_confidence,
                'recommendation': o.recommendation,
                'rec_encoded': self._encode_rec(o.recommendation),
                'hour': o.received_at.hour,
                'dayofweek': o.received_at.weekday(),
                'symbol': o.symbol,
                'label': o.label,
            })

        df = pd.DataFrame(records)

        # Filter hanya actionable (exclude NEUTRAL untuk binary model, tapi keep untuk multi-class)
        actionable = df[df['label'].isin(CLASSES)].copy()
        if len(actionable) < 15:
            logger.warning(f"⚠️ Only {len(actionable)} actionable outcomes, need 15+")
            return False

        logger.info(f"📊 Training V4 with {len(actionable)} labeled outcomes")

        # Features & target
        X = self._build_features(actionable)
        y = actionable['label']

        # Encode labels
        self.label_encoder.fit(CLASSES)
        y_encoded = self.label_encoder.transform(y)

        # Log distribution
        unique, counts = np.unique(y_encoded, return_counts=True)
        dist = {self.label_encoder.inverse_transform([i])[0]: c for i, c in zip(unique, counts)}
        logger.info(f"📊 Class distribution: {dist}")

        # Split (stratified)
        if len(np.unique(y_encoded)) < 2:
            logger.warning("⚠️ Only one class, cannot train")
            return False

        actionable = self._balance_training_frame(actionable)
        if self.last_balance_info.get('applied'):
            logger.info(
                "📊 V4 neutral downsampling applied: %s -> %s",
                self.last_balance_info['before'],
                self.last_balance_info['after'],
            )

        X = self._build_features(actionable)
        y = actionable['label']
        y_encoded = self.label_encoder.transform(y)

        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y_encoded, test_size=test_size, random_state=42, stratify=y_encoded
            )
        except ValueError:
            # Fallback kalau stratify gagal
            X_train, X_test, y_train, y_test = train_test_split(
                X, y_encoded, test_size=test_size, random_state=42
            )

        # Scale
        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s = self.scaler.transform(X_test)

        # Train
        logger.info("🤖 Training RF + GB models...")
        sample_weight = compute_sample_weight(class_weight='balanced', y=y_train)
        self.rf_model.fit(X_train_s, y_train, sample_weight=sample_weight)
        self.gb_model.fit(X_train_s, y_train, sample_weight=sample_weight)

        # Evaluate
        self.last_eval = self._evaluate(X_test_s, y_test, self.label_encoder)
        self.is_fitted = True
        self.last_trained = datetime.now()

        logger.info(f"✅ V4 model trained. Win rate: {self.last_eval.win_rate:.1%}, "
                    f"Profit factor: {self.last_eval.profit_factor:.2f}")

        # Save
        self.save_model()
        return True

    def _encode_rec(self, rec: str) -> int:
        """Encode recommendation to int"""
        mapping = {'BUY': 0, 'STRONG_BUY': 1, 'SELL': 2, 'STRONG_SELL': 3, 'HOLD': -1}
        return mapping.get(rec.upper(), -1)

    def _evaluate(self, X_test: np.ndarray, y_test: np.ndarray,
                  encoder: LabelEncoder) -> MLEvaluation:
        """Evaluate dengan trading-focused metrics"""
        # Predictions
        pred_rf = self.rf_model.predict(X_test)
        pred_gb = self.gb_model.predict(X_test)

        # Ensemble (vote)
        pred_ens = np.array([
            np.bincount([r, g]).argmax() for r, g in zip(pred_rf, pred_gb)
        ])

        # Accuracy
        acc = np.mean(pred_ens == y_test)

        # Confusion matrix
        cm = confusion_matrix(y_test, pred_ens, labels=range(len(encoder.classes_)))

        # Win rate: GOOD / (GOOD + BAD)
        # Map labels
        test_labels = encoder.inverse_transform(y_test)
        pred_labels = encoder.inverse_transform(pred_ens)

        good_count = sum(1 for t in test_labels if t.startswith('GOOD'))
        bad_count = sum(1 for t in test_labels if t.startswith('BAD'))
        win_rate = good_count / (good_count + bad_count) if (good_count + bad_count) > 0 else 0

        # Profit factor (simplified: assume fixed TP/SL)
        # GOOD_BUY/GODD_SELL = +3%, BAD_BUY/BAD_SELL = -2%, NEUTRAL = 0%
        profit_map = {
            'GOOD_BUY': 3.0, 'GOOD_SELL': 3.0,
            'BAD_BUY': -2.0, 'BAD_SELL': -2.0,
            'NEUTRAL_BUY': 0.0, 'NEUTRAL_SELL': 0.0
        }
        profits = [profit_map.get(p, 0.0) for p in pred_labels]
        total_profit = sum(p for p in profits if p > 0)
        total_loss = abs(sum(p for p in profits if p < 0))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # Expectancy
        expectancy = np.mean(profits) if profits else 0.0

        # Precision per class
        label_ids = list(range(len(encoder.classes_)))
        report = classification_report(
            y_test, pred_ens, labels=label_ids, target_names=encoder.classes_, output_dict=True, zero_division=0
        )
        prec_good_buy = report.get('GOOD_BUY', {}).get('precision', 0.0)
        prec_bad_buy = report.get('BAD_BUY', {}).get('precision', 0.0)

        report_str = classification_report(
            y_test, pred_ens, labels=label_ids, target_names=encoder.classes_, zero_division=0
        )

        return MLEvaluation(
            accuracy=acc,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            precision_good_buy=prec_good_buy,
            precision_bad_buy=prec_bad_buy,
            confusion_matrix=cm,
            report=report_str,
        )

    def predict(self, features: Dict[str, Any]) -> Tuple[str, float]:
        """
        Predict label untuk signal baru.

        Args:
            features: dict dengan keys: signal_price, ml_confidence, recommendation, hour, dayofweek, symbol

        Returns:
            (predicted_label: str, confidence: float)
        """
        if not self.is_fitted:
            return "NEUTRAL", 0.5

        # Build single row
        df = pd.DataFrame([{
            'signal_price': features.get('signal_price', 0),
            'ml_confidence': features.get('ml_confidence', 0.5),
            'rec_encoded': self._encode_rec(features.get('recommendation', 'HOLD')),
            'hour': features.get('hour', 0),
            'dayofweek': features.get('dayofweek', 0),
            'symbol': features.get('symbol', ''),
        }])

        X = self._build_features(df)
        Xs = self.scaler.transform(X)

        # Predict
        pred_rf = self.rf_model.predict(Xs)[0]
        pred_gb = self.gb_model.predict(Xs)[0]
        pred = np.bincount([pred_rf, pred_gb]).argmax()

        # Confidence = average probability of predicted class
        proba_rf = self.rf_model.predict_proba(Xs)[0]
        proba_gb = self.gb_model.predict_proba(Xs)[0]
        conf = (
            self._probability_for_encoded_class(self.rf_model, proba_rf, pred) +
            self._probability_for_encoded_class(self.gb_model, proba_gb, pred)
        ) / 2

        label = self.label_encoder.inverse_transform([pred])[0]
        return label, float(conf)

    def save_model(self):
        """Save model to disk"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            with open(self.model_path, 'wb') as f:
                pickle.dump({
                    'rf_model': self.rf_model,
                    'gb_model': self.gb_model,
                    'scaler': self.scaler,
                    'label_encoder': self.label_encoder,
                    'feature_names': self.feature_names,
                    'is_fitted': self.is_fitted,
                    'last_eval': self.last_eval,
                    'last_trained': self.last_trained,
                    'last_class_distribution': self.last_class_distribution,
                    'last_balance_info': self.last_balance_info,
                }, f)
            logger.info(f"💾 V4 model saved to {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save V4 model: {e}")

    def load_model(self) -> bool:
        """Load model from disk"""
        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
            self.rf_model = data['rf_model']
            self.gb_model = data['gb_model']
            self.scaler = data['scaler']
            self.label_encoder = data['label_encoder']
            self.feature_names = data['feature_names']
            self.is_fitted = data['is_fitted']
            self.last_eval = data.get('last_eval')
            self.last_trained = data.get('last_trained')
            self.last_class_distribution = data.get('last_class_distribution', {})
            self.last_balance_info = data.get('last_balance_info', {})
            logger.info(f"📂 V4 model loaded from {self.model_path}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to load V4 model: {e}, creating fresh")
            self._init_models()
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get model status for display"""
        return {
            'version': 'V4',
            'fitted': self.is_fitted,
            'last_trained': self.last_trained.isoformat() if self.last_trained else None,
            'win_rate': self.last_eval.win_rate if self.last_eval else None,
            'profit_factor': self.last_eval.profit_factor if self.last_eval else None,
            'expectancy': self.last_eval.expectancy if self.last_eval else None,
            'accuracy': self.last_eval.accuracy if self.last_eval else None,
            'class_distribution': self.last_class_distribution,
            'balance_info': self.last_balance_info,
        }


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    # Dummy outcomes
    from datetime import datetime
    class DummyOutcome:
        def __init__(self, label, price=1000, conf=0.7, rec="BUY"):
            self.signal_price = price
            self.ml_confidence = conf
            self.recommendation = rec
            self.received_at = datetime.now()
            self.symbol = "BTCIDR"
            self.label = label

    outcomes = [
        DummyOutcome("GOOD_BUY", 1000, 0.8, "BUY"),
        DummyOutcome("GOOD_BUY", 1050, 0.75, "BUY"),
        DummyOutcome("BAD_BUY", 1100, 0.55, "BUY"),
        DummyOutcome("BAD_BUY", 900, 0.5, "BUY"),
        DummyOutcome("NEUTRAL_BUY", 1000, 0.6, "BUY"),
        DummyOutcome("GOOD_SELL", 2000, 0.85, "SELL"),
        DummyOutcome("BAD_SELL", 2100, 0.5, "SELL"),
    ] * 10  # Duplicate for min samples

    model = MLTradingModelV4(model_path="models/test_v4.pkl")
    success = model.train_from_outcomes(outcomes)
    print(f"Train success: {success}")
    print(f"Status: {model.get_status()}")

    pred, conf = model.predict({
        'signal_price': 1000,
        'ml_confidence': 0.8,
        'recommendation': 'BUY',
        'hour': 14,
        'dayofweek': 2,
        'symbol': 'BTCIDR',
    })
    print(f"Prediction: {pred} (conf: {conf:.2%})")
