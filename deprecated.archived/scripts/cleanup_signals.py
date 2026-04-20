#!/usr/bin/env python3
"""
Database Cleanup Script
=======================
Cleans old signal data to prevent database bloat.

Usage:
    python scripts/cleanup_signals.py --days 30
    python scripts/cleanup_signals.py --all  # Reset everything

Add to crontab for weekly cleanup:
    0 2 * * 0 cd /opt/crypto-bot && python scripts/cleanup_signals.py --days 30
"""

import os
import sys
import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def cleanup_signals(db_path: str, days: int = 30, dry_run: bool = False):
    """Clean signal records older than specified days."""

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False

    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime('%Y-%m-%d')

    print(f"🧹 Cleaning signals older than {days} days (before {cutoff_str})")
    print(f"   Database: {db_path}")

    if dry_run:
        print("   [DRY RUN - No changes will be made]")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get count before
        cursor.execute("SELECT COUNT(*) FROM signals")
        count_before = cursor.fetchone()[0]

        # Delete old signals
        if not dry_run:
            cursor.execute(
                "DELETE FROM signals WHERE signal_time < ?",
                (cutoff_str,)
            )
            deleted = cursor.rowcount
            conn.commit()
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM signals WHERE signal_time < ?",
                (cutoff_str,)
            )
            deleted = cursor.fetchone()[0]

        # Get count after
        cursor.execute("SELECT COUNT(*) FROM signals")
        count_after = cursor.fetchone()[0]

        # Vacuum to reclaim space
        if not dry_run and deleted > 0:
            cursor.execute("VACUUM")
            conn.commit()

        conn.close()

        print(f"   Records before: {count_before:,}")
        print(f"   Records after: {count_after:,}")
        print(f"   {'Would delete' if dry_run else 'Deleted'}: {deleted:,} records")

        # Calculate size reduction
        size = os.path.getsize(db_path)
        print(f"   Current size: {size / 1024 / 1024:.2f} MB")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def cleanup_all(db_path: str, dry_run: bool = False):
    """Reset database - DANGER!"""

    if not dry_run:
        response = input("⚠️  WARNING: This will DELETE ALL SIGNALS! Type 'DELETE' to confirm: ")
        if response != "DELETE":
            print("Cancelled.")
            return False

    return cleanup_signals(db_path, days=0, dry_run=dry_run)

def main():
    parser = argparse.ArgumentParser(description='Clean up old signal data')
    parser.add_argument('--days', type=int, default=30,
                        help='Delete signals older than N days (default: 30)')
    parser.add_argument('--all', action='store_true',
                        help='Delete ALL signals (DANGER!)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be deleted without deleting')
    parser.add_argument('--db', type=str, default='data/signals.db',
                        help='Database path')

    args = parser.parse_args()

    print("="*60)
    print("Crypto Bot - Database Cleanup")
    print("="*60)

    # Resolve database path
    db_path = args.db
    if not os.path.isabs(db_path):
        # Try relative to bot directory
        bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(bot_dir, db_path)

    if args.all:
        success = cleanup_all(db_path, dry_run=args.dry_run)
    else:
        success = cleanup_signals(db_path, days=args.days, dry_run=args.dry_run)

    print("="*60)
    if success:
        print("✅ Cleanup completed")
    else:
        print("❌ Cleanup failed")

    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
