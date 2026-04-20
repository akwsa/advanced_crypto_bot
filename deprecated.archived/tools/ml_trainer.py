"""
ML Signal Model Trainer (STANDALONE - ALTERNATIVE APPROACH)
===========================================================
Train ML model dari TA signals di signals.db - APPROACH BERBEDA dari ml_model_v2.py

PERBEDAAN PENDEKATAN:
=====================
| ml_model_v2.py (PRODUCTION) | ml_trainer.py (EXPERIMENTAL) |
|------------------------------|-------------------------------|
| Features dari OHLCV price    | Features dari TA indicators   |
| 20+ technical features       | 6 encoded TA signals          |
| Ensemble RF + GB             | RF / GB / XGBoost             |
| Binary/multi-class target    | 5-class classification        |
| Used by bot.py live          | Standalone analysis only      |

CARA PAKAI:
    python tools/ml_trainer.py

    # Export training report
    python tools/ml_trainer.py --report

    # Train with specific model
    python tools/ml_trainer.py --model xgboost

HASIL:
    - models/signal_model_v2.pkl (model baru - FORMAT BERBEDA!)
    - ml_training_report.txt (laporan lengkap)

⚠️  WARNING: Model ini TIDAK LANGSUNG COMPATIBLE dengan bot.py!
    Bot.py menggunakan ml_model_v2.py yang punya format berbeda.
    Script ini hanya untuk analisis & eksperimen.
"""

import os
import sys
import json
import logging
import sqlite3
import argparse
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
import joblib

