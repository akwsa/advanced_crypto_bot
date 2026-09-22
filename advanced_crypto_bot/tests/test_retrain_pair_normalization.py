import unittest

import pandas as pd

from bot import AdvancedCryptoBot


class _FakeTrainingDb:
    def __init__(self):
        self.frames = {
            "BTCIDR": pd.DataFrame(
                [
                    {
                        "pair": "BTCIDR",
                        "timestamp": "2026-04-01 00:00:00",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 10,
                    }
                ]
            ),
            "btcidr": pd.DataFrame(
                [
                    {
                        "pair": "btcidr",
                        "timestamp": "2026-04-01 00:01:00",
                        "open": 2,
                        "high": 2,
                        "low": 2,
                        "close": 2,
                        "volume": 20,
                    }
                ]
            ),
            "BTC_IDR": pd.DataFrame(
                [
                    {
                        "pair": "BTC_IDR",
                        "timestamp": "2026-04-01 00:02:00",
                        "open": 3,
                        "high": 3,
                        "low": 3,
                        "close": 3,
                        "volume": 30,
                    }
                ]
            ),
        }

    def get_all_pairs(self):
        return list(self.frames)

    def get_all_watchlists(self):
        return {1: ["BTC/IDR"]}

    def get_price_history(self, pair, limit=2000):
        return self.frames.get(pair, pd.DataFrame()).copy()


class TestRetrainPairNormalization(unittest.TestCase):
    def test_collect_training_data_groups_pair_variants(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.db = _FakeTrainingDb()

        frames, summary = bot._collect_normalized_training_data(
            pairs_to_check=None,
            include_small_groups=True,
            include_zero_summary=True,
        )

        self.assertEqual(summary, ["• `BTCIDR`: 3 candles"])
        self.assertEqual(len(frames), 1)
        self.assertEqual(len(frames[0]), 3)
        self.assertEqual(set(frames[0]["pair"]), {"btcidr"})


if __name__ == "__main__":
    unittest.main()
