#!/usr/bin/env python3
"""
Diagnostic: Why /signals only shows 4 pairs?
Check watchlist DB, memory state, and signal generation.
"""

import sqlite3
import os

DB_PATH = 'data/trading.db'

print("=" * 60)
print("🔍 DIAGNOSTIC: /signals OUTPUT")
print("=" * 60)

if not os.path.exists(DB_PATH):
    print(f"\n❌ Database not found: {DB_PATH}")
    exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Check watchlist
cursor.execute("SELECT user_id, pair, is_active FROM watchlist ORDER BY user_id, pair")
watchlist_rows = cursor.fetchall()

print(f"\n📋 WATCHLIST DATABASE ({len(watchlist_rows)} entries):")
by_user = {}
for row in watchlist_rows:
    uid = row['user_id']
    if uid not in by_user:
        by_user[uid] = []
    by_user[uid].append({
        'pair': row['pair'],
        'active': row['is_active']
    })

for uid, pairs in by_user.items():
    active = [p for p in pairs if p['active']]
    print(f"\n  User {uid}: {len(pairs)} total, {len(active)} active")
    if len(active) <= 20:
        for p in active:
            print(f"    • {p['pair']}")
    else:
        for p in active[:10]:
            print(f"    • {p['pair']}")
        print(f"    ... and {len(active) - 10} more")

# 2. Check price_history coverage
print(f"\n📈 PRICE HISTORY COVERAGE:")
cursor.execute("""
    SELECT pair, COUNT(*) as cnt, MAX(timestamp) as latest
    FROM price_history
    GROUP BY pair
    HAVING cnt >= 60
    ORDER BY cnt DESC
""")
price_rows = cursor.fetchall()
print(f"   Pairs with 60+ candles: {len(price_rows)}")
for row in price_rows[:10]:
    print(f"    • {row['pair']:20s}: {row['cnt']:>5,} candles (latest: {row['latest']})")
if len(price_rows) > 10:
    print(f"    ... and {len(price_rows) - 10} more")

# 3. Check if the 4 pairs shown are in watchlist
problem_pairs = ['orderidr', 'superidr', 'didr', 'raveidr']
print(f"\n🔍 CHECKING PROBLEM PAIRS (shown in /signals):")
for p in problem_pairs:
    cursor.execute("SELECT user_id, pair, is_active FROM watchlist WHERE pair = ?", (p,))
    found = cursor.fetchone()
    if found:
        print(f"  ✅ {p}: User {found['user_id']}, active={found['is_active']}")
    else:
        print(f"  ❌ {p}: NOT IN WATCHLIST!")

# 4. Check top pairs that SHOULD be shown
print(f"\n🔍 TOP PAIRS THAT SHOULD APPEAR (from WATCH_PAIRS in config):")
config_pairs = ['btcidr', 'ethidr', 'bridr', 'pippinidr', 'solidr', 'dogeidr', 'xrpidr', 'adaidr']
for p in config_pairs:
    cursor.execute("SELECT user_id, pair, is_active FROM watchlist WHERE pair = ?", (p,))
    found = cursor.fetchone()
    if found:
        print(f"  ✅ {p}: User {found['user_id']}, active={found['is_active']}")
    else:
        print(f"  ❌ {p}: NOT IN WATCHLIST!")

conn.close()

print(f"\n{'='*60}")
print("💡 DIAGNOSIS:")
print("=" * 60)

# Check if problem pairs are actually in watchlist
all_watchlist_pairs = [row['pair'] for row in watchlist_rows if row['is_active']]
problem_in_watchlist = [p for p in problem_pairs if p in all_watchlist_pairs]
config_in_watchlist = [p for p in config_pairs if p in all_watchlist_pairs]

if problem_in_watchlist and not config_in_watchlist:
    print("⚠️  Config pairs (btcidr, etc) NOT in watchlist!")
    print("    But problem pairs ARE in watchlist.")
    print("    → User may have removed config pairs and added others manually")
elif config_in_watchlist:
    print(f"✅ Config pairs ARE in watchlist: {config_in_watchlist}")
    print("    → Bug is in signal generation or memory sync")
else:
    print("⚠️  Neither config nor problem pairs found in watchlist")
    print("    → Watchlist may have been cleared or corrupted")

print(f"\n{'='*60}")
