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


# ---------------------------------------------------------------------------
# Regression: Indodax orderbook returning bid prices == 0 must NOT be reported
# as SPREAD_TOO_WIDE. Root cause (2026-06-09): low-cap pairs (dlcidr, homeidr,
# zerebroidr, ...) returned bid levels with price=0, so max(bid_prices)=0 and
# spread became 200%. The block_reason was misleading.
# Fix: filter level prices ≤ 0; when one side becomes empty, label
# block_reason="NO_BID_LIQUIDITY" instead of SPREAD_TOO_WIDE.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_analyze_market_intelligence_zero_bid_price_labeled_no_bid_liquidity():
    """Bid level with price=0 should produce NO_BID_LIQUIDITY, not SPREAD_TOO_WIDE."""
    bot = _FakeBot(
        {
            "bids": [["0", "100.0"]],            # price=0 → filtered out
            "asks": [["412", "2.0"], ["413", "1.0"]],
        }
    )

    result = await analyze_market_intelligence(bot, "pippinidr", current_price=412.0)

    assert result["spread_too_wide"] is True
    assert result["block_reason"] == "NO_BID_LIQUIDITY"
    assert result["passes_entry_filter"] is False
    # spread_pct should NOT be reported as 200%; it should be missing/None
    assert "spread_pct" not in result or result.get("spread_pct") in (None, 0)


@pytest.mark.asyncio
async def test_analyze_market_intelligence_empty_bids_labeled_no_bid_liquidity():
    """Completely empty bids list should produce NO_BID_LIQUIDITY."""
    bot = _FakeBot(
        {
            "bids": [],
            "asks": [["1000", "5.0"]],
        }
    )

    result = await analyze_market_intelligence(bot, "homeidr", current_price=1000.0)

    assert result["block_reason"] == "NO_BID_LIQUIDITY"
    assert result["passes_entry_filter"] is False


@pytest.mark.asyncio
async def test_analyze_market_intelligence_empty_asks_labeled_no_bid_liquidity():
    """Completely empty asks should also be flagged (same one-sided liquidity issue)."""
    bot = _FakeBot(
        {
            "bids": [["100", "5.0"]],
            "asks": [],
        }
    )

    result = await analyze_market_intelligence(bot, "saharaidr", current_price=100.0)

    assert result["block_reason"] == "NO_BID_LIQUIDITY"
    assert result["passes_entry_filter"] is False


@pytest.mark.asyncio
async def test_analyze_market_intelligence_negative_bid_price_filtered():
    """Defensive: negative price (corrupt API data) must also be filtered."""
    bot = _FakeBot(
        {
            "bids": [["-1", "100.0"], ["0", "50.0"]],  # both invalid
            "asks": [["500", "2.0"]],
        }
    )

    result = await analyze_market_intelligence(bot, "junkidr", current_price=500.0)

    assert result["block_reason"] == "NO_BID_LIQUIDITY"
    assert result["passes_entry_filter"] is False


@pytest.mark.asyncio
async def test_analyze_market_intelligence_mixed_zero_and_valid_bids_uses_valid():
    """If some bid levels have price=0 but others are valid, use the valid ones."""
    bot = _FakeBot(
        {
            "bids": [["0", "100.0"], ["95", "5.0"], ["94", "3.0"]],  # 0 filtered, 95 used
            "asks": [["96", "2.0"], ["97", "1.0"]],
        }
    )

    result = await analyze_market_intelligence(bot, "btcidr", current_price=95.5)

    # Should compute normal spread, not be blocked by NO_BID_LIQUIDITY
    assert result.get("block_reason") != "NO_BID_LIQUIDITY"
    assert result["best_bid"] == 95.0
    assert result["best_ask"] == 96.0


# ---------------------------------------------------------------------------
# Regression 2026-06-10: detect_spoofing dengan SPOOFING_ENABLED=True mengubah
# harga asli orderbook via round(price, -3). Untuk pair low-cap (~300-3000),
# round(price, -3) menghilangkan presisi dan bisa membuat bid > ask → spread
# negatif. Contoh real dari log VM:
#   gweiidr: bid=3,000 ask=2,989  (should be ~2979 vs ~2989)
#   homeidr: bid=1,000 ask=574    (should be ~571 vs ~575)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_analyze_market_intelligence_spread_tetap_positif_meski_detect_spoofing_rounding():
    """Spread harus tetap positif meski _detect_spoofing return data yang di-rounding."""
    # Simulasi: _detect_spoofing mengembalikan harga yang sudah di-round
    # ke ribuan (= harga asli 571 menjadi 1000, harga asli 575 menjadi 1000)
    # Skenario: spoof cleaning sudah aktif, cleaned_bids berisi round(price, -3)
    cleaned_bids_rounded = [["1000", "5.0"], ["1000", "3.0"]]  # round(571, -3) = 1000!
    cleaned_asks_rounded = [["1000", "2.0"]]  # round(575, -3) = 1000 (atau 574 tetap)

    class _RoundFakeBot:
        def __init__(self):
            self.indodax = _FakeIndodax({
                "bids": [["571", "10.0"], ["568", "5.0"]],
                "asks": [["575", "2.0"], ["577", "3.0"]],
            })
            self.historical_data = {
                "homeidr": pd.DataFrame({"volume": [100.0] * 25})
            }

        def _update_heatmap(self, pair, raw_bids, raw_asks):
            return None

        def _detect_spoofing(self, pair, raw_bids, raw_asks):
            # Spoof cleaning aktif — return data ROUNDED (simulasi bug)
            return cleaned_bids_rounded, cleaned_asks_rounded, True

    bot = _RoundFakeBot()
    result = await analyze_market_intelligence(bot, "homeidr", current_price=573.0)

    # Spread harus tetap positif (pakai raw data, bukan cleaned)
    assert result["spread_pct"] > 0, (
        f"Spread harus positif, got {result['spread_pct']*100:.3f}% "
        f"(bid={result['best_bid']:.0f} ask={result['best_ask']:.0f})"
    )
    assert result["best_bid"] == 571.0, "best_bid harus dari raw (571), bukan round(571, -3) = 1000"
    assert result["best_ask"] == 575.0, "best_ask harus dari raw (575)"


@pytest.mark.asyncio
async def test_analyze_market_intelligence_volume_default_is_zero_when_no_data():
    """volume_ratio default harus 0.0 (bukan 1.0) kalau tidak ada historical_data."""
    bot = _FakeBot(
        {
            "bids": [["100", "5.0"]],
            "asks": [["102", "2.0"]],
        },
        # Pair tidak ada di historical_data langsung
    )
    # Hapus historical_data untuk pair yang di-scan
    pair = "novolidr"
    bot.historical_data = {"btcidr": pd.DataFrame({"volume": [100.0] * 25})}

    result = await analyze_market_intelligence(bot, pair, current_price=100.0)

    assert result["volume_ratio"] == 0.0, (
        f"volume_ratio harus 0.0 tanpa data, got {result['volume_ratio']}"
    )
    assert result["volume_spike"] is False
