#!/usr/bin/env python3
"""Delete invalid pairs - fixed"""
import sqlite3

DB_PATH = 'data/trading.db'
SIGNALS_DB_PATH = 'data/signals.db'
INVALID_PAIRS = ['orderidr', 'superidr', 'didr', 'raveidr']

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Also connect to signals.db
try:
    signals_conn = sqlite3.connect(SIGNALS_DB_PATH)
    signals_cursor = signals_conn.cursor()
    has_signals_db = True
except Exception as e:
    print(f"Warning: signals.db not available: {e}")
    has_signals_db = False
    signals_conn = None

for pair in INVALID_PAIRS:
    cursor.execute("DELETE FROM watchlist WHERE pair = ?", (pair,))
    wl = cursor.rowcount
    cursor.execute("DELETE FROM price_history WHERE pair = ?", (pair,))
    ph = cursor.rowcount
    # Delete from signals.db using symbol column (uppercase)
    sig = 0
    if has_signals_db:
        signals_cursor.execute("DELETE FROM signals WHERE symbol = ?", (pair.upper(),))
        sig = signals_cursor.rowcount
    print(f"  {pair}: wl={wl}, ph={ph}, signals={sig}")

conn.commit()
if signals_conn:
    signals_conn.commit()

# Verify
cursor.execute("SELECT COUNT(*) FROM watchlist WHERE pair IN (?,?,?,?)", INVALID_PAIRS)
print(f"\nRemaining invalid pairs in watchlist: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM watchlist WHERE is_active = 1")
print(f"Total active watchlist pairs: {cursor.fetchone()[0]}")

conn.close()
if signals_conn:
    signals_conn.close()
print("✅ Done. RESTART BOT now!")
