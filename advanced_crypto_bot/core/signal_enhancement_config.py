# Tujuan: Konfigurasi threshold dan bobot signal enhancement.
# Caller: SignalEnhancementEngine dan signal pipeline.
# Dependensi: dataclasses/env-style configuration.
# Main Functions: class SignalEnhancementConfig.
# Side Effects: No side effects.
"""
Signal Enhancement Configuration Module
=========================================
Configurable features untuk meningkatkan signal quality.
Enable/disable dari environment variables.

Features:
1. Volume Check - Validates signal based on 24h trading volume
2. VWAP - Volume Weighted Average Price
3. Ichimoku Cloud - Comprehensive trend analysis
4. Divergence Detection - RSI/MACD divergence from price
5. Candlestick Patterns - Price action patterns
"""

import os
from typing import Dict, Any


def _safe_float_env(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _safe_int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


class SignalEnhancementConfig:
    """Configuration class untuk signal enhancement features"""
    
    def __init__(self):
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        return {
            # Feature toggles
            "volume_check": {
                "enabled": os.getenv("ENABLE_VOLUME_CHECK", "true").lower() == "true",
                "min_volume_idr": _safe_float_env("MIN_VOLUME_IDR", 100000000),
                "weight": _safe_float_env("VOLUME_WEIGHT", 0.15)
            },
            "vwap": {
                "enabled": os.getenv("ENABLE_VWAP", "true").lower() == "true",
                "period": _safe_int_env("VWAP_PERIOD", 14),
                "weight": _safe_float_env("VWAP_WEIGHT", 0.10)
            },
            "ichimoku": {
                "enabled": os.getenv("ENABLE_ICHIMOKU", "true").lower() == "true",
                "conversion_period": _safe_int_env("ICHIMOKU_CONVERSION", 9),
                "base_period": _safe_int_env("ICHIMOKU_BASE", 26),
                "span_b_period": _safe_int_env("ICHIMOKU_SPAN_B", 52),
                "delay_period": _safe_int_env("ICHIMOKU_DELAY", 26),
                "weight": _safe_float_env("ICHIMOKU_WEIGHT", 0.12)
            },
            "divergence": {
                "enabled": os.getenv("ENABLE_DIVERGENCE", "true").lower() == "true",
                "lookback": _safe_int_env("DIVERGENCE_LOOKBACK", 20),
                "rsi_period": _safe_int_env("DIVERGENCE_RSI_PERIOD", 14),
                "macd_fast": _safe_int_env("DIVERGENCE_MACD_FAST", 12),
                "macd_slow": _safe_int_env("DIVERGENCE_MACD_SLOW", 26),
                "macd_signal": _safe_int_env("DIVERGENCE_MACD_SIGNAL", 9),
                "weight": _safe_float_env("DIVERGENCE_WEIGHT", 0.15)
            },
            "candlestick_patterns": {
                "enabled": os.getenv("ENABLE_CANDLESTICK_PATTERNS", "true").lower() == "true",
                "lookback": _safe_int_env("CANDLE_LOOKBACK", 3),
                "weight": _safe_float_env("CANDLE_WEIGHT", 0.10)
            }
        }
    
    def is_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self._config.get(feature, {}).get("enabled", False)
    
    def get_config(self, feature: str) -> Dict[str, Any]:
        """Get full config for a feature"""
        return self._config.get(feature, {})
    
    def get_weight(self, feature: str) -> float:
        """Get weight for a feature"""
        return self._config.get(feature, {}).get("weight", 0.0)
    
    def get_all_enabled(self) -> Dict[str, Any]:
        """Get all enabled features with their configs"""
        return {
            feature: config 
            for feature, config in self._config.items() 
            if config.get("enabled", False)
        }
    
    def __repr__(self):
        enabled = [f for f, c in self._config.items() if c.get("enabled")]
        return f"SignalEnhancementConfig(enabled: {enabled})"


# Global instance
signal_enhancement_config = SignalEnhancementConfig()
