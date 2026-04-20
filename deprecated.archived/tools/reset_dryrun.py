#!/usr/bin/env python3
"""
Reset Script - DRY RUN Mode
=============================
Reset balance, watchlist, dan trades untuk testing DRY RUN.

USAGE:
    python reset_dryrun.py              # Reset semua (balance + watchlist + trades)
    python reset_dryrun.py --balance    # Reset balance saja
    python reset_dryrun.py --watchlist  # Reset watchlist saja
    python reset_dryrun.py --trades     # Reset trades saja
    python reset_dryrun.py --all        # Reset SEMUA (balance + watchlist + trades + signals)
    python reset_dryrun.py --user 123456 --balance 50000000  # Reset user tertentu
"""

import sqlite3
import argparse
import sys
import os
from datetime import datetime

# Import config untuk initial balance
try:
    from config import Config
    INITIAL_BALANCE = Config.INITIAL_BALANCE
except ImportError:
    INITIAL_BALANCE = 10000000  # Default 10 juta IDR

DATABASE_PATH = "data/trading.db"
SIGNALS_DB = "data/signals.db"


def get_connection(db_path):
    """Get database connection"""
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def reset_balance(user_id=None, new_balance=None):
    """Reset balance ke initial value atau custom value"""
    conn = get_connection(DATABASE_PATH)
    if not conn:
        return

    cursor = conn.cursor()

    if new_balance is None:
        new_balance = INITIAL_BALANCE

    if user_id:
        # Reset specific user
        cursor.execute('''
            UPDATE users SET balance = ? WHERE user_id = ?
        ''', (new_balance, user_id))
        print(f"✅ Balance user {user_id} reset ke {new_balance:,.0f} IDR")
    else:
        # Reset semua users
        cursor.execute('''
            UPDATE users SET balance = ?
        ''', (new_balance,))
        count = cursor.rowcount
        print(f"✅ Balance {count} user(s) reset ke {new_balance:,.0f} IDR")

    conn.commit()
    conn.close()


def reset_watchlist(user_id=None):
    """Reset watchlist"""
    conn = get_connection(DATABASE_PATH)
    if not conn:
        return

    cursor = conn.cursor()

    if user_id:
        # Reset specific user
        cursor.execute('''
            DELETE FROM watchlist WHERE user_id = ?
        ''', (user_id,))
        count = cursor.rowcount
        print(f"✅ Watchlist user {user_id} dihapus ({count} pair)")
    else:
        # Reset semua watchlist
        cursor.execute('''
            DELETE FROM watchlist
        ''')
        count = cursor.rowcount
        print(f"✅ Semua watchlist dihapus ({count} pair)")

    conn.commit()
    conn.close()


def reset_trades(user_id=None):
    """Reset semua trades (open + closed)"""
    conn = get_connection(DATABASE_PATH)
    if not conn:
        return

    cursor = conn.cursor()

    if user_id:
        # Reset specific user
        cursor.execute('''
            DELETE FROM trades WHERE user_id = ?
        ''', (user_id,))
        count = cursor.rowcount
        print(f"✅ Trades user {user_id} dihapus ({count} trade)")
    else:
        # Reset semua trades
        cursor.execute('''
            DELETE FROM trades
        ''')
        count = cursor.rowcount
        print(f"✅ Semua trades dihapus ({count} trade)")

    conn.commit()
    conn.close()


def reset_signals():
    """Reset semua signals dari signals.db"""
    conn = get_connection(SIGNALS_DB)
    if not conn:
        print(f"⚠️ Signals DB not found: {SIGNALS_DB} (skipping)")
        return

    cursor = conn.cursor()

    cursor.execute('''
        DELETE FROM signals
    ''')
    count = cursor.rowcount
    print(f"✅ Semua signals dihapus ({count} signal)")

    conn.commit()
    conn.close()


def reset_price_history():
    """Reset historical price data"""
    conn = get_connection(DATABASE_PATH)
    if not conn:
        return

    cursor = conn.cursor()

    cursor.execute('''
        DELETE FROM price_history
    ''')
    count = cursor.rowcount
    print(f"✅ Price history dihapus ({count} records)")

    conn.commit()
    conn.close()


