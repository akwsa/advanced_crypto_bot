from datetime import datetime
from types import SimpleNamespace

import pytest

from bot import AdvancedCryptoBot
from core.config import Config
from core.database import Database


def _bot_with(db, price_data):
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    bot.db = db
    bot.price_data = price_data
    bot.entry_circuit_breaker_active = False
    bot.is_trading = True
    return bot


def test_canonical_equity_uses_normalized_positions_not_legacy(tmp_path):
    db = Database(str(tmp_path / 'trading.db'))
    db.add_user(1, 'tester', 'Test')
    db.update_balance(1, 43_000_000)
    with db.get_connection() as conn:
        conn.execute('''INSERT INTO autotrade_positions
            (pair,user_id,quantity,avg_price,cost_basis,fees,status)
            VALUES ('btcidr',1,2,3000000,6000000,18000,'OPEN')''')
        conn.execute('''INSERT INTO trades
            (user_id,pair,type,price,amount,total,fee,signal_source,status)
            VALUES (1,'btcidr','BUY',3000000,0,0,0,'auto','CLOSED')''')
    now = datetime.now()
    bot = _bot_with(db, {'btcidr': {'bid': 3_100_000, 'last': 3_200_000, 'timestamp': now}})

    valuation = bot._calculate_canonical_equity(1, now=now.timestamp())

    assert valuation['available'] is True
    assert valuation['open_value'] == 6_200_000
    assert valuation['equity'] == 49_200_000
    assert bot._calculate_equity(1) == pytest.approx(49_200_000)


@pytest.mark.parametrize('price_fields,mark_offset_seconds,reason', [
    ({'last': 3_200_000}, 0, 'missing_bid'),
    ({'bid': 3_100_000}, -301, 'stale_mark'),
    ({'bid': 3_100_000}, 6, 'future_mark'),
], ids=['missing-bid', 'stale-mark', 'future-mark'])
def test_canonical_equity_fails_closed_without_fresh_bid(
    tmp_path, monkeypatch, price_fields, mark_offset_seconds, reason,
):
    reference_time = 1_800_000_000.0
    monkeypatch.setattr('bot.time.time', lambda: reference_time)
    monkeypatch.setattr(Config, 'AUTOTRADE_EQUITY_MARK_MAX_AGE_SECONDS', 300)
    db = Database(str(tmp_path / 'trading.db'))
    db.add_user(1, 'tester', 'Test')
    with db.get_connection() as conn:
        conn.execute('''INSERT INTO autotrade_positions
            (pair,user_id,quantity,avg_price,cost_basis,fees,status)
            VALUES ('btcidr',1,1,100,100,0,'OPEN')''')
    price_data = {
        'btcidr': {
            **price_fields,
            'timestamp': reference_time + mark_offset_seconds,
        },
    }
    bot = _bot_with(db, price_data)
    original_peak = db.get_equity_peak(1)

    allowed, message = bot._check_max_drawdown(1)

    assert allowed is False
    assert f'btcidr:{reason}' in message
    assert db.get_equity_peak(1) == original_peak
    assert bot.is_trading is True
    assert bot.entry_circuit_breaker_active is True


def test_drawdown_blocks_entries_without_disabling_automation(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'trading.db'))
    db.add_user(1, 'tester', 'Test')
    db.update_balance(1, 40_000_000)
    db.set_equity_peak(1, 50_000_000)
    bot = _bot_with(db, {})
    monkeypatch.setattr(Config, 'MAX_DRAWDOWN_PCT', 0.10)

    allowed, message = bot._check_max_drawdown(1)

    assert allowed is False
    assert '20.0%' in message
    assert bot.is_trading is True
    assert bot.entry_circuit_breaker_active is True


def test_drawdown_check_fails_closed_on_valuation_error():
    bot = _bot_with(SimpleNamespace(), {})

    allowed, message = bot._check_max_drawdown(1)

    assert allowed is False
    assert 'valuation_error' in message
    assert bot.is_trading is True
    assert bot.entry_circuit_breaker_active is True


def test_projection_drift_audit_is_read_only_and_specific(tmp_path):
    db = Database(str(tmp_path / 'trading.db'))
    db.add_user(1, 'tester', 'Test')
    with db.get_connection() as conn:
        conn.execute('''INSERT INTO autotrade_positions
            (pair,user_id,quantity,avg_price,cost_basis,fees,status)
            VALUES ('aceidr',1,2,100,200,1,'OPEN')''')
        conn.execute('''INSERT INTO trades
            (user_id,pair,type,price,amount,total,fee,signal_source,status)
            VALUES (1,'aceidr','BUY',100,0,0,0,'auto','CLOSED')''')

    report = db.audit_autotrade_projection_drift(1)

    assert report['normalized_open_count'] == 1
    assert report['legacy_open_count'] == 0
    assert report['normalized_open_cost_basis'] == 200
    assert report['mismatches'] == [{
        'pair': 'aceidr',
        'legacy_open': False,
        'legacy_quantity': 0.0,
        'normalized_open': True,
        'normalized_quantity': 2.0,
    }]


def test_normalized_position_lookup_and_sell_normalize_pair_variants(tmp_path):
    db = Database(str(tmp_path / 'trading.db'))
    db.add_user(1, 'tester', 'Test')
    db.update_balance(1, 1_000)
    with db.get_connection() as conn:
        conn.execute('''INSERT INTO autotrade_positions
            (pair,user_id,quantity,avg_price,cost_basis,fees,status)
            VALUES ('BTC/IDR',1,2,100,200,0,'OPEN')''')

    assert db.get_autotrade_position('btc_idr', 1)['quantity'] == 2
    assert db.record_dryrun_sell(
        fill_key='normalized-pair-sell', order_id='S-NORM', pair='btcidr',
        user_id=1, price=110, quantity=2, fee=0,
    ) is True
    assert db.get_autotrade_position('BTCIDR', 1)['status'] == 'CLOSED'


def test_atomic_close_normalizes_legacy_and_position_pair_variants(tmp_path):
    db = Database(str(tmp_path / 'trading.db'))
    db.add_user(1, 'tester', 'Test')
    with db.get_connection() as conn:
        trade_id = conn.execute('''INSERT INTO trades
            (user_id,pair,type,price,amount,total,fee,signal_source,status)
            VALUES (1,'BTC/IDR','BUY',100,2,200,0,'auto','OPEN')''').lastrowid
        conn.execute('''INSERT INTO autotrade_positions
            (pair,user_id,quantity,avg_price,cost_basis,fees,status)
            VALUES ('btc_idr',1,2,100,200,0,'OPEN')''')

    assert db.close_atomic_dryrun_position(
        trade_id=trade_id,
        fill_key='normalized-atomic-close',
        order_id='S-ATOMIC-NORM',
        pair='btcidr',
        user_id=1,
        sell_price=110,
        quantity=2,
        fee=0,
        reason='test',
        pnl=20,
        pnl_pct=10,
    ) is True
    assert db.get_trade(trade_id)['status'] == 'CLOSED'
    assert db.get_autotrade_position('BTC/IDR', 1)['status'] == 'CLOSED'
