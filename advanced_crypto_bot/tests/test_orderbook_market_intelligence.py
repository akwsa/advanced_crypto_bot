import pandas as pd
import pytest
from types import SimpleNamespace

from autotrade.runtime import analyze_market_intelligence


class _FakeIndodax:
    def __init__(self, orderbook):
        self.orderbook = orderbook

    def get_orderbook(self, pair, limit=20):
        return self.orderbook


class _FakeBot:
    def __init__(self, orderbook, volume_rows=25):
        self.indodax = _FakeIndodax(orderbook)
        self.historical_data = {
            "btcidr": pd.DataFrame(
                {
                    "volume": [100.0] * (volume_rows - 1) + [150.0],
                }
            )
        }

    def _update_heatmap(self, pair, raw_bids, raw_asks):
        return None

    def _detect_spoofing(self, pair, raw_bids, raw_asks):
        return raw_bids, raw_asks, False


@pytest.mark.asyncio
async def test_analyze_market_intelligence_converts_string_orderbook_levels_to_numeric():
    bot = _FakeBot(
        {
            "bids": [["100", "2.5"], ["99", "1.5"]],
            "asks": [["101", "1.0"], ["102", "1.0"]],
        }
    )

    result = await analyze_market_intelligence(bot, "btcidr", current_price=100.0)

    assert result["buy_sell_ratio"] > 1.0
    assert result["orderbook_pressure"] == "BULLISH"
    assert result["overall_signal"] in ["BULLISH", "MODERATE"]


@pytest.mark.asyncio
async def test_analyze_market_intelligence_skips_invalid_orderbook_rows_without_crashing():
    bot = _FakeBot(
        {
            "bids": [["100", "2.0"], [None, "oops"], ["bad"]],
            "asks": [["101", "3.0"], ["102", None]],
        }
    )

    result = await analyze_market_intelligence(bot, "btcidr", current_price=100.0)

    assert isinstance(result["buy_sell_ratio"], float)
    assert result["orderbook_pressure"] in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert "passes_entry_filter" in result
