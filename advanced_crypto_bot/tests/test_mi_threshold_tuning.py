"""Regression test untuk MI threshold tuning 2026-06-09.

Konteks: setelah fix pre_sr_recommendation (commit 1b92bb6) di-deploy,
bot di VM masih 0 entry DRY RUN. Investigasi log: 26 dari 48 scan (54%)
di-block oleh MI filter dengan reason "Signal=NEUTRAL", padahal signal
STRONG_BUY/BUY dari ML+TA.

Root cause: threshold MI_VOLUME_SPIKE_MIN (1.3) dan MI_ORDERBOOK_BULLISH_MIN
(1.2) terlalu tinggi untuk pair low-cap di Indodax. Pair sideways
konsolidasi normal punya volume ratio ~1.0 dan bid/ask ratio 0.95-1.10,
tidak akan pernah memenuhi 1.3 / 1.2.

Fix: relax thresholds:
- MI_VOLUME_SPIKE_MIN: 1.3 → 1.1 (volume sedikit di atas avg cukup)
- MI_ORDERBOOK_BULLISH_MIN: 1.2 → 1.05 (bid pressure 5% cukup)

Test ini lock-in nilai baru dan verify bahwa scenario "moderate volume +
moderate bid pressure" sekarang menghasilkan MODERATE (bukan NEUTRAL).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from autotrade.runtime import analyze_market_intelligence
from core.config import Config


def _build_bot(*, volume_ratio: float, bid_volume: float, ask_volume: float, last_price: float = 100.0):
    """Build minimal bot fixture for MI analysis."""
    bot = MagicMock()

    # Historical data: 21 candles, last volume = volume_ratio × avg
    avg_vol = 1000.0
    last_vol = avg_vol * volume_ratio
    df = pd.DataFrame(
        {
            "open": [last_price] * 21,
            "high": [last_price + 1] * 21,
            "low": [last_price - 1] * 21,
            "close": [last_price] * 21,
            "volume": [avg_vol] * 20 + [last_vol],
        }
    )
    bot.historical_data = {"testidr": df}

    # Orderbook with notional bid_volume / ask_volume
    bid_amount = bid_volume / last_price
    ask_amount = ask_volume / last_price
    bids = [[str(last_price * 0.999), str(bid_amount)]]
    asks = [[str(last_price * 1.001), str(ask_amount)]]
    bot.indodax = MagicMock()
    bot.indodax.get_orderbook.return_value = {"bids": bids, "asks": asks}

    # Spoofing detection passthrough
    bot._update_heatmap = MagicMock()
    bot._detect_spoofing = MagicMock(return_value=(bids, asks, False))

    return bot


def test_mi_volume_spike_min_threshold_is_relaxed_to_1_1():
    """Pin threshold value — fail jika threshold di-bump kembali tanpa update test."""
    assert Config.MI_VOLUME_SPIKE_MIN == 1.1, (
        f"Expected MI_VOLUME_SPIKE_MIN=1.1 (relaxed 2026-06-09), got {Config.MI_VOLUME_SPIKE_MIN}. "
        "Bila perubahan disengaja, update test ini juga."
    )


def test_mi_orderbook_bullish_min_threshold_is_relaxed_to_1_05():
    """Pin threshold value."""
    assert Config.MI_ORDERBOOK_BULLISH_MIN == 1.05, (
        f"Expected MI_ORDERBOOK_BULLISH_MIN=1.05 (relaxed 2026-06-09), got {Config.MI_ORDERBOOK_BULLISH_MIN}. "
        "Bila perubahan disengaja, update test ini juga."
    )


@pytest.mark.asyncio
async def test_mi_moderate_volume_and_moderate_bid_pressure_yields_moderate_signal():
    """Skenario realistic: volume 1.15× avg + bid/ask ratio 1.08.
    Sebelum tuning: NEUTRAL (1.15 < 1.3 AND 1.08 < 1.2) → block.
    Sesudah tuning: BULLISH (1.15 ≥ 1.1 AND 1.08 ≥ 1.05) → allow.
    """
    bot = _build_bot(volume_ratio=1.15, bid_volume=10_800_000, ask_volume=10_000_000)
    # Ratio = 10.8M / 10M = 1.08

    result = await analyze_market_intelligence(bot, "testidr", current_price=100.0)

    # Volume spike harus terdeteksi (1.15 ≥ 1.1)
    assert result["volume_spike"] is True, (
        f"Volume ratio 1.15× harus pass threshold 1.1. Got volume_spike={result['volume_spike']}, "
        f"volume_ratio={result['volume_ratio']}"
    )
    # Orderbook pressure harus BULLISH (1.08 ≥ 1.05)
    assert result["orderbook_pressure"] == "BULLISH", (
        f"Bid/ask ratio 1.08 harus pass threshold 1.05. Got pressure={result['orderbook_pressure']}, "
        f"buy_sell_ratio={result['buy_sell_ratio']}"
    )
    # Both true → BULLISH overall
    assert result["overall_signal"] == "BULLISH"
    assert result["passes_entry_filter"] is True


@pytest.mark.asyncio
async def test_mi_low_volume_with_moderate_bid_pressure_yields_moderate():
    """Skenario: volume below avg (0.9×) + bid pressure 1.1.
    Sebelum: NEUTRAL (0.9 < 1.3 AND 1.1 < 1.2). Sesudah: MODERATE (volume fail, ob pass).
    """
    bot = _build_bot(volume_ratio=0.9, bid_volume=11_000_000, ask_volume=10_000_000)

    result = await analyze_market_intelligence(bot, "testidr", current_price=100.0)

    assert result["volume_spike"] is False  # 0.9 < 1.1
    assert result["orderbook_pressure"] == "BULLISH"  # 1.1 ≥ 1.05
    assert result["overall_signal"] == "MODERATE"  # 1 of 2 bullish signals
    # MI_ALLOW_MODERATE_ENTRY = True → masih lolos
    assert result["passes_entry_filter"] is True, (
        "MODERATE harus lolos kalau MI_ALLOW_MODERATE_ENTRY=True"
    )


@pytest.mark.asyncio
async def test_mi_truly_neutral_pair_still_blocked():
    """Sanity: pair benar-benar sideways/bearish tetap NEUTRAL.
    Volume normal (1.0×) + bid/ask seimbang (1.0). Tidak boleh lolos.
    """
    bot = _build_bot(volume_ratio=1.0, bid_volume=10_000_000, ask_volume=10_000_000)

    result = await analyze_market_intelligence(bot, "testidr", current_price=100.0)

    assert result["volume_spike"] is False  # 1.0 < 1.1
    assert result["orderbook_pressure"] == "NEUTRAL"  # 1.0 < 1.05
    assert result["overall_signal"] == "NEUTRAL"
    assert result["passes_entry_filter"] is False, (
        "Pair benar-benar neutral harus tetap di-block — proteksi minimum"
    )
