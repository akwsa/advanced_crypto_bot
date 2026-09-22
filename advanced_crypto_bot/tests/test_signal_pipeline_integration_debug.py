from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from signals.signal_pipeline import generate_signal_for_pair


class _PipelineIntegrationBot:
    def __init__(self, *, last_price: float, signal_payload: dict, quality_payload: dict, sr_levels: dict):
        self.historical_data = {
            "BTCIDR": self._build_df(last_price)
        }
        self.price_data = {
            "BTCIDR": {"last": last_price, "timestamp": datetime.now()}
        }
        self.previous_signals = {}
        self._signal_db = MagicMock()
        self._signal_db.insert_signal.return_value = 1
        self.ml_version = "V2"
        self._adaptive_engine = None

        self.ml_model = MagicMock()
        self.ml_model.predict.return_value = (True, signal_payload.get("ml_confidence", 0.7), signal_payload.get("recommendation", "BUY"))
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
        closes = [400.0] * 55 + [395.0, 392.0, 390.0, 389.0, last_price]
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
async def test_debug_duplicate_case_prints_actual_second_signal_shape():
    first_signal_payload = {
        "recommendation": "STRONG_BUY",
        "ml_confidence": 0.83,
        "combined_strength": 0.36,
        "price": 389.0,
        "indicators": {
            "rsi": "OVERSOLD",
            "macd": "BULLISH_CROSS",
            "ma_trend": "BULLISH",
            "bb": "LOWER",
            "volume": "NORMAL",
        },
    }
    first_quality_payload = {
        "type": "STRONG_BUY",
        "recommendation": "STRONG_BUY",
        "confluence": 4,
    }
    sr_levels = {
        "support_1": 387.0,
        "support_2": 384.0,
        "resistance_1": 404.0,
        "resistance_2": 410.0,
        "price_zone": "IN_SUPPORT",
        "risk_reward_ratio": 4.5,
    }

    bot = _PipelineIntegrationBot(
        last_price=389.0,
        signal_payload=first_signal_payload,
        quality_payload=first_quality_payload,
        sr_levels=sr_levels,
    )

    with patch("api.indodax_api.IndodaxAPI") as mock_indodax:
        mock_indodax.return_value.get_ticker.return_value = {"last": 389.0}
        await generate_signal_for_pair(bot, "BTCIDR")

    bot.historical_data["BTCIDR"] = bot._build_df(388.0)
    bot.price_data["BTCIDR"] = {"last": 388.0, "timestamp": datetime.now()}
    bot.trading_engine.generate_signal.return_value = {
        **first_signal_payload,
        "price": 388.0,
        "ml_confidence": 0.81,
        "combined_strength": 0.33,
    }
    bot.signal_quality_engine.generate_signal.return_value = {
        "type": "STRONG_BUY",
        "recommendation": "STRONG_BUY",
        "confluence": 4,
    }
    bot.previous_signals["BTCIDR"]["timestamp"] = datetime.now() - timedelta(minutes=8)

    with patch("api.indodax_api.IndodaxAPI") as mock_indodax:
        mock_indodax.return_value.get_ticker.return_value = {"last": 388.0}
        second = await generate_signal_for_pair(bot, "BTCIDR")

    print(second)
