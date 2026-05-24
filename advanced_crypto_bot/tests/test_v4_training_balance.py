import os
import tempfile
import unittest
from datetime import datetime

import pandas as pd

from analysis.ml_model_v4 import MLTradingModelV4


class _Outcome:
    def __init__(self, label, rec="BUY", price=1000.0, conf=0.7, symbol="BTCIDR"):
        self.signal_price = price
        self.ml_confidence = conf
        self.recommendation = rec
        self.received_at = datetime(2026, 5, 21, 12, 0, 0)
        self.symbol = symbol
        self.label = label


class TestV4TrainingBalance(unittest.TestCase):
    def test_neutral_outcomes_are_capped_per_direction(self):
        fd, path = tempfile.mkstemp(suffix=".pkl")
        os.close(fd)
        os.unlink(path)
        model = MLTradingModelV4(model_path=path)
        rows = []
        rows.extend({"label": "GOOD_BUY"} for _ in range(5))
        rows.extend({"label": "BAD_BUY"} for _ in range(5))
        rows.extend({"label": "NEUTRAL_BUY"} for _ in range(100))
        rows.extend({"label": "GOOD_SELL"} for _ in range(8))
        rows.extend({"label": "BAD_SELL"} for _ in range(7))
        rows.extend({"label": "NEUTRAL_SELL"} for _ in range(120))

        balanced = model._balance_training_frame(pd.DataFrame(rows), neutral_ratio=3, min_neutral_per_side=20)
        counts = balanced["label"].value_counts().to_dict()

        self.assertEqual(counts["GOOD_BUY"], 5)
        self.assertEqual(counts["BAD_BUY"], 5)
        self.assertEqual(counts["GOOD_SELL"], 8)
        self.assertEqual(counts["BAD_SELL"], 7)
        self.assertEqual(counts["NEUTRAL_BUY"], 30)
        self.assertEqual(counts["NEUTRAL_SELL"], 45)
        self.assertTrue(model.last_balance_info["applied"])

    def test_predict_confidence_handles_missing_trained_classes(self):
        outcomes = []
        outcomes.extend(_Outcome("GOOD_BUY", rec="BUY", price=1000 + i, conf=0.8) for i in range(30))
        outcomes.extend(_Outcome("NEUTRAL_BUY", rec="BUY", price=1100 + i, conf=0.6) for i in range(40))

        fd, path = tempfile.mkstemp(suffix=".pkl")
        os.close(fd)
        os.unlink(path)
        try:
            model = MLTradingModelV4(model_path=path)
            self.assertTrue(model.train_from_outcomes(outcomes, test_size=0.25))

            pred, conf = model.predict({
                "signal_price": 1200.0,
                "ml_confidence": 0.75,
                "recommendation": "BUY",
                "hour": 12,
                "dayofweek": 3,
                "symbol": "BTCIDR",
            })

            self.assertIn(pred, {"GOOD_BUY", "NEUTRAL_BUY"})
            self.assertGreaterEqual(conf, 0.0)
            self.assertLessEqual(conf, 1.0)
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
