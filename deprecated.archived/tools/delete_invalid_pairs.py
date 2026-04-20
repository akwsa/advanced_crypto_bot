#!/usr/bin/env python3
"""
Delete invalid pairs from watchlist, price_history, and signals
"""

import sqlite3

DB_PATH = 'data/trading.db'
SIGNALS_DB_PATH = 'data/signals.db'
INVALID_PAIRS = ['orderidr', 'superidr', 'didr', 'raveidr']

print("=" * 60)
print("🗑️ DELETING INVALID PAIRS")
print("=" * 60)

# Connect to both databases
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    signals_conn = sqlite3.connect(SIGNALS_DB_PATH)
    signals_cursor = signals_conn.cursor()
    has_signals_db = True
except Exception as e:
    print(f"⚠️ Could not connect to signals.db: {e}")
    has_signals_db = False
    signals_conn = None
    signals_cursor = None

for pair in INVALID_PAIRS:
    # Delete from watchlist
    cursor.execute("DELETE FROM watchlist WHERE pair = ?", (pair,))
    wl_deleted = cursor.rowcount

    # Delete from price_history
    cursor.execute("DELETE FROM price_history WHERE pair = ?", (pair,))
    ph_deleted = cursor.rowcount

    # Delete from signals.db (new primary signal storage)
    sig_deleted = 0
    if has_signals_db:
        signals_cursor.execute("DELETE FROM signals WHERE symbol = ?", (pair.upper(),))
        sig_deleted = signals_cursor.rowcount

    status = "✅" if wl_deleted > 0 or ph_deleted > 0 or sig_deleted > 0 else "ℹ️ "
    print(f"{status} {pair}: watchlist={wl_deleted}, price_history={ph_deleted}, signals={sig_deleted}")

conn.commit()
if signals_conn:
    signals_conn.commit()

# Verify deletion
print(f"\n📋 VERIFYING:")
cursor.execute("SELECT COUNT(*) as cnt FROM watchlist WHERE pair IN ({})".format(','.join('?'*len(INVALID_PAIRS))), INVALID_PAIRS)
remaining_wl = cursor.fetchone()['cnt']

cursor.execute("SELECT COUNT(*) as cnt FROM price_history WHERE pair IN ({})".format(','.join('?'*len(INVALID_PAIRS))), INVALID_PAIRS)
remaining_ph = cursor.fetchone()['cnt']

print(f"  Watchlist remaining: {remaining_wl}")
print(f"  Price history remaining: {remaining_ph}")

if signals_conn:
    signals_cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE symbol IN ({})".format(','.join('?'*len(INVALID_PAIRS))), [p.upper() for p in INVALID_PAIRS])
    remaining_sig = signals_cursor.fetchone()['cnt']
    print(f"  Signals remaining: {remaining_sig}")

# Show final watchlist count
cursor.execute("SELECT COUNT(*) as cnt FROM watchlist WHERE is_active = 1")
total_active = cursor.fetchone()['cnt']
print(f"\n✅ Total active watchlist pairs: {total_active}")

conn.close()
if signals_conn:
    signals_conn.close()
print(f"\n{'='*60}")
