#!/usr/bin/env python3
"""Read-only canonical equity and projection-drift audit."""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.indodax_api import IndodaxAPI
from autotrade.valuation import value_normalized_equity
from core.config import Config
from core.database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/trading.db')
    parser.add_argument('--user-id', type=int, required=True)
    args = parser.parse_args()

    db = Database(args.db)
    positions = db.get_open_autotrade_positions(args.user_id)
    prices = {}
    api = IndodaxAPI()
    for position in positions:
        pair = str(position['pair']).replace('/', '').replace('_', '').lower()
        ticker = api.get_ticker(pair)
        if ticker:
            prices[pair] = {'bid': ticker.get('bid'), 'timestamp': ticker.get('timestamp')}
    valuation = value_normalized_equity(
        cash=db.get_balance(args.user_id),
        positions=positions,
        price_data=prices,
        now_ts=time.time(),
        max_age_seconds=Config.AUTOTRADE_EQUITY_MARK_MAX_AGE_SECONDS,
    )
    report = db.audit_autotrade_projection_drift(args.user_id)
    report['valuation'] = valuation
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == '__main__':
    main()
