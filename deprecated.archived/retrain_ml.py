#!/usr/bin/env python3
"""
Quick ML model retrain script
Trains the ML model with historical data from database
"""

import sys
sys.path.insert(0, '.')

from core.database import Database
from core.config import Config
from analysis.ml_model import MLTradingModel
import pandas as pd

print("=" * 60)
print("ML MODEL RETRAIN")
print("=" * 60)
print()

# Load database
db = Database()
print("[OK] Database loaded")

# Collect historical data
data_frames = []
pairs_loaded = []

for pair in Config.WATCH_PAIRS:
    df = db.get_price_history(pair, limit=5000)
    if not df.empty and len(df) >= 100:
        data_frames.append(df)
        pairs_loaded.append(f"{pair}: {len(df)} candles")
        print(f"  [OK] {pair}: {len(df)} candles")
    elif not df.empty:
        print(f"  [WARN] {pair}: only {len(df)} candles (need 100+)")

if not data_frames:
    print("\n[FAIL] NOT ENOUGH DATA for training!")
    print("Need at least 100 candles per pair.")
    print("Bot needs to run for longer to collect data.")
    sys.exit(1)

# Concat all data
all_data = pd.concat(data_frames, ignore_index=True)
total_candles = len(all_data)

print(f"\nData: {total_candles} candles from {len(pairs_loaded)} pairs")

# Train model
model = MLTradingModel()
print("\nTraining ML model...")

success = model.train(all_data)

if success:
    accuracy = getattr(model, 'last_accuracy', 'N/A')
    print(f"\n[OK] Model trained successfully!")
    if isinstance(accuracy, (int, float)):
        print(f"   Accuracy: {accuracy:.2%}")
    else:
        print(f"   Accuracy: {accuracy}")
    print(f"   Model saved to: {model.model_path}")
    print(f"\nBot will use this model after restart.")
else:
    print("\n[FAIL] Model training FAILED!")
    print("Check logs for details.")
    sys.exit(1)