def show_current_status(user_id=None):
    """Show current status sebelum reset"""
    conn = get_connection(DATABASE_PATH)
    if not conn:
        return

    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("  CURRENT STATUS (SEBELUM RESET)")
    print("=" * 60)

    if user_id:
        # Show specific user
        cursor.execute('''
            SELECT user_id, balance, first_name, username
            FROM users WHERE user_id = ?
        ''', (user_id,))
        user = cursor.fetchone()
        if user:
            print(f"\n👤 User: {user['first_name']} (@{user['username'] or 'N/A'})")
            print(f"   User ID: {user['user_id']}")
            print(f"   Balance: {user['balance']:,.0f} IDR")

            # Count watchlist
            cursor.execute('SELECT COUNT(*) as count FROM watchlist WHERE user_id = ?', (user_id,))
            print(f"   Watchlist: {cursor.fetchone()['count']} pair(s)")

            # Count trades
            cursor.execute('SELECT COUNT(*) as count FROM trades WHERE user_id = ?', (user_id,))
            print(f"   Trades: {cursor.fetchone()['count']} trade(s)")
        else:
            print(f"❌ User {user_id} not found")
    else:
        # Show all users
        cursor.execute('SELECT COUNT(*) as count FROM users')
        print(f"\n👥 Total Users: {cursor.fetchone()['count']}")

        cursor.execute('SELECT user_id, balance, first_name FROM users')
        for user in cursor.fetchall():
            print(f"\n👤 {user['first_name']} (ID: {user['user_id']})")
            print(f"   Balance: {user['balance']:,.0f} IDR")

        # Total watchlist
        cursor.execute('SELECT COUNT(*) as count FROM watchlist')
        print(f"\n📊 Total Watchlist: {cursor.fetchone()['count']} pair(s)")

        # Total trades
        cursor.execute('SELECT COUNT(*) as count FROM trades')
        print(f"📊 Total Trades: {cursor.fetchone()['count']} trade(s)")

    # Signals
    if os.path.exists(SIGNALS_DB):
        signals_conn = sqlite3.connect(SIGNALS_DB)
        cursor = signals_conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM signals')
        count = cursor.fetchone()[0]
        print(f"📊 Total Signals: {count}")
        signals_conn.close()

    print("=" * 60 + "\n")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Reset DRY RUN data")
    parser.add_argument("--balance", action="store_true", help="Reset balance saja")
    parser.add_argument("--watchlist", action="store_true", help="Reset watchlist saja")
    parser.add_argument("--trades", action="store_true", help="Reset trades saja")
    parser.add_argument("--signals", action="store_true", help="Reset signals saja")
    parser.add_argument("--price-history", action="store_true", help="Reset price history saja")
    parser.add_argument("--all", action="store_true", help="Reset SEMUA")
    parser.add_argument("--user", type=int, help="Reset user tertentu (default: semua)")
    parser.add_argument("--new-balance", type=float, help="Custom balance (default: INITIAL_BALANCE)")
    parser.add_argument("--status", action="store_true", help="Lihat status saja (tidak reset)")

    args = parser.parse_args()

    # Show status sebelum reset
    show_current_status(args.user)

    # Jika tidak ada argument, reset semua
    if len(sys.argv) == 1:
        args.all = True

    # Reset balance
    if args.balance or args.all:
        reset_balance(args.user, args.new_balance)

    # Reset watchlist
    if args.watchlist or args.all:
        reset_watchlist(args.user)

    # Reset trades
    if args.trades or args.all:
        reset_trades(args.user)

    # Reset signals
    if args.signals or args.all:
        reset_signals()

    # Reset price history
    if args.price_history or args.all:
        reset_price_history()

    # Show status setelah reset
    if args.balance or args.watchlist or args.trades or args.signals or args.price_history or args.all:
        print("\n✅ RESET COMPLETE!\n")
        show_current_status(args.user)
    else:
        print("💡 Usage: python reset_dryrun.py --help untuk options")


if __name__ == "__main__":
    main()