warnings.filterwarnings('ignore')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class SignalModelTrainer:
    """Train ML model dari signals.db - standalone, tidak ubah bot"""
    
    def __init__(self, db_path: str = "data/signals.db"):
        self.db_path = db_path
        self.df = None
        self.models = {}
        self.best_model = None
        self.best_accuracy = 0
        self.scaler = StandardScaler()
        
        # Feature mappings
        self.rsi_map = {
            'OVERSOLD': 0, 'NEUTRAL': 1, 'OVERBOUGHT': 2, 'BULLISH': 3
        }
        self.macd_map = {
            'STRONG_BEARISH': 0, 'BEARISH': 1, 'NEUTRAL': 2, 'BULLISH': 3, 'STRONG_BULLISH': 4
        }
        self.ma_map = {
            'BEARISH': 0, 'NEUTRAL': 1, 'BULLISH': 2
        }
        self.bb_map = {
            'LOWER': 0, 'NEUTRAL': 1, 'BOUNCE': 2, 'UPPER': 3
        }
        self.vol_map = {
            'LOW': 0, 'NORMAL': 1, 'HIGH': 2
        }
        self.target_map = {
            'STRONG_SELL': 0, 'SELL': 1, 'HOLD': 2, 'BUY': 3, 'STRONG_BUY': 4
        }
        self.target_names = ['STRONG_SELL', 'SELL', 'HOLD', 'BUY', 'STRONG_BUY']
        
    def load_data(self) -> bool:
        """Load data dari signals.db"""
        logger.info("=" * 70)
        logger.info("  ML SIGNAL MODEL TRAINER")
        logger.info("=" * 70)
        
        if not os.path.exists(self.db_path):
            logger.error(f"❌ Database tidak ditemukan: {self.db_path}")
            logger.info("💡 Pastikan bot sudah berjalan dan menyimpan signals")
            return False
        
        try:
            # Baca data
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql("""
                SELECT
                    symbol, price, recommendation,
                    rsi, macd, ma_trend, bollinger, volume,
                    received_at
                FROM signals
                WHERE recommendation IN ('STRONG_SELL', 'SELL', 'HOLD', 'BUY', 'STRONG_BUY')
            """, conn)
            conn.close()
            
            if len(df) == 0:
                logger.error("❌ Tidak ada data valid di database")
                return False
            
            self.df = df
            logger.info(f"✅ Loaded {len(df)} signals from database")
            logger.info(f"   Date range: {df['received_at'].min()} to {df['received_at'].max()}")
            logger.info(f"   Unique symbols: {df['symbol'].nunique()}")
            logger.info(f"   Recommendations: {df['recommendation'].value_counts().to_dict()}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load data: {e}")
            return False
    
    def preprocess(self) -> tuple:
        """Preprocess data untuk training"""
        logger.info("\n" + "=" * 70)
        logger.info("  STEP 1: PREPROCESSING DATA")
        logger.info("=" * 70)
        
        df = self.df.copy()
        
        # Encode categorical features
        logger.info("\n📊 Encoding categorical features...")
        
        df['rsi_encoded'] = df['rsi'].map(self.rsi_map)
        valid_count = df['rsi_encoded'].notna().sum()
        invalid_count = df['rsi_encoded'].isna().sum()
        df['rsi_encoded'] = df['rsi_encoded'].fillna(1).astype(int)
        logger.info(f"   ✅ RSI encoded: {df['rsi_encoded'].nunique()} unique values ({valid_count} valid, {invalid_count} invalid→NEUTRAL)")

        df['macd_encoded'] = df['macd'].map(self.macd_map)
        valid_count = df['macd_encoded'].notna().sum()
        invalid_count = df['macd_encoded'].isna().sum()
        df['macd_encoded'] = df['macd_encoded'].fillna(2).astype(int)
        logger.info(f"   ✅ MACD encoded: {df['macd_encoded'].nunique()} unique values ({valid_count} valid, {invalid_count} invalid→NEUTRAL)")

        df['ma_encoded'] = df['ma_trend'].map(self.ma_map)
        valid_count = df['ma_encoded'].notna().sum()
        invalid_count = df['ma_encoded'].isna().sum()
        df['ma_encoded'] = df['ma_encoded'].fillna(1).astype(int)
        logger.info(f"   ✅ MA Trend encoded: {df['ma_encoded'].nunique()} unique values ({valid_count} valid, {invalid_count} invalid→NEUTRAL)")

        df['bollinger_encoded'] = df['bollinger'].map(self.bb_map)
        valid_count = df['bollinger_encoded'].notna().sum()
        invalid_count = df['bollinger_encoded'].isna().sum()
        df['bollinger_encoded'] = df['bollinger_encoded'].fillna(1).astype(int)
        logger.info(f"   ✅ Bollinger encoded: {df['bollinger_encoded'].nunique()} unique values ({valid_count} valid, {invalid_count} invalid→NEUTRAL)")

        df['volume_encoded'] = df['volume'].map(self.vol_map)
        valid_count = df['volume_encoded'].notna().sum()
        invalid_count = df['volume_encoded'].isna().sum()
        df['volume_encoded'] = df['volume_encoded'].fillna(1).astype(int)
        logger.info(f"   ✅ Volume encoded: {df['volume_encoded'].nunique()} unique values ({valid_count} valid, {invalid_count} invalid→NORMAL)")
        
        # Scale numeric features
        logger.info("\n📊 Scaling numeric features...")
        
        # Log transform price (handle extreme range)
        df['price_log'] = np.log1p(df['price'])
        df['price_scaled'] = self.scaler.fit_transform(df[['price_log']])
        logger.info(f"   ✅ Price scaled: range [{df['price_scaled'].min():.2f}, {df['price_scaled'].max():.2f}]")
        
        # Encode target
        logger.info("\n📊 Encoding target variable...")
        df['target'] = df['recommendation'].map(self.target_map)
        
        # Drop rows with invalid target
        before = len(df)
        df = df.dropna(subset=['target'])
        df['target'] = df['target'].astype(int)
        after = len(df)
        
        if before > after:
            logger.warning(f"   ⚠️ Dropped {before - after} rows with invalid target")
        
        logger.info(f"   ✅ Target encoded: {df['target'].nunique()} classes")
        
        # Define features (TA ONLY - no ml_confidence/combined_strength to avoid data leakage)
        self.feature_names = [
            'price_scaled',
            'rsi_encoded',
            'macd_encoded',
            'ma_encoded',
            'bollinger_encoded',
            'volume_encoded'
        ]
        
        X = df[self.feature_names]
        y = df['target']
        
        logger.info(f"\n📊 Final dataset:")
        logger.info(f"   Samples: {len(X)}")
        logger.info(f"   Features: {len(self.feature_names)}")
        logger.info(f"   Classes: {y.nunique()}")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, 
            test_size=0.2, 
            random_state=42,
            stratify=y
        )
        
        logger.info(f"\n📊 Train/Test Split:")
        logger.info(f"   Train: {len(X_train)} samples")
        logger.info(f"   Test:  {len(X_test)} samples")
        
        return X_train, X_test, y_train, y_test
    
    def train_random_forest(self, X_train, X_test, y_train, y_test):
        """Train Random Forest"""
        logger.info("\n" + "=" * 70)
        logger.info("  STEP 2a: TRAINING RANDOM FOREST")
        logger.info("=" * 70)
        
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
        
        model.fit(X_train, y_train)
        
        train_acc = model.score(X_train, y_train)
        test_acc = model.score(X_test, y_test)
        
        logger.info(f"\n✅ Random Forest Results:")
        logger.info(f"   Train Accuracy: {train_acc:.2%}")
        logger.info(f"   Test Accuracy:  {test_acc:.2%}")
        
        self.models['random_forest'] = {
            'model': model,
            'train_acc': train_acc,
            'test_acc': test_acc
        }
        
        return model, test_acc
    
    def train_gradient_boosting(self, X_train, X_test, y_train, y_test):
        """Train Gradient Boosting"""
        logger.info("\n" + "=" * 70)
        logger.info("  STEP 2b: TRAINING GRADIENT BOOSTING")
        logger.info("=" * 70)
        
        model = GradientBoostingClassifier(
            n_estimators=150,
            learning_rate=0.1,
            max_depth=5,
            random_state=42
        )
        
        model.fit(X_train, y_train)
        
        train_acc = model.score(X_train, y_train)
        test_acc = model.score(X_test, y_test)
        
        logger.info(f"\n✅ Gradient Boosting Results:")
        logger.info(f"   Train Accuracy: {train_acc:.2%}")
        logger.info(f"   Test Accuracy:  {test_acc:.2%}")
        
        self.models['gradient_boosting'] = {
            'model': model,
            'train_acc': train_acc,
            'test_acc': test_acc
        }
        
        return model, test_acc
    
    def train_xgboost(self, X_train, X_test, y_train, y_test):
        """Train XGBoost (jika tersedia)"""
        logger.info("\n" + "=" * 70)
        logger.info("  STEP 2c: TRAINING XGBOOST")
        logger.info("=" * 70)
        
        try:
            import xgboost as xgb
            
            model = xgb.XGBClassifier(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=6,
                random_state=42,
                use_label_encoder=False,
                eval_metric='mlogloss'
            )
            
            model.fit(X_train, y_train)
            
            train_acc = model.score(X_train, y_train)
            test_acc = model.score(X_test, y_test)
            
            logger.info(f"\n✅ XGBoost Results:")
            logger.info(f"   Train Accuracy: {train_acc:.2%}")
            logger.info(f"   Test Accuracy:  {test_acc:.2%}")
            
            self.models['xgboost'] = {
                'model': model,
                'train_acc': train_acc,
                'test_acc': test_acc
            }
            
            return model, test_acc
            
        except ImportError:
            logger.warning("⚠️  XGBoost tidak terinstall. Skip training.")
            logger.info("💡 Install dengan: pip install xgboost")
            return None, 0
    
    def evaluate_model(self, model, X_test, y_test, model_name: str):
        """Evaluate model dengan classification report"""
        logger.info("\n" + "=" * 70)
        logger.info(f"  EVALUATION: {model_name.upper()}")
        logger.info("=" * 70)
        
        y_pred = model.predict(X_test)
        
        # Classification report
        report = classification_report(
            y_test, y_pred, 
            target_names=self.target_names,
            output_dict=True
        )
        
        # Confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        
        logger.info(f"\n📊 Classification Report:")
        for name in self.target_names:
            if name in report:
                r = report[name]
                logger.info(f"   {name:<15} P:{r['precision']:.2%} R:{r['recall']:.2%} F1:{r['f1-score']:.2%} Support:{r['support']}")
        
        logger.info(f"\n   Overall Accuracy: {report['accuracy']:.2%}")
        
        logger.info(f"\n📊 Confusion Matrix:")
        logger.info(f"   {cm}")
        
        # Feature importance
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            idx = importances.argsort()[::-1]
            
            logger.info(f"\n📊 Feature Importance:")
            for i in idx:
                logger.info(f"   {self.feature_names[i]:<25} {importances[i]:.2%}")
        
        return report
    
    def select_best_model(self):
        """Pilih model terbaik"""
        logger.info("\n" + "=" * 70)
        logger.info("  STEP 3: SELECTING BEST MODEL")
        logger.info("=" * 70)
        
        for name, data in self.models.items():
            logger.info(f"   {name:<20} Train: {data['train_acc']:.2%}  Test: {data['test_acc']:.2%}")
        
        # Pilih berdasarkan test accuracy
        best_name = max(self.models.keys(), key=lambda k: self.models[k]['test_acc'])
        self.best_model = self.models[best_name]['model']
        self.best_accuracy = self.models[best_name]['test_acc']
        
        logger.info(f"\n✅ Best Model: {best_name}")
        logger.info(f"   Test Accuracy: {self.best_accuracy:.2%}")
        
        return best_name
    
    def save_model(self, model_name: str):
        """Save model ke file"""
        logger.info("\n" + "=" * 70)
        logger.info("  STEP 4: SAVING MODEL")
        logger.info("=" * 70)
        
        # Pastikan folder models ada
        os.makedirs('models', exist_ok=True)
        
        model_data = {
            'model': self.best_model,
            'scaler': self.scaler,
            'features': self.feature_names,
            'rsi_map': self.rsi_map,
            'macd_map': self.macd_map,
            'ma_map': self.ma_map,
            'bb_map': self.bb_map,
            'vol_map': self.vol_map,
            'target_map': self.target_map,
            'target_names': self.target_names,
            'model_name': model_name,
            'train_accuracy': max(m['train_acc'] for m in self.models.values()),
            'test_accuracy': self.best_accuracy,
            'trained_on': datetime.now().isoformat(),
            'data_size': len(self.df)
        }
        
        model_path = 'models/signal_model_v2.pkl'
        joblib.dump(model_data, model_path)
        
        file_size = os.path.getsize(model_path) / 1024
        logger.info(f"\n✅ Model saved to: {model_path}")
        logger.info(f"   File size: {file_size:.1f} KB")
        logger.info(f"   Test Accuracy: {self.best_accuracy:.2%}")
        logger.info(f"\n💡 Bot masih pakai model lama (tidak berubah)")
        logger.info(f"💡 Model baru siap untuk testing/deployment nanti")
        
        return model_path
    
    def generate_report(self) -> str:
        """Generate training report"""
        report = []
        report.append("=" * 70)
        report.append("  ML SIGNAL MODEL TRAINING REPORT")
        report.append("=" * 70)
        report.append(f"Training Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Database: {self.db_path}")
        report.append(f"Data Size: {len(self.df)} signals")
        report.append(f"Date Range: {self.df['received_at'].min()} to {self.df['received_at'].max()}")
        report.append(f"Unique Symbols: {self.df['symbol'].nunique()}")
        report.append("")
        
        report.append("MODEL COMPARISON:")
        report.append("-" * 70)
        for name, data in self.models.items():
            report.append(f"  {name:<20} Train: {data['train_acc']:.2%}  Test: {data['test_acc']:.2%}")
        
        report.append("")
        report.append(f"BEST MODEL: {max(self.models.keys(), key=lambda k: self.models[k]['test_acc'])}")
        report.append(f"Test Accuracy: {self.best_accuracy:.2%}")
        report.append("")
        
        report.append("FEATURE IMPORTANCE:")
        report.append("-" * 70)
        if hasattr(self.best_model, 'feature_importances_'):
            importances = self.best_model.feature_importances_
            idx = importances.argsort()[::-1]
            for i in idx:
                report.append(f"  {self.feature_names[i]:<25} {importances[i]:.2%}")
        
        report.append("")
        report.append("CLASS DISTRIBUTION:")
        report.append("-" * 70)
        for rec, count in self.df['recommendation'].value_counts().items():
            report.append(f"  {rec:<15} {count:>5} ({count/len(self.df)*100:.1f}%)")
        
        report.append("")
        report.append("=" * 70)
        report.append("  STATUS: ✅ MODEL TRAINED & SAVED (bot tidak diubah)")
        report.append("=" * 70)
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="ML Signal Model Trainer")
    parser.add_argument("--model", type=str, default="all", 
                       help="Model to train: all, random_forest, gradient_boosting, xgboost")
    parser.add_argument("--report", action="store_true", help="Generate training report")
    parser.add_argument("--db", type=str, default="data/signals.db", help="Database path")
    args = parser.parse_args()
    
    # Initialize trainer
    trainer = SignalModelTrainer(db_path=args.db)
    
    # Load data
    if not trainer.load_data():
        sys.exit(1)
    
    # Preprocess
    X_train, X_test, y_train, y_test = trainer.preprocess()
    
    # Train models
    if args.model in ['all', 'random_forest']:
        trainer.train_random_forest(X_train, X_test, y_train, y_test)
    
    if args.model in ['all', 'gradient_boosting']:
        trainer.train_gradient_boosting(X_train, X_test, y_train, y_test)
    
    if args.model in ['all', 'xgboost']:
        trainer.train_xgboost(X_train, X_test, y_train, y_test)
    
    if not trainer.models:
        logger.error("❌ No models trained!")
        sys.exit(1)
    
    # Evaluate all models
    for name, data in trainer.models.items():
        trainer.evaluate_model(data['model'], X_test, y_test, name)
    
    # Select best
    best_name = trainer.select_best_model()
    
    # Save
    model_path = trainer.save_model(best_name)
    
    # Generate report
    if args.report:
        report = trainer.generate_report()
        print("\n" + report)
        
        # Save to file
        with open('ml_training_report.txt', 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"\n📄 Report saved to: ml_training_report.txt")
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("  TRAINING COMPLETE!")
    logger.info("=" * 70)
    logger.info(f"✅ Best Model: {best_name}")
    logger.info(f"✅ Test Accuracy: {trainer.best_accuracy:.2%}")
    logger.info(f"✅ Saved to: {model_path}")
    logger.info(f"✅ Bot: TIDAK DIUBAH (masih pakai model lama)")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
