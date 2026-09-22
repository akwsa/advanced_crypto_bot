import sqlite3
import tempfile
import unittest
from contextlib import contextmanager

from api.tma_server import TMADataProvider
from core.database import Database


class SimpleDb:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def get_connection(self):
        yield self.conn


class TestTMADataProvider(unittest.TestCase):
    def test_heatmap_supports_core_database_signal_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            db = Database(tmp.name)
            with db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO signals
                    (pair, signal_type, price, confidence, indicators, ml_prediction, recommendation)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("btcidr", "BUY", 100.0, 0.72, "{}", "BUY", "BUY"),
                )

            rows = TMADataProvider(db).get_signal_heatmap()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["pair"], "btcidr")
            self.assertEqual(rows[0]["recommendation"], "BUY")
            self.assertAlmostEqual(rows[0]["ml_confidence"], 0.72)
            self.assertEqual(rows[0]["combined_strength"], 0.0)
            db.close()

    def test_heatmap_supports_signal_database_schema(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE signals (
                symbol TEXT,
                price REAL,
                recommendation TEXT,
                ml_confidence REAL,
                combined_strength REAL,
                received_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO signals
            (symbol, price, recommendation, ml_confidence, combined_strength, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ethidr", 200.0, "SELL", 0.81, -0.44, "2026-04-25 08:04:08"),
        )

        rows = TMADataProvider(SimpleDb(conn)).get_signal_heatmap()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pair"], "ethidr")
        self.assertEqual(rows[0]["recommendation"], "SELL")
        self.assertAlmostEqual(rows[0]["ml_confidence"], 0.81)
        self.assertAlmostEqual(rows[0]["combined_strength"], -0.44)
        conn.close()


if __name__ == "__main__":
    unittest.main()

