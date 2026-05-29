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


@pytest.mark.asyncio
async def test_analyze_market_intelligence_blocks_entry_when_spread_too_wide():
    """Spread > MI_SPREAD_MAX_PCT should block entry even if OB is bullish."""
    bot = _FakeBot(
        {
            "bids": [["100", "5.0"], ["99", "3.0"]],
            "asks": [["105", "2.0"], ["106", "1.0"]],  # spread = 5/102.5 ≈ 4.88%
        }
    )

    from unittest.mock import patch as _patch
    with _patch("autotrade.runtime.Config.MI_SPREAD_MAX_PCT", 0.02):
        result = await analyze_market_intelligence(bot, "btcidr", current_price=100.0)

    assert result["spread_pct"] > 0.02
    assert result["spread_too_wide"] is True
    assert result["block_reason"] == "SPREAD_TOO_WIDE"
    assert result["passes_entry_filter"] is False


@pytest.mark.asyncio
async def test_analyze_market_intelligence_allows_entry_when_spread_tight():
    """Tight spread should not block entry."""
    bot = _FakeBot(
        {
            "bids": [["100", "5.0"], ["99", "3.0"]],
            "asks": [["100.5", "2.0"], ["101", "1.0"]],  # spread = 0.5/100.25 ≈ 0.5%
        }
    )

    from unittest.mock import patch as _patch
    with _patch("autotrade.runtime.Config.MI_SPREAD_MAX_PCT", 0.02):
        result = await analyze_market_intelligence(bot, "btcidr", current_price=100.0)

    assert result["spread_pct"] < 0.02
    assert result.get("spread_too_wide", False) is False
    # passes_entry_filter depends on overall_signal too, but spread is not blocking
    if result.get("passes_entry_filter"):
        assert result.get("block_reason") != "SPREAD_TOO_WIDE"


@pytest.mark.asyncio
async def test_analyze_market_intelligence_spread_result_includes_bid_ask_mid():
    """Result should always include best_bid, best_ask, mid_price when orderbook is valid."""
    bot = _FakeBot(
        {
            "bids": [["100", "5.0"], ["98", "3.0"]],
            "asks": [["102", "2.0"], ["104", "1.0"]],
        }
    )

    result = await analyze_market_intelligence(bot, "btcidr", current_price=100.0)

    assert result["best_bid"] == 100.0
    assert result["best_ask"] == 102.0
    assert result["mid_price"] == 101.0
    assert abs(result["spread_pct"] - (2.0 / 101.0)) < 0.001
