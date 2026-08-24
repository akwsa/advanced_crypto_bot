from datetime import datetime

import pandas as pd

from core.database import Database


def test_save_price_history_accepts_pandas_timestamps(tmp_path):
    db = Database(str(tmp_path / "trading.db"))
    candles = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-08-24 10:00:00", "2026-08-24 10:15:00"]),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 11.0],
        }
    )

    assert db.save_price_history("btcidr", candles) == 2

    saved = db.get_price_history("btcidr", limit=10)
    assert len(saved) == 2
    assert saved["timestamp"].tolist() == candles["timestamp"].tolist()


def test_save_price_history_normalizes_datetime_index_and_skips_nat(tmp_path):
    db = Database(str(tmp_path / "trading.db"))
    candles = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 11.0],
        },
        index=pd.DatetimeIndex([datetime(2026, 8, 24, 10, 0), pd.NaT]),
    )

    assert db.save_price_history("ethidr", candles) == 1
    assert len(db.get_price_history("ethidr", limit=10)) == 1
