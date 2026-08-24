#!/usr/bin/env python3
"""Report durable autotrade decision-funnel health from SQLite."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import build_autotrade_funnel_report


def _sqlite_timestamp(value):
    return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/trading.db')
    parser.add_argument('--hours', type=float, default=24.0)
    parser.add_argument('--user-id', type=int)
    parser.add_argument('--max-generic-rate', type=float, default=0.005)
    parser.add_argument('--json', action='store_true', help='Retained for explicit machine-readable usage.')
    args = parser.parse_args()
    if not math.isfinite(args.hours) or args.hours <= 0:
        parser.error('--hours must be finite and greater than zero')
    if not math.isfinite(args.max_generic_rate) or not 0 <= args.max_generic_rate <= 1:
        parser.error('--max-generic-rate must be finite and between zero and one')

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=args.hours)
    db_path = os.path.abspath(args.db)
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            report = build_autotrade_funnel_report(
                conn,
                user_id=args.user_id,
                start_at=_sqlite_timestamp(start),
                end_at=_sqlite_timestamp(end),
            )
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc), 'database': db_path}, sort_keys=True), file=sys.stderr)
        return 1

    generic_rate = report['integrity']['generic_rate']
    report['integrity']['max_generic_rate'] = args.max_generic_rate
    report['integrity']['passed'] = generic_rate <= args.max_generic_rate
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['integrity']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
