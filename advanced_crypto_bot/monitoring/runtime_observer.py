#!/usr/bin/env python3
"""
Runtime Observer & Monitor
==========================
Script untuk memantau bot secara real-time dari terminal.

Features:
- Monitor adaptive thresholds per pair
- Monitor active trades / positions
- Monitor signal distribution (BUY/SELL/HOLD)
- Monitor circuit breaker status
- Monitor V4 outcomes accumulation

Usage:
    ./venv/bin/python monitoring/runtime_observer.py --db data/trading.db --interval 60
"""

import argparse
import sqlite3
import time
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def format_pct(value):
    return f"{value:.1%}" if value is not None else "N/A"


def format_price(value):
    if value is None:
        return "N/A"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    else:
        return f"{value:,.0f}"


def get_adaptive_summary(db_path):
    """Get adaptive thresholds summary."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT pair, win_rate_7d, profit_factor_7d, total_trades_7d,
               confidence_threshold_buy, position_size_multiplier, skip_pair
        FROM adaptive_thresholds
        ORDER BY profit_factor_7d DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_signal_distribution(db_path):
    """Get signal distribution for last 24h."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Try signals.db first
    try:
        cursor.execute('''
            SELECT recommendation, COUNT(*) as cnt
            FROM signals
            WHERE received_at >= datetime('now', '-24 hours')
            GROUP BY recommendation
        ''')
    except Exception:
        conn.close()
        return {}
    
    rows = cursor.fetchall()
    conn.close()
    return {row['recommendation']: row['cnt'] for row in rows}


def get_active_positions(db_path):
    """Get open trades count."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT pair, COUNT(*) as cnt, SUM(total) as exposure
        FROM trades
        WHERE status = 'OPEN'
        GROUP BY pair
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_v4_outcomes_summary(db_path):
    """Get V4 outcomes summary."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT outcome_label, COUNT(*) as cnt
        FROM trade_outcomes
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY outcome_label
    ''')
    rows = cursor.fetchall()
    conn.close()
    return {row['outcome_label']: row['cnt'] for row in rows}


def get_circuit_breaker_status(db_path):
    """Get drawdown state."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM drawdown_state LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        return None


def print_dashboard(db_path):
    """Print real-time dashboard."""
    os.system('clear' if os.name != 'nt' else 'cls')
    
    print("=" * 70)
    print(f" ADVANCED CRYPTO BOT — RUNTIME MONITOR")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Signal Distribution
    print("\n📊 SIGNAL DISTRIBUTION (24h)")
    print("-" * 40)
    signals = get_signal_distribution(db_path.replace('trading.db', 'signals.db'))
    if signals:
        total = sum(signals.values())
        for rec, cnt in sorted(signals.items(), key=lambda x: -x[1]):
            pct = cnt / total * 100
            bar = "█" * int(pct / 5)
            print(f"  {rec:12s} {cnt:4d} ({pct:5.1f}%) {bar}")
    else:
        print("  No signals in last 24h")
    
    # Adaptive Thresholds
    print("\n🧠 ADAPTIVE THRESHOLDS (Top 10)")
    print("-" * 70)
    print(f"  {'Pair':<12} {'WR':<8} {'PF':<8} {'N':<4} {'Conf':<8} {'PosSize':<8} {'Status'}")
    print("-" * 70)
    thresholds = get_adaptive_summary(db_path)
    for t in thresholds[:10]:
        status = "🚫 SKIP" if t['skip_pair'] else "✅ OK"
        print(f"  {t['pair']:<12} {format_pct(t['win_rate_7d']):<8} {t['profit_factor_7d']:<8.2f} "
              f"{t['total_trades_7d']:<4} {t['confidence_threshold_buy']:<8.2f} "
              f"{t['position_size_multiplier']:<8.2f} {status}")
    
    # Active Positions
    print("\n💰 ACTIVE POSITIONS")
    print("-" * 40)
    positions = get_active_positions(db_path)
    if positions:
        for pos in positions:
            print(f"  {pos['pair']:<12} {pos['cnt']} pos, exposure {format_price(pos['exposure'])}")
    else:
        print("  No open positions")
    
    # V4 Outcomes
    print("\n🤖 V4 OUTCOMES (7d)")
    print("-" * 40)
    outcomes = get_v4_outcomes_summary(db_path)
    if outcomes:
        for label, cnt in sorted(outcomes.items()):
            print(f"  {label:<15} {cnt:4d}")
    else:
        print("  No V4 outcomes recorded yet")
    
    # Circuit Breaker
    print("\n🛡️ CIRCUIT BREAKER")
    print("-" * 40)
    cb = get_circuit_breaker_status(db_path)
    if cb:
        print(f"  Peak equity: {format_price(cb.get('equity_peak', 0))}")
        print(f"  Status: MONITORING")
    else:
        print("  Status: NOT INITIALIZED (no trades yet)")
    
    print("\n" + "=" * 70)
    print(" Press Ctrl+C to exit")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Runtime Monitor for Crypto Bot')
    parser.add_argument('--db', default='data/trading.db', help='Database path')
    parser.add_argument('--interval', type=int, default=60, help='Refresh interval in seconds')
    args = parser.parse_args()
    
    print(f"Starting runtime monitor (refresh every {args.interval}s)...")
    print(f"Database: {args.db}")
    
    try:
        while True:
            print_dashboard(args.db)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")


if __name__ == '__main__':
    main()
