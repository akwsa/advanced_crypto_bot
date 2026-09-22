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

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from autotrade.runtime import analyze_market_intelligence
from core.config import Config


def _build_bot(*, volume_ratio: float, bid_volume: float, ask_volume: float, last_price: float = 100.0):
    """Build minimal bot fixture for MI analysis.

    2026-06-10: volume di historical_data adalah volume_24h cumulative dari
    ticker (di-append berulang per poll). MI sekarang hitung volume_ratio dari
    DELTA volume antar candle, bukan raw value. Fixture mensimulasikan pattern
    ini: 21 candle dengan delta konstan = avg_delta, kecuali delta terakhir =
    avg_delta * volume_ratio.
    """
    bot = MagicMock()

    avg_delta = 1000.0
    deltas = [avg_delta] * 19 + [avg_delta * volume_ratio]  # 20 deltas total
    volumes = [0.0]
    for d in deltas:
        volumes.append(volumes[-1] + d)
    # volumes: 21 entries (cumulative volume_24h pattern)

    df = pd.DataFrame(
        {
            "open": [last_price] * 21,
            "high": [last_price + 1] * 21,
            "low": [last_price - 1] * 21,
            "close": [last_price] * 21,
            "volume": volumes,
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

    with patch.object(Config, "MI_ALLOW_NEUTRAL_ENTRY", False):
        result = await analyze_market_intelligence(bot, "testidr", current_price=100.0)

    assert result["volume_spike"] is False  # 1.0 < 1.1
    assert result["orderbook_pressure"] == "NEUTRAL"  # 1.0 < 1.05
    assert result["overall_signal"] == "NEUTRAL"
    assert result["passes_entry_filter"] is False, (
        "Pair benar-benar neutral harus tetap di-block — proteksi minimum"
    )


@pytest.mark.asyncio
async def test_mi_volume_ratio_uses_delta_not_raw_cumulative_volume():
    """Regression test 2026-06-10.

    Bug: historical_data.volume adalah volume_24h dari ticker (rolling 24h),
    di-append berulang per poll. Akibatnya raw_value/avg ≈ 1.0 untuk SEMUA
    pair, tidak peduli aktivitas trading sebenarnya.

    Fix: pakai DELTA volume_24h antar candle = trade baru dalam window poll.

    Test ini build dataset dengan cumulative volume monoton naik di rate
    konstan (no spike) dan verify volume_ratio ≈ 1.0 — bukan ratio dari
    raw cumulative value (yang akan mendekati 1.0 hanya secara kebetulan).
    Lalu test juga bahwa SPIKE di delta terakhir ter-detect.
    """
    bot_no_spike = MagicMock()
    # 21 candle dengan volume cumulative monoton naik 100/poll (delta konstan).
    # Raw value: 100, 200, 300, ..., 2100. Raw ratio = 2100 / mean([200..2100]) = 1.83.
    # Delta-mode: semua delta = 100, ratio = 100/100 = 1.0 (correct, no spike).
    cumulative = [100.0 * i for i in range(1, 22)]
    df_no_spike = pd.DataFrame(
        {
            "open": [100.0] * 21, "high": [101.0] * 21, "low": [99.0] * 21,
            "close": [100.0] * 21, "volume": cumulative,
        }
    )
    bot_no_spike.historical_data = {"testidr": df_no_spike}
    bot_no_spike.indodax = MagicMock()
    bot_no_spike.indodax.get_orderbook.return_value = {
        "bids": [["99.9", "100"]], "asks": [["100.1", "100"]],
    }
    bot_no_spike._update_heatmap = MagicMock()
    bot_no_spike._detect_spoofing = MagicMock(return_value=([["99.9", "100"]], [["100.1", "100"]], False))

    result = await analyze_market_intelligence(bot_no_spike, "testidr", current_price=100.0)
    assert result["volume_ratio"] == 1.0, (
        f"Cumulative volume monoton naik konstan harus give ratio ~1.0 (delta konstan). "
        f"Got {result['volume_ratio']} — tanda regress ke raw-value mode."
    )
    assert result["volume_spike"] is False

    # Sekarang test SPIKE: delta terakhir 5x lipat. Cumulative jump.
    bot_spike = MagicMock()
    cumulative_spike = [100.0 * i for i in range(1, 21)] + [2000.0 + 500.0]  # delta last = 500
    df_spike = pd.DataFrame(
        {
            "open": [100.0] * 21, "high": [101.0] * 21, "low": [99.0] * 21,
            "close": [100.0] * 21, "volume": cumulative_spike,
        }
    )
    bot_spike.historical_data = {"testidr": df_spike}
    bot_spike.indodax = MagicMock()
    bot_spike.indodax.get_orderbook.return_value = {
        "bids": [["99.9", "100"]], "asks": [["100.1", "100"]],
    }
    bot_spike._update_heatmap = MagicMock()
    bot_spike._detect_spoofing = MagicMock(return_value=([["99.9", "100"]], [["100.1", "100"]], False))

    result_spike = await analyze_market_intelligence(bot_spike, "testidr", current_price=100.0)
    # avg delta = (19*100 + 500) / 20 = 120, last delta = 500, ratio = 4.17
    assert result_spike["volume_ratio"] >= 4.0, (
        f"Delta spike 5x harus terdeteksi sebagai high ratio. Got {result_spike['volume_ratio']}"
    )
    assert result_spike["volume_spike"] is True


@pytest.mark.asyncio
async def test_mi_volume_ratio_default_zero_when_no_history():
    """Pair tanpa historical_data → volume_ratio default 0.0 (bukan misleading 1.0)."""
    bot = MagicMock()
    bot.historical_data = {}  # Pair tidak di-preload
    bot.indodax = MagicMock()
    bot.indodax.get_orderbook.return_value = {
        "bids": [["99.9", "100"]], "asks": [["100.1", "100"]],
    }
    bot._update_heatmap = MagicMock()
    bot._detect_spoofing = MagicMock(return_value=([["99.9", "100"]], [["100.1", "100"]], False))

    result = await analyze_market_intelligence(bot, "newpairidr", current_price=100.0)
    assert result["volume_ratio"] == 0.0, (
        "No history → volume_ratio harus 0.0 (eksplisit no-data), "
        "bukan 1.0 (misleading 'normal volume')"
    )
    assert result["volume_spike"] is False
