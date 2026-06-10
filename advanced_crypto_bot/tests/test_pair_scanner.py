"""Tests untuk autohunter/pair_scanner.py."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from autohunter import pair_scanner  # noqa: E402
from autohunter.pair_scanner import (  # noqa: E402
    PairSnapshot,
    build_watchlist_recommendation,
    scan_top_movers,
    scan_top_volume,
)


def _ticker(pair, last, high, low, bid, ask, volume, change=None):
    return {
        "pair": pair,
        "last": last,
        "high": high,
        "low": low,
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "change_percent": change,
    }


class _FakeAPI:
    def __init__(self, tickers):
        self._tickers = tickers

    def get_all_tickers(self):
        return self._tickers


class PairSnapshotTests(unittest.TestCase):
    def setUp(self):
        pair_scanner._cache_invalidate()

    def test_display_pair_format(self):
        s = PairSnapshot("btcidr", 100, 110, 90, 99, 100, 1e9, 5.0)
        self.assertEqual(s.display_pair, "BTC/IDR")

    def test_spread_pct_calc(self):
        s = PairSnapshot("btcidr", 100, 110, 90, 99, 101, 1e9, 5.0)
        self.assertAlmostEqual(s.spread_pct, 2.0, places=2)

    def test_spread_pct_invalid_when_bid_gt_ask(self):
        s = PairSnapshot("btcidr", 100, 110, 90, 105, 99, 1e9, 5.0)
        self.assertIsNone(s.spread_pct)

    def test_distance_from_high_zero_at_peak(self):
        s = PairSnapshot("btcidr", 100, 100, 90, 99, 100, 1e9, None)
        self.assertAlmostEqual(s.distance_from_high_pct, 0.0)

    def test_distance_from_high_5pct_below(self):
        s = PairSnapshot("btcidr", 95, 100, 90, 94, 96, 1e9, None)
        self.assertAlmostEqual(s.distance_from_high_pct, 5.0)


class ScanTopVolumeTests(unittest.TestCase):
    def setUp(self):
        pair_scanner._cache_invalidate()

    def test_returns_top_pairs_by_volume(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9, 2.5),
            _ticker("ethidr", 5e7, 5.5e7, 4.5e7, 4.9e7, 5.1e7, 50e9, 3.0),
            _ticker("solidr", 1e6, 1.1e6, 0.9e6, 0.99e6, 1.01e6, 30e9, 1.5),
            _ticker("xrpidr", 20000, 22000, 18000, 19500, 20100, 10e9, 5.0),
            _ticker("dogeidr", 300, 320, 280, 290, 305, 5e9, 8.0),
        ])
        result = scan_top_volume(api, limit=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].pair, "btcidr")
        self.assertEqual(result[0].rank, 1)
        self.assertEqual(result[1].pair, "ethidr")
        self.assertEqual(result[2].pair, "solidr")
        for s in result:
            self.assertIn("TOP_VOLUME", s.badges)

    def test_filters_below_min_volume(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9),
            _ticker("dustidr", 1, 1.1, 0.9, 0.99, 1.01, 100_000),  # 100K vs default 100M
        ])
        result = scan_top_volume(api, limit=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pair, "btcidr")

    def test_skips_non_idr_markets(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9),
            _ticker("btc_usdt", 60000, 65000, 55000, 59000, 61000, 100e9),  # USDT pair
        ])
        result = scan_top_volume(api, limit=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pair, "btcidr")

    def test_skips_pairs_with_zero_price_or_volume(self):
        api = _FakeAPI([
            _ticker("zeroidr", 0, 0, 0, 0, 0, 100e9),
            _ticker("nopriceidr", 0, 100, 90, 99, 101, 100e9),
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9),
        ])
        result = scan_top_volume(api, limit=10)
        self.assertEqual(len(result), 1)


class ScanTopMoversTests(unittest.TestCase):
    def setUp(self):
        pair_scanner._cache_invalidate()

    def test_top_gainers_sort_by_score_desc(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.05e9, 0.98e9, 0.99e9, 1.01e9, 100e9, 2.0),
            _ticker("dogeidr", 320, 320, 280, 318, 321, 5e9, 14.3),  # near high, +14%
            _ticker("xrpidr", 20000, 22000, 18000, 19000, 20500, 8e9, -2.0),  # -2%
            _ticker("solidr", 1e6, 1.05e6, 0.95e6, 0.99e6, 1.01e6, 10e9, 8.0),
        ])
        result = scan_top_movers(api, limit=3, direction="up")
        self.assertGreater(len(result), 0)
        # Doge should be #1 (highest momentum + dekat puncak = PUMPING)
        self.assertEqual(result[0].pair, "dogeidr")
        self.assertIn("TOP_GAINER", result[0].badges)
        self.assertIn("PUMPING", result[0].badges)
        # Negative change should rank lowest
        if len(result) > 1:
            for s in result:
                self.assertGreater(s.score, -100)

    def test_top_losers_direction_down(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.95e9, 0.99e9, 1.01e9, 100e9, 2.0),
            _ticker("xrpidr", 18000, 22000, 18000, 17900, 18100, 8e9, -15.0),
            _ticker("dogeidr", 250, 320, 250, 249, 251, 5e9, -20.0),
        ])
        result = scan_top_movers(api, limit=3, direction="down")
        self.assertEqual(result[0].pair, "dogeidr")  # paling jeblok
        self.assertIn("TOP_LOSER", result[0].badges)

    def test_filters_low_volume_pairs(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.95e9, 0.99e9, 1.01e9, 100e9, 5.0),
            # Pair tipis dengan change tinggi — harus di-skip karena volume < 500M
            _ticker("scamidr", 100, 200, 100, 99, 101, 100e6, 50.0),
        ])
        result = scan_top_movers(api, limit=5)
        pairs = [s.pair for s in result]
        self.assertIn("btcidr", pairs)
        self.assertNotIn("scamidr", pairs)

    def test_excludes_pairs_without_change_percent(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.95e9, 0.99e9, 1.01e9, 100e9, change=None),
            _ticker("ethidr", 5e7, 5.5e7, 4.8e7, 4.99e7, 5.01e7, 50e9, change=3.0),
        ])
        result = scan_top_movers(api, limit=5)
        pairs = [s.pair for s in result]
        self.assertNotIn("btcidr", pairs)
        self.assertIn("ethidr", pairs)


class WatchlistRecommendationTests(unittest.TestCase):
    def setUp(self):
        pair_scanner._cache_invalidate()

    def test_merges_top_volume_and_movers_unique(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9, 2.0),
            _ticker("ethidr", 5e7, 5.5e7, 4.5e7, 4.9e7, 5.1e7, 50e9, 3.0),
            _ticker("dogeidr", 320, 320, 280, 318, 321, 5e9, 14.3),
            _ticker("xrpidr", 20500, 22000, 18000, 20400, 20600, 8e9, 8.0),
            _ticker("solidr", 1e6, 1.05e6, 0.95e6, 0.99e6, 1.01e6, 10e9, 5.0),
        ])
        result = build_watchlist_recommendation(api, top_volume_limit=2, top_mover_limit=3)
        pairs = [s.pair for s in result]
        # btcidr & ethidr top volume; doge/xrp/sol top movers (≥500M)
        self.assertIn("btcidr", pairs)
        self.assertIn("ethidr", pairs)
        self.assertIn("dogeidr", pairs)
        # Tidak ada duplikat
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_excludes_blacklist(self):
        api = _FakeAPI([
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9, 2.0),
            _ticker("ethidr", 5e7, 5.5e7, 4.5e7, 4.9e7, 5.1e7, 50e9, 3.0),
        ])
        result = build_watchlist_recommendation(
            api, top_volume_limit=10, top_mover_limit=5, exclude={"btcidr"}
        )
        pairs = [s.pair for s in result]
        self.assertNotIn("btcidr", pairs)
        self.assertIn("ethidr", pairs)


class CacheTests(unittest.TestCase):
    def setUp(self):
        pair_scanner._cache_invalidate()

    def test_cache_returns_same_result_within_ttl(self):
        api = MagicMock()
        api.get_all_tickers.return_value = [
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9, 2.0)
        ]
        result1 = scan_top_volume(api, limit=5)
        result2 = scan_top_volume(api, limit=5)
        self.assertEqual(api.get_all_tickers.call_count, 1)  # only called once
        self.assertEqual([s.pair for s in result1], [s.pair for s in result2])

    def test_cache_bypassed_when_use_cache_false(self):
        api = MagicMock()
        api.get_all_tickers.return_value = [
            _ticker("btcidr", 1e9, 1.1e9, 0.9e9, 0.99e9, 1.01e9, 100e9, 2.0)
        ]
        scan_top_volume(api, limit=5, use_cache=False)
        scan_top_volume(api, limit=5, use_cache=False)
        self.assertEqual(api.get_all_tickers.call_count, 2)

    def test_api_failure_returns_empty_not_crash(self):
        api = MagicMock()
        api.get_all_tickers.side_effect = RuntimeError("network down")
        result = scan_top_volume(api, limit=5)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
