#!/usr/bin/env python3
"""
Test Adaptive Learning Engine
==============================
Run: ./venv/bin/python tests/test_adaptive_learning.py -v
"""

import unittest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.database import Database
from analysis.adaptive_learning import AdaptiveLearningEngine, PairPerformanceMetrics


class TestAdaptiveLearningEngine(unittest.TestCase):
    """Test adaptive learning engine."""

    def setUp(self):
        self.db = Database(':memory:')
        self.engine = AdaptiveLearningEngine(self.db)
        
        # Seed some trades
        for i in range(5):
            # Winning trades
            tid = self.db.add_trade(1, 'btcidr', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.8)
            self.db.close_trade(tid, close_price=1100, pnl=100, pnl_pct=10.0)
        
        for i in range(3):
            # Losing trades
            tid = self.db.add_trade(1, 'btcidr', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.6)
            self.db.close_trade(tid, close_price=950, pnl=-50, pnl_pct=-5.0)

    def tearDown(self):
        self.db.close()

    def test_analyze_pair_performance(self):
        """Engine harus bisa analisis performa pair."""
        metrics = self.engine.analyze_pair_performance('btcidr', days=7)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.pair, 'btcidr')
        self.assertEqual(metrics.total_trades, 8)
        self.assertEqual(metrics.win_count, 5)
        self.assertEqual(metrics.loss_count, 3)
        self.assertAlmostEqual(metrics.win_rate, 5/8, places=2)

    def test_update_and_get_adaptive_thresholds(self):
        """Thresholds harus tersimpan dan bisa di-retrieve."""
        metrics = self.engine.analyze_pair_performance('btcidr', days=7)
        self.engine.update_adaptive_thresholds(metrics)
        
        thresholds = self.engine.get_adaptive_thresholds('btcidr')
        self.assertIn('confidence_threshold_buy', thresholds)
        self.assertIn('position_size_multiplier', thresholds)
        self.assertFalse(thresholds['skip_pair'])

    def test_skip_pair_when_unprofitable(self):
        """Pair dengan PF < 1.0 harus di-skip."""
        # Add many losing trades
        for i in range(10):
            tid = self.db.add_trade(1, 'badpair', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.5)
            self.db.close_trade(tid, close_price=900, pnl=-100, pnl_pct=-10.0)
        
        metrics = self.engine.analyze_pair_performance('badpair', days=7)
        self.engine.update_adaptive_thresholds(metrics)
        
        thresholds = self.engine.get_adaptive_thresholds('badpair')
        self.assertTrue(thresholds['skip_pair'])

    def test_record_trade_outcome(self):
        """Trade outcome harus tersimpan untuk V4 training."""
        self.engine.record_trade_outcome(
            trade_id=9999, pair='manualpair', entry_price=1000,
            exit_price=1100, ml_confidence=0.75,
            recommendation='BUY', pnl_pct=10.0,
            hold_duration_minutes=120
        )
        
        data = self.engine.get_v4_training_data(days=7)
        manual_outcomes = [o for o in data if o['pair'] == 'manualpair']
        self.assertEqual(len(manual_outcomes), 1)
        self.assertEqual(manual_outcomes[0]['outcome_label'], 'GOOD_BUY')

    def test_record_regime(self):
        """Regime history harus tersimpan."""
        self.engine.record_regime('btcidr', 'TRENDING_UP', 0.05, 'UP')
        history = self.engine.get_regime_history('btcidr')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['regime'], 'TRENDING_UP')

    def test_trade_outcomes_auto_recorded_on_close(self):
        """Database.close_trade() harus auto-record ke trade_outcomes."""
        tid = self.db.add_trade(1, 'ethidr', 'BUY', 500, 2.0, 1000, 3, 'test', 0.7)
        self.db.close_trade(tid, close_price=550, pnl=100, pnl_pct=10.0)
        
        outcomes = self.engine.get_v4_training_data(days=7)
        eth_outcomes = [o for o in outcomes if o['pair'] == 'ethidr']
        self.assertEqual(len(eth_outcomes), 1)
        self.assertEqual(eth_outcomes[0]['outcome_label'], 'GOOD_BUY')


if __name__ == '__main__':
    unittest.main(verbosity=2)
