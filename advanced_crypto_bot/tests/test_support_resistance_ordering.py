import unittest
import sys
import types

sys.modules.setdefault("numpy", types.SimpleNamespace())
sys.modules.setdefault("pandas", types.SimpleNamespace(DataFrame=object))
sys.modules.setdefault("scipy", types.SimpleNamespace())
sys.modules.setdefault("scipy.signal", types.SimpleNamespace(argrelextrema=lambda *args, **kwargs: []))
from analysis.support_resistance import SupportResistanceDetector


class TestSupportResistanceOrdering(unittest.TestCase):
    def setUp(self):
        self.detector = SupportResistanceDetector()

    def test_normalize_resistance_nearest_level_first(self):
        levels = self.detector._normalize_levels(
            {
                "support_1": 4350,
                "support_2": 4261,
                "resistance_1": 4528,
                "resistance_2": 4455,
            },
            current_price=4439,
        )

        self.assertEqual(levels["support_1"], 4350)
        self.assertEqual(levels["support_2"], 4261)
        self.assertEqual(levels["resistance_1"], 4455)
        self.assertEqual(levels["resistance_2"], 4528)

    def test_normalize_jellyjelly_example_resistance_order(self):
        levels = self.detector._normalize_levels(
            {
                "support_1": 1120,
                "support_2": 1119,
                "resistance_1": 1127,
                "resistance_2": 1122,
            },
            current_price=1121,
        )

        self.assertEqual(levels["support_1"], 1120)
        self.assertEqual(levels["support_2"], 1119)
        self.assertEqual(levels["resistance_1"], 1122)
        self.assertEqual(levels["resistance_2"], 1127)


if __name__ == "__main__":
    unittest.main()
