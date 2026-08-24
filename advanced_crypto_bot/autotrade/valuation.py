"""Pure canonical valuation for Strategy 1 normalized dry-run portfolios."""

from __future__ import annotations

import math
from datetime import datetime


def _pair_key(value) -> str:
    return str(value or '').replace('/', '').replace('_', '').lower()


def _timestamp_seconds(value) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    return float(value)


def value_normalized_equity(*, cash, positions, price_data, now_ts,
                            max_age_seconds, max_future_skew_seconds=5.0):
    """Return cash + fresh executable-bid value, or an unavailable result."""
    cash = float(cash)
    now_ts = float(now_ts)
    max_age_seconds = float(max_age_seconds)
    max_future_skew_seconds = float(max_future_skew_seconds)
    open_value = 0.0
    marks = []
    unavailable = []
    normalized_prices = {_pair_key(key): value for key, value in (price_data or {}).items()}

    for position in positions:
        pair = _pair_key(position['pair'])
        price_row = normalized_prices.get(pair) or {}
        try:
            bid = float(price_row.get('bid'))
        except (TypeError, ValueError):
            bid = 0.0
        try:
            mark_ts = _timestamp_seconds(price_row.get('timestamp'))
            age_seconds = now_ts - mark_ts
        except (TypeError, ValueError, OverflowError):
            age_seconds = float('inf')
        if not math.isfinite(bid) or bid <= 0:
            unavailable.append({'pair': pair, 'reason': 'missing_bid'})
            continue
        if not math.isfinite(age_seconds) or age_seconds > max_age_seconds:
            unavailable.append({
                'pair': pair, 'reason': 'stale_mark', 'age_seconds': age_seconds,
            })
            continue
        if age_seconds < -max_future_skew_seconds:
            unavailable.append({
                'pair': pair, 'reason': 'future_mark', 'age_seconds': age_seconds,
            })
            continue
        quantity = float(position['quantity'])
        value = bid * quantity
        open_value += value
        marks.append({
            'pair': pair,
            'bid': bid,
            'quantity': quantity,
            'value': value,
            'age_seconds': max(0.0, age_seconds),
        })

    if unavailable:
        return {
            'available': False,
            'equity': None,
            'cash': cash,
            'open_value': None,
            'marks': marks,
            'unavailable': unavailable,
        }
    return {
        'available': True,
        'equity': cash + open_value,
        'cash': cash,
        'open_value': open_value,
        'marks': marks,
        'unavailable': [],
    }

