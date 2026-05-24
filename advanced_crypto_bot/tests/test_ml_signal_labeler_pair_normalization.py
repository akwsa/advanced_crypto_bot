import sqlite3
from datetime import datetime

import pandas as pd

from analysis.ml_signal_trainer import SignalOutcomeLabeler


def test_labeler_loads_price_history_for_normalized_pair_variants(tmp_path):
    signals_db = tmp_path / "signals.db"
    trading_db = tmp_path / "trading.db"

    with sqlite3.connect(signals_db) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                price REAL,
                recommendation TEXT,
                ml_confidence REAL,
                received_at TEXT,
                received_date TEXT,
                combined_strength REAL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO signals (
                id, symbol, price, recommendation, ml_confidence,
                received_at, received_date, combined_strength
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "BTCIDR",
                100.0,
                "BUY",
                0.80,
                "2026-05-21 07:00:00",
                "2026-05-21",
                0.7,
            ),
        )

    with sqlite3.connect(trading_db) as conn:
        conn.execute(
            """
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY,
                pair TEXT,
                timestamp TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL
            )
            """
        )
        # The live DB commonly stores normalized lowercase/no-separator pairs,
        # while signals.db stores uppercase symbols. The labeler must bridge that.
        for idx, high in enumerate([101.0, 102.0, 103.5], start=1):
            conn.execute(
                """
                INSERT INTO price_history (
                    id, pair, timestamp, open, high, low, close, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idx,
                    "btcidr",
                    f"2026-05-21 07:0{idx}:00",
                    100.0,
                    high,
                    99.0,
                    high,
                    10.0,
                ),
            )

    labeler = SignalOutcomeLabeler(str(signals_db), str(trading_db))
    signals = labeler.load_signals(days_back=365)
    outcome = labeler.label_single_signal(signals.iloc[0], tp_pct=3, sl_pct=5, window=10)

    assert outcome.label == "GOOD_BUY"
    assert outcome.candles_checked == 3
    assert outcome.hit_tp is True
