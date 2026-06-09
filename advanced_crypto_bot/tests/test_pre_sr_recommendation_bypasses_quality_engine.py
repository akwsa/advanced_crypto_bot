"""Regression test untuk fix 2026-06-09 (STRONG_BUY zero entry).

Akar masalah: `pre_sr_recommendation` sebelumnya di-snapshot SETELAH
Quality Engine V3 jalan. Akibatnya ketika Quality Engine men-downgrade
STRONG_BUY → HOLD karena confluence < 4, autotrade ikut melihat HOLD
walau ML+TA setuju STRONG_BUY. Hasil: 0 entry DRY RUN walau banyak
signal STRONG_BUY (homeidr 8x, portalidr 7x, saharaidr 6x dst).

Fix: snapshot `pre_sr_recommendation` SEBELUM Quality Engine berjalan.
Autotrade execution path bypass kedua filter (Quality Engine + SR
Validation), karena autotrade punya 17 entry gate sendiri yang lebih
tepat untuk keputusan eksekusi.

Test ini memastikan pre_sr_recommendation = STRONG_BUY walaupun final
signal["recommendation"] = HOLD (akibat Quality Engine).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from signals.signal_pipeline import generate_signal_for_pair


class _PipelineBot:
    """Minimal bot fixture replicating pipeline dependencies."""

    def __init__(self, *, signal_payload: dict, quality_payload: dict, sr_levels: dict):
        last_price = signal_payload.get("price", 100.0)
        self.historical_data = {"BTCIDR": self._build_df(last_price)}
        self.price_data = {"BTCIDR": {"last": last_price, "timestamp": datetime.now()}}
        self.previous_signals = {}
        self._signal_db = MagicMock()
        self._signal_db.insert_signal.return_value = 1
        self.ml_version = "V2"
        self._adaptive_engine = None

        self.ml_model = MagicMock()
        self.ml_model.predict.return_value = (
            True,
            signal_payload.get("ml_confidence", 0.7),
            signal_payload.get("recommendation", "STRONG_BUY"),
        )
        self.ml_model._is_fitted = True

        self.ml_model_v4 = MagicMock()
        self.ml_model_v4.is_fitted = False

        self.trading_engine = MagicMock()
        self.trading_engine.generate_signal.return_value = dict(signal_payload)

        self.signal_quality_engine = MagicMock()
        self.signal_quality_engine.check_volatility_filter.return_value = (True, "OK")
        self.signal_quality_engine.detect_market_regime.return_value = ("TREND", 1.0)
        self.signal_quality_engine.generate_signal.return_value = dict(quality_payload)
        self.signal_quality_engine.analyze_mean_reversion.return_value = None

        self.sr_detector = MagicMock()
        self.sr_detector.detect_levels.return_value = dict(sr_levels)

        self.signal_enhancement = MagicMock()
        self.signal_enhancement.analyze.return_value = {
            "enabled_features": [],
            "adjustments": [],
            "vwap": {},
            "ichimoku": {},
            "divergence": {},
            "candlestick": {},
            "volume": {},
            "final_confidence_adjustment": 0.0,
            "should_override": False,
        }

        self.indodax = MagicMock()
        self.indodax.get_ticker.return_value = {"last": last_price, "vol_idr": 1_000_000_000}

    @staticmethod
    def _build_df(last_price: float) -> pd.DataFrame:
        # Pipeline minta minimum 60 candles, kasih 70 untuk margin.
        closes = [last_price * 0.98] * 65 + [
            last_price * 0.985, last_price * 0.99, last_price * 0.995,
            last_price * 0.998, last_price,
        ]
        return pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1 for c in closes],
                "low": [c - 1 for c in closes],
                "close": closes,
                "volume": [1000.0] * len(closes),
            }
        )


@pytest.mark.asyncio
async def test_pre_sr_recommendation_preserves_strong_buy_when_quality_engine_downgrades_to_hold():
    """STRONG_BUY signal downgraded to HOLD by Quality Engine harus tetap
    keep pre_sr_recommendation = STRONG_BUY supaya autotrade bisa pakai."""
    signal_payload = {
        "recommendation": "STRONG_BUY",
        "ml_confidence": 0.55,
        "combined_strength": 0.24,
        "price": 540.0,
        "indicators": {
            "rsi": "NEUTRAL",
            "macd": "BULLISH_CROSS",
            "ma_trend": "BULLISH",
            "bb": "MIDDLE",
            "volume": "NORMAL",
        },
    }
    # Quality Engine men-downgrade ke HOLD karena confluence cuma 2.
    # Replicates real VM trace: homeidr 12:32:22.
    quality_payload = {
        "type": "HOLD",
        "recommendation": "HOLD",
        "confluence": 2,
        "reason": "STRONG_BUY requirements not met",
    }
    sr_levels = {
        "support_1": 530.0,
        "support_2": 525.0,
        "resistance_1": 541.0,
        "resistance_2": 550.0,
        "price_zone": "IN_RESISTANCE",
        "risk_reward_ratio": 0.10,
    }

    bot = _PipelineBot(
        signal_payload=signal_payload,
        quality_payload=quality_payload,
        sr_levels=sr_levels,
    )

    result = await generate_signal_for_pair(bot, "BTCIDR")

    assert result is not None, "Pipeline harus return signal dict"

    # Final recommendation memang HOLD karena Quality Engine.
    assert result["recommendation"] == "HOLD", (
        "Quality Engine harus tetap downgrade ke HOLD (untuk notif Telegram)"
    )

    # KEY ASSERTION: autotrade bypass field tetap STRONG_BUY.
    # Tanpa fix ini, pre_sr_recommendation = HOLD dan autotrade skip.
    assert result["pre_sr_recommendation"] == "STRONG_BUY", (
        f"pre_sr_recommendation harus = 'STRONG_BUY' (pre-Quality-Engine), "
        f"got '{result.get('pre_sr_recommendation')}'. "
        "Snapshot harus di-ambil SEBELUM Quality Engine, bukan sesudah."
    )


@pytest.mark.asyncio
async def test_pre_sr_recommendation_preserves_buy_when_quality_engine_downgrades():
    """Variasi: BUY (bukan STRONG_BUY) yang di-downgrade Quality Engine."""
    signal_payload = {
        "recommendation": "BUY",
        "ml_confidence": 0.52,
        "combined_strength": 0.15,
        "price": 412.0,
        "indicators": {"rsi": "NEUTRAL", "macd": "NEUTRAL", "ma_trend": "BULLISH"},
    }
    quality_payload = {
        "type": "HOLD",
        "recommendation": "HOLD",
        "confluence": 1,
        "reason": "BUY requirements not met",
    }
    sr_levels = {
        "support_1": 408.0,
        "support_2": 405.0,
        "resistance_1": 415.0,
        "resistance_2": 420.0,
        "price_zone": "MIDDLE",
        "risk_reward_ratio": 0.5,
    }
    bot = _PipelineBot(
        signal_payload=signal_payload,
        quality_payload=quality_payload,
        sr_levels=sr_levels,
    )

    result = await generate_signal_for_pair(bot, "BTCIDR")

    assert result is not None
    assert result["recommendation"] == "HOLD"
    assert result["pre_sr_recommendation"] == "BUY"


@pytest.mark.asyncio
async def test_pre_sr_recommendation_preserved_when_quality_engine_approves():
    """Sanity: kalau Quality Engine approve, pre_sr juga harus match
    (atau lebih kuat) — tidak boleh ada regresi untuk happy path."""
    signal_payload = {
        "recommendation": "STRONG_BUY",
        "ml_confidence": 0.80,
        "combined_strength": 0.40,
        "price": 100.0,
        "indicators": {
            "rsi": "OVERSOLD",
            "macd": "BULLISH_CROSS",
            "ma_trend": "BULLISH",
            "bb": "LOWER",
            "volume": "HIGH",
        },
    }
    quality_payload = {
        "type": "STRONG_BUY",
        "recommendation": "STRONG_BUY",
        "confluence": 5,
    }
    sr_levels = {
        "support_1": 98.0,
        "support_2": 95.0,
        "resistance_1": 110.0,
        "resistance_2": 115.0,
        "price_zone": "IN_SUPPORT",
        "risk_reward_ratio": 5.0,
    }
    bot = _PipelineBot(
        signal_payload=signal_payload,
        quality_payload=quality_payload,
        sr_levels=sr_levels,
    )

    result = await generate_signal_for_pair(bot, "BTCIDR")

    assert result is not None
    # Happy path: keduanya STRONG_BUY.
    assert result["pre_sr_recommendation"] == "STRONG_BUY"
    # Final recommendation bisa STRONG_BUY atau down ke BUY (jika SR
    # validation downgrade), tapi pre_sr_recommendation tidak terpengaruh.
    assert result["recommendation"] in ("STRONG_BUY", "BUY", "HOLD")
