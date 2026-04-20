#!/usr/bin/env python3
"""Quick script to check ML model status and database data count."""

import os
import sys
import joblib
import sqlite3
from datetime import datetime

# Paths
MODEL_PATH = 'models/trading_model.pkl'
DB_PATH = 'data/trading.db'
SIGNALS_DB_PATH = 'data/signals.db'

print("=" * 60)
print("🤖 ML MODEL STATUS CHECK")
print("=" * 60)

# ── 1. Load model ─────────────────────────────────────────────
if not os.path.exists(MODEL_PATH):
    print(f"\n❌ Model file not found at {MODEL_PATH}")
    sys.exit(1)

print(f"\n📂 Loading model from {MODEL_PATH} ...")
data = joblib.load(MODEL_PATH)

last_trained = data.get('last_trained')
accuracy = data.get('last_accuracy')
precision = data.get('last_precision')
recall = data.get('last_recall')
feature_names = data.get('feature_names')
scaler = data.get('scaler')
model = data.get('model')

print(f"\n✅ Model loaded successfully")
print(f"   Last trained : {last_trained or 'Unknown'}")
print(f"   Accuracy     : {accuracy if accuracy else 'N/A'}")
print(f"   Precision    : {precision if precision else 'N/A'}")
print(f"   Recall       : {recall if recall else 'N/A'}")
print(f"   Features     : {len(feature_names) if feature_names else 0}")

if model:
    print(f"\n🧠 Model components:")
    for key in model:
        print(f"   • {key}")

# ── 2. Database stats ─────────────────────────────────────────
print("\n" + "=" * 60)
print("💾 DATABASE STATS")
print("=" * 60)

if not os.path.exists(DB_PATH):
    print(f"\n❌ Database not found at {DB_PATH}")
else:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Total candles
    cursor.execute("SELECT COUNT(*) as cnt FROM price_history")
    total_candles = cursor.fetchone()['cnt']
    print(f"\n📊 Total candles in DB: {total_candles:,}")

    # Per-pair candle count
    cursor.execute("""
        SELECT pair, COUNT(*) as cnt, MAX(timestamp) as latest
        FROM price_history
        GROUP BY pair
        ORDER BY cnt DESC
    """)
    rows = cursor.fetchall()
    print(f"\n📈 Per-pair breakdown:")
    for row in rows:
        print(f"   • {row['pair']:15s} : {row['cnt']:>6,} candles  (latest: {row['latest']})")

    # Total signals (from signals.db)
    try:
        signals_conn = sqlite3.connect(SIGNALS_DB_PATH)
        signals_conn.row_factory = sqlite3.Row
        signals_cursor = signals_conn.cursor()

        signals_cursor.execute("SELECT COUNT(*) as cnt FROM signals")
        total_signals = signals_cursor.fetchone()['cnt']
        print(f"\n📡 Total signals recorded: {total_signals:,}")

        # Recent signals (last 24h)
        signals_cursor.execute("""
            SELECT COUNT(*) as cnt FROM signals
            WHERE received_at > datetime('now', '-24 hours')
        """)
        recent_signals = signals_cursor.fetchone()['cnt']
        print(f"📡 Signals (last 24h)   : {recent_signals}")

        # Strong signals (from new schema with recommendation column)
        signals_cursor.execute("""
            SELECT COUNT(*) as cnt FROM signals
            WHERE recommendation IN ('STRONG_BUY', 'STRONG_SELL')
            AND received_date >= date('now', '-7 days')
        """)
        strong_signals = signals_cursor.fetchone()['cnt']
        print(f"🔥 Strong signals (7d)  : {strong_signals}")

        signals_conn.close()
    except Exception as e:
        print(f"\n⚠️  Could not read signals database: {e}")

    # Watchlist
    cursor.execute("SELECT user_id, COUNT(*) as cnt FROM watchlist WHERE is_active = 1 GROUP BY user_id")
    wl_rows = cursor.fetchall()
    print(f"\n👀 Active watchlist pairs:")
    for row in wl_rows:
        print(f"   • User {row['user_id']}: {row['cnt']} pairs")

    conn.close()

print("\n" + "=" * 60)
print("✅ Done.")
print("=" * 60)
