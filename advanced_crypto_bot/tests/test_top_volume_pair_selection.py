# Tujuan: Regression tests untuk top-volume pair selection helper / filter volume minimum.
# Caller: unittest/pytest focused runtime pair selection behavior.
# Dependensi: bot.AdvancedCryptoBot dengan fake ticker snapshot.

import unittest
from types import SimpleNamespace

from bot import AdvancedCryptoBot


class TestTopVolumePairSelection(unittest.TestCase):
    def _bot(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.indodax = SimpleNamespace()
        return bot

    def test_selects_top_50_idr_pairs_above_500m_volume(self):
        bot = self._bot()
        tickers = []
        for i in range(60):
            tickers.append({
                "pair": f"coin{i}idr",
                "volume": 2_000_000_000 - (i * 10_000_000),
                "last": 1000 + i,
            })
        tickers.extend([
            {"pair": "tinyidr", "volume": 499_999_999, "last": 1},
            {"pair": "mediumusdt", "volume": 9_000_000_000, "last": 1},
        ])

        selected = bot._select_top_volume_pairs(tickers, limit=50, min_volume_idr=500_000_000)

        self.assertEqual(len(selected), 50)
        self.assertEqual(selected[0]["pair"], "coin0idr")
        self.assertEqual(selected[-1]["pair"], "coin49idr")
        self.assertTrue(all(item["pair"].endswith("idr") for item in selected))
        self.assertTrue(all(float(item["volume"]) > 500_000_000 for item in selected))

    def test_ignores_pairs_at_or_below_volume_threshold_for_watchlist_seed(self):
        bot = self._bot()
        tickers = [
            {"pair": "btcidr", "volume": 5_000_000_000, "last": 1},
            {"pair": "ethidr", "volume": 1_500_000_000, "last": 1},
            {"pair": "xrpidr", "volume": 1_000_000_000, "last": 1},
            {"pair": "dogeidr", "volume": 999_999_999, "last": 1},
            {"pair": "pepeusdt", "volume": 9_999_999_999, "last": 1},
        ]

        selected = bot._select_top_volume_pairs(tickers, limit=50, min_volume_idr=1_000_000_000)
        pairs = [item["pair"] for item in selected]

        self.assertEqual(pairs, ["btcidr", "ethidr"])


if __name__ == "__main__":
    unittest.main()
