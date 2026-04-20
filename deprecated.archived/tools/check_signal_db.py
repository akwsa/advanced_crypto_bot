#!/usr/bin/env python3
"""
Signal DB Quick Check
=====================
Check signal database status WITHOUT locking the file.
Uses WAL mode and read-only connection.

USAGE:
    python check_signal_db.py              # Quick status
    python check_signal_db.py --count      # Total count only
    python check_signal_db.py --recent 20  # Last 20 signals
    python check_signal_db.py --today      # Signals today
    python check_signal_db.py --symbol BTCIDR  # Filter by symbol
    python check_signal_db.py --rec BUY    # Filter by recommendation
"""

import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = "data/signals.db"


def get_readonly_connection():
    """Open DB in read-only mode with WAL to avoid locking"""
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        print(f"   Expected path: {os.path.abspath(DB_PATH)}")
        sys.exit(1)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def show_status(conn):
    """Show quick database status"""
    cursor = conn.cursor()

    # Total count
    cursor.execute("SELECT COUNT(*) as cnt FROM signals")
    total = cursor.fetchone()["cnt"]

    # Today's count
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE received_date = ?", (today,))
    today_count = cursor.fetchone()["cnt"]

    # Latest signal
    cursor.execute("SELECT symbol, recommendation, received_at FROM signals ORDER BY received_at DESC LIMIT 1")
    latest = cursor.fetchone()

    # Incomplete signals count
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM signals
        WHERE rsi IN ('—', '---') OR macd IN ('—', '---')
        OR ma_trend IN ('—', '---') OR bollinger IN ('—', '---')
        OR volume IN ('—', '---')
    """)
    incomplete = cursor.fetchone()["cnt"]

    print(f"\n{'=' * 60}")
    print(f"  📊 SIGNAL DATABASE STATUS")
    print(f"{'=' * 60}")
    print(f"   Total signals:    {total}")
    print(f"   Today ({today}):  {today_count}")
    print(f"   Incomplete (—):   {incomplete}")
    if latest:
        print(f"   Latest signal:    {latest['symbol']} {latest['recommendation']} @ {latest['received_at']}")
    print(f"{'=' * 60}\n")


def show_recent(conn, limit=10):
    """Show recent signals"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT symbol, price, recommendation, ml_confidence, received_at
        FROM signals
        ORDER BY received_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    if not rows:
        print("⚠️ No signals found")
        return

    print(f"\n{'=' * 80}")
    print(f"  📋 RECENT {limit} SIGNALS")
    print(f"{'=' * 80}")
    print(f"{'No':<5} {'Date/Time':<22} {'Symbol':<14} {'Rec':<14} {'Price':<16} {'Confidence':<12}")
    print(f"{'─' * 80}")

    for i, row in enumerate(rows, 1):
        price = row["price"]
        try:
            price = float(price)
            price_str = f"{price:,.0f}" if price >= 1000 else f"{price:.4f}"
        except (ValueError, TypeError):
            price_str = str(price)

        conf = f"{row['ml_confidence']:.1%}" if row["ml_confidence"] else "—"

        print(f"{i:<5} {row['received_at']:<22} {row['symbol']:<14} {row['recommendation']:<14} {price_str:<16} {conf:<12}")

    print(f"{'=' * 80}\n")


def show_today(conn):
    """Show all signals from today"""
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT symbol, price, recommendation, ml_confidence, received_at
        FROM signals
        WHERE received_date = ?
        ORDER BY received_at DESC
    """, (today,))

    rows = cursor.fetchall()
    if not rows:
        print(f"\n⚠️ No signals found for today ({today})\n")
        return

    print(f"\n{'=' * 80}")
    print(f"  📅 SIGNALS TODAY ({today}) - {len(rows)} signals")
    print(f"{'=' * 80}")

    for i, row in enumerate(rows, 1):
        price = row["price"]
        try:
            price = float(price)
            price_str = f"{price:,.0f}" if price >= 1000 else f"{price:.4f}"
        except (ValueError, TypeError):
            price_str = str(price)

        conf = f"{row['ml_confidence']:.1%}" if row["ml_confidence"] else "—"
        print(f"  {i:>3}. {row['received_at']}  {row['symbol']:<14} {row['recommendation']:<14} {price_str:>12}  {conf}")

    print(f"{'=' * 80}\n")


def filter_signals(conn, symbol=None, rec=None):
    """Filter signals by symbol or recommendation"""
    cursor = conn.cursor()
    query = "SELECT symbol, price, recommendation, ml_confidence, received_at FROM signals WHERE 1=1"
    params = []

    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())

    if rec:
        query += " AND recommendation = ?"
        params.append(rec.upper())

    query += " ORDER BY received_at DESC LIMIT 50"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    if not rows:
        print(f"\n⚠️ No signals found")
        return

    filter_desc = []
    if symbol: filter_desc.append(f"Symbol={symbol.upper()}")
    if rec: filter_desc.append(f"Rec={rec.upper()}")

    print(f"\n{'=' * 80}")
    print(f"  🔍 SIGNALS: {', '.join(filter_desc)} ({len(rows)} results)")
    print(f"{'=' * 80}")

    for i, row in enumerate(rows, 1):
        price = row["price"]
        try:
            price = float(price)
            price_str = f"{price:,.0f}" if price >= 1000 else f"{price:.4f}"
        except (ValueError, TypeError):
            price_str = str(price)

        conf = f"{row['ml_confidence']:.1%}" if row["ml_confidence"] else "—"
        print(f"  {i:>3}. {row['received_at']}  {row['symbol']:<14} {row['recommendation']:<14} {price_str:>12}  {conf}")

    print(f"{'=' * 80}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Signal DB Quick Check (Read-Only, No Lock)")
    parser.add_argument("--count", action="store_true", help="Show total count only")
    parser.add_argument("--recent", type=int, default=0, help="Show last N signals")
    parser.add_argument("--today", action="store_true", help="Show all signals from today")
    parser.add_argument("--symbol", type=str, help="Filter by symbol")
    parser.add_argument("--rec", type=str, help="Filter by recommendation")

    args = parser.parse_args()

    conn = get_readonly_connection()

    try:
        if args.count:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM signals")
            print(f"Total signals: {cursor.fetchone()['cnt']}")
        elif args.recent > 0:
            show_recent(conn, args.recent)
        elif args.today:
            show_today(conn)
        elif args.symbol or args.rec:
            filter_signals(conn, args.symbol, args.rec)
        else:
            show_status(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
