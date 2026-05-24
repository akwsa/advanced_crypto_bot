import os
import unittest
from unittest.mock import patch

import core.config as config_module
from core.config import Config


class TestConfigNormalization(unittest.TestCase):
    def test_get_pair_symbol_normalizes_separators_and_aliases(self):
        self.assertEqual(Config.get_pair_symbol("BTC/IDR"), "btcidr")
        self.assertEqual(Config.get_pair_symbol("ETH_IDR"), "ethidr")
        self.assertEqual(Config.get_pair_symbol("solvidr"), "solidr")
        self.assertEqual(Config.get_pair_symbol("soliddr"), "solidr")

    def test_parse_watch_pairs_deduplicates_and_aliases_sol(self):
        pairs = config_module._parse_watch_pairs("BTC/IDR, btcidr, solvidr, soliddr, solidr")
        self.assertEqual(pairs, ["btcidr", "solidr"])

    def test_default_watch_pairs_use_solidr_not_solvidr(self):
        self.assertIn("solidr", Config.WATCH_PAIRS)
        self.assertNotIn("solvidr", Config.WATCH_PAIRS)
        self.assertNotIn("soliddr", Config.WATCH_PAIRS)

    def test_timezone_defaults_are_wib(self):
        self.assertEqual(Config.TRADING_TIMEZONE_OFFSET, 7)
        self.assertEqual(Config.TRADING_TIMEZONE_LABEL, "WIB")


if __name__ == "__main__":
    unittest.main()
