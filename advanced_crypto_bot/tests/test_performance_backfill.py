import os
import tempfile
import unittest

from analysis.backfill_performance_metrics import run_backfill
from core.database import Database


class TestPerformanceBackfill(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.db_path)
        self.db.add_user(1, "tester", "Tester")

    def tearDown(self):
        self.db.close_thread_connection()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_close_trade_updates_daily_performance_with_explicit_pnl(self):
        trade_id = self.db.add_trade(
            user_id=1,
            pair="btcidr",
            trade_type="BUY",
            price=100_000.0,
            amount=2.0,
            total=200_000.0,
            fee=0.0,
            signal_source="TEST",
            ml_confidence=0.9,
        )

        self.assertTrue(self.db.close_trade(trade_id, close_price=110.0, pnl=20.0, pnl_pct=10.0))

        perf = self.db.get_performance(1, days=7)
        self.assertEqual(len(perf), 1)
        self.assertEqual(perf[0]["total_trades"], 1)
        self.assertEqual(perf[0]["winning_trades"], 1)
        self.assertEqual(perf[0]["losing_trades"], 0)
        self.assertAlmostEqual(perf[0]["total_profit_loss"], 20.0)
        self.assertAlmostEqual(perf[0]["win_rate"], 100.0)

    def test_close_trade_legacy_sell_signature_computes_pnl_and_updates_performance(self):
        trade_id = self.db.add_trade(
            user_id=1,
            pair="ethidr",
            trade_type="BUY",
            price=50.0,
            amount=4.0,
            total=200.0,
            fee=0.0,
            signal_source="TEST",
            ml_confidence=0.8,
        )

        self.assertTrue(
            self.db.close_trade(
                trade_id=trade_id,
                sell_price=45.0,
                sell_amount=4.0,
                order_id="SIM-1",
                reason="Auto-SELL",
            )
        )

        trade = self.db.get_trade(trade_id)
        self.assertEqual(trade["status"], "CLOSED")
        self.assertAlmostEqual(trade["profit_loss"], -20.0)
        self.assertAlmostEqual(trade["profit_loss_pct"], -10.0)

        perf = self.db.get_performance(1, days=7)
        self.assertEqual(len(perf), 1)
        self.assertEqual(perf[0]["total_trades"], 1)
        self.assertEqual(perf[0]["winning_trades"], 0)
        self.assertEqual(perf[0]["losing_trades"], 1)
        self.assertAlmostEqual(perf[0]["total_profit_loss"], -20.0)
        self.assertAlmostEqual(perf[0]["win_rate"], 0.0)

    def test_backfill_rebuilds_profit_feedback_from_fifo_matched_sell_rows(self):
        self.db.add_trade(
            user_id=1,
            pair="btcidr",
            trade_type="BUY",
            price=100_000.0,
            amount=2.0,
            total=200_000.0,
            fee=0.0,
            signal_source="INDODAX",
            ml_confidence=0.75,
        )
        sell_id = self.db.add_indodax_trade(
            user_id=1,
            pair="btcidr",
            trade_type="SELL",
            price=120_000.0,
            amount=1.5,
            total=180_000.0,
            fee=0.0,
            indodax_order_id="SELL-1",
            timestamp="2026-04-26 10:00:00",
            notes=None,
        )

        result = run_backfill(self.db_path)

        self.assertEqual(result["legacy_sell_rows_rebuilt"], 1)
        self.assertEqual(result["skipped_invalid"], 0)

        trade = self.db.get_trade(sell_id)
        self.assertEqual(trade["status"], "CLOSED")
        self.assertAlmostEqual(trade["profit_loss"], 30_000.0)
        self.assertAlmostEqual(trade["profit_loss_pct"], 20.0)
        self.assertIsNotNone(trade["closed_at"])

        perf = self.db.get_performance(1, days=30)
        self.assertEqual(len(perf), 1)
        self.assertEqual(perf[0]["total_trades"], 1)
        self.assertEqual(perf[0]["winning_trades"], 1)

        pair_perf = self.db.get_pair_performance("btcidr")
        self.assertIsNotNone(pair_perf)
        self.assertEqual(pair_perf["total_trades"], 1)
        self.assertEqual(pair_perf["win_count"], 1)
        self.assertAlmostEqual(pair_perf["profit_factor"], float("inf"))

        review = self.db.get_trade_review(sell_id)
        self.assertIsNotNone(review)
        self.assertAlmostEqual(review["entry_price"], 100_000.0)
        self.assertAlmostEqual(review["exit_price"], 120_000.0)

        with self.db.get_connection() as conn:
            outcome = conn.execute(
                "SELECT * FROM trade_outcomes WHERE trade_id = ?",
                (sell_id,),
            ).fetchone()
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["outcome_label"], "GOOD_BUY")

    def test_backfill_skips_invalid_tiny_legacy_sell_rows(self):
        self.db.add_trade(
            user_id=1,
            pair="btcidr",
            trade_type="BUY",
            price=100_000_000.0,
            amount=1.0,
            total=100_000_000.0,
            fee=0.0,
            signal_source="INDODAX",
            ml_confidence=0.7,
        )
        self.db.add_indodax_trade(
            user_id=1,
            pair="btcidr",
            trade_type="SELL",
            price=1.0,
            amount=0.1,
            total=0.1,
            fee=0.0,
            indodax_order_id="BAD-SELL",
            timestamp="2026-04-24 11:00:00",
            notes=None,
        )

        result = run_backfill(self.db_path)

        self.assertEqual(result["legacy_sell_rows_rebuilt"], 0)
        self.assertEqual(result["skipped_invalid"], 1)
        self.assertEqual(self.db.get_all_pair_performance(min_trades=0), [])
