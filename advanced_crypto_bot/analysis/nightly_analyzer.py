#!/usr/bin/env python3
"""
Nightly Analysis Job
===================
Job yang berjalan setiap malam untuk:
1. Analisis performa per pair (7 hari)
2. Update adaptive thresholds
3. Record trade outcomes untuk V4 training
4. Generate summary report

Usage:
    # Dari terminal (manual)
    ./venv/bin/python analysis/nightly_analyzer.py --db data/trading.db
    
    # Dari bot (scheduled)
    scheduler.add_job(nightly_analyzer.run, 'cron', hour=2, minute=0)
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.database import Database
from analysis.adaptive_learning import AdaptiveLearningEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('crypto_bot')


def run_nightly_analysis(db_path: str = 'data/trading.db'):
    """Run nightly analysis dan print summary."""
    logger.info("🌙 Starting nightly adaptive learning analysis...")
    
    db = Database(db_path)
    engine = AdaptiveLearningEngine(db)
    
    result = engine.run_nightly_analysis()
    
    # Print summary
    print("\n" + "="*60)
    print("NIGHTLY ANALYSIS REPORT")
    print("="*60)
    print(f"Pairs analyzed: {result['pairs_analyzed']}")
    print(f"Pairs skipped: {result['pairs_skipped']}")
    print(f"V4 outcomes (7d): {result['v4_outcomes_7d']}")
    
    # Show top performers
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pair, win_rate_7d, profit_factor_7d, total_trades_7d, skip_pair
            FROM adaptive_thresholds
            ORDER BY profit_factor_7d DESC
            LIMIT 10
        ''')
        rows = cursor.fetchall()
        
        if rows:
            print("\n--- Top Performers ---")
            for row in rows:
                status = "🚫 SKIP" if row['skip_pair'] else "✅"
                print(f"  {status} {row['pair']}: WR={row['win_rate_7d']:.1%}, PF={row['profit_factor_7d']:.2f}, N={row['total_trades_7d']}")
    
    print("="*60)
    
    db.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Nightly Adaptive Learning Analysis')
    parser.add_argument('--db', default='data/trading.db', help='Database path')
    args = parser.parse_args()
    
    run_nightly_analysis(args.db)
