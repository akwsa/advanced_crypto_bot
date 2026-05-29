import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from autohunter.smart_profit_hunter import SmartProfitHunter, STOP_LOSS


class _RowLikeFrame:
    def __init__(self, df):
        self._df = df

    @property
    def empty(self):
        return self._df.empty

    def __len__(self):
        return len(self._df)

    def iterrows(self):
        return self._df.iterrows()

    def tail(self, n):
        return _RowLikeFrame(self._df.tail(n))


class _HistoricalData(dict):
    def __contains__(self, key):
        return super().__contains__(key) or super().__contains__(key.upper())

    def __getitem__(self, key):
        if super().__contains__(key):
            return super().__getitem__(key)
        return super().__getitem__(key.upper())

    def get(self, key, default=None):
        if super().__contains__(key):
            return super().get(key, default)
        return super().get(key.upper(), default)


def _build_hunter():
    hunter = SmartProfitHunter(dry_run=True)
    hunter.send_notification = AsyncMock(return_value=None)
    hunter.create_sell_order = MagicMock(return_value="sell-order-1")
    return hunter


def _sample_trade():
    return {
        "pair_id": "btcidr",
        "entry_price": 1000.0,
        "coin_amount": 10.0,
        "sold_50": False,
        "sold_30": False,
        "sold_20": False,
    }


def test_partial_sell_reduces_remaining_coin_and_updates_pnl_and_balance():
    hunter = _build_hunter()
    hunter.balance_idr = 5000.0
    hunter.daily_pnl = 0.0
    trade = _sample_trade()
    hunter.active_trades["BTC/IDR"] = dict(trade)

    asyncio.run(
        hunter.partial_sell(
            "BTC/IDR",
            hunter.active_trades["BTC/IDR"],
            price=1100.0,
            percent=0.5,
            reason="Take Profit 1 (+3%)",
        )
    )

    remaining = hunter.active_trades["BTC/IDR"]["coin_amount"]
    assert remaining == 5.0
    assert hunter.active_trades["BTC/IDR"]["sold_50"] is True
    assert hunter.daily_pnl == 500.0
    assert hunter.balance_idr == 10500.0
    hunter.send_notification.assert_called_once()
    sent_message = hunter.send_notification.await_args.args[0]
    assert "Remaining: `5.00` coins" in sent_message


def test_dynamic_risk_reward_uses_support_and_resistance_when_available():
    hunter = _build_hunter()
    df = pd.DataFrame(
        {
            "open": [100.0] * 60,
            "high": [101.0] * 60,
            "low": [99.0] * 60,
            "close": [100.0] * 60,
            "volume": [1000.0] * 60,
        }
    )
    hunter.main_bot = SimpleNamespace(
        historical_data=_HistoricalData({"BTCIDR": _RowLikeFrame(df)}),
        sr_detector=SimpleNamespace(
            detect_levels=lambda _df: {
                "nearest_support": 95.0,
                "nearest_resistance": 120.0,
            }
        ),
    )

    rr, stop_loss, take_profit = hunter._compute_dynamic_risk_reward(100.0, "btcidr")

    assert stop_loss == 95.0 * 0.995
    assert take_profit == 120.0 * 0.995
    expected_risk = 100.0 - stop_loss
    expected_reward = take_profit - 100.0
    assert rr == round(expected_reward / expected_risk, 2)


def test_dynamic_risk_reward_falls_back_to_fixed_percentages_when_sr_invalid():
    hunter = _build_hunter()
    df = pd.DataFrame(
        {
            "open": [100.0] * 60,
            "high": [101.0] * 60,
            "low": [99.0] * 60,
            "close": [100.0] * 60,
            "volume": [1000.0] * 60,
        }
    )
    hunter.main_bot = SimpleNamespace(
        historical_data=_HistoricalData({"BTCIDR": _RowLikeFrame(df)}),
        sr_detector=SimpleNamespace(
            detect_levels=lambda _df: {
                "nearest_support": 105.0,
                "nearest_resistance": 110.0,
            }
        ),
    )

    rr, stop_loss, take_profit = hunter._compute_dynamic_risk_reward(100.0, "btcidr")

    expected_stop_loss = 100.0 * (1 + STOP_LOSS / 100)
    expected_take_profit = 100.0 * 1.05
    expected_risk = 100.0 - expected_stop_loss
    expected_reward = expected_take_profit - 100.0
    assert stop_loss == expected_stop_loss
    assert take_profit == expected_take_profit
    assert rr == round(expected_reward / expected_risk, 2)


def test_get_candles_prefers_main_bot_ohlcv_data_before_api_fallback():
    hunter = _build_hunter()
    df = pd.DataFrame(
        {
            "open": [1.0] * 25,
            "high": [2.0] * 25,
            "low": [0.5] * 25,
            "close": [1.5] * 25,
            "volume": [123.0] * 25,
            "timestamp": list(range(25)),
        }
    )
    hunter.main_bot = SimpleNamespace(
        historical_data=_HistoricalData({"BTCIDR": _RowLikeFrame(df)})
    )

    candles = hunter.get_candles("btc_idr", limit=3)

    assert len(candles) == 3
    assert candles[0]["open"] == 1.0
    assert candles[0]["high"] == 2.0
    assert candles[0]["low"] == 0.5
    assert candles[0]["price"] == 1.5
    assert candles[0]["volume"] == 123.0
    hunter.session.get = MagicMock()
    hunter.session.get.assert_not_called()
