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
                "min_volume_idr": float(os.getenv("MIN_VOLUME_IDR", "100000000")),
                "weight": float(os.getenv("VOLUME_WEIGHT", "0.15"))
            },
            "vwap": {
                "enabled": os.getenv("ENABLE_VWAP", "true").lower() == "true",
                "period": int(os.getenv("VWAP_PERIOD", "14")),
                "weight": float(os.getenv("VWAP_WEIGHT", "0.10"))
            },
            "ichimoku": {
                "enabled": os.getenv("ENABLE_ICHIMOKU", "true").lower() == "true",
                "conversion_period": int(os.getenv("ICHIMOKU_CONVERSION", "9")),
                "base_period": int(os.getenv("ICHIMOKU_BASE", "26")),
                "span_b_period": int(os.getenv("ICHIMOKU_SPAN_B", "52")),
                "delay_period": int(os.getenv("ICHIMOKU_DELAY", "26")),
                "weight": float(os.getenv("ICHIMOKU_WEIGHT", "0.12"))
            },
            "divergence": {
                "enabled": os.getenv("ENABLE_DIVERGENCE", "true").lower() == "true",
                "lookback": int(os.getenv("DIVERGENCE_LOOKBACK", "20")),
                "rsi_period": int(os.getenv("DIVERGENCE_RSI_PERIOD", "14")),
                "macd_fast": int(os.getenv("DIVERGENCE_MACD_FAST", "12")),
                "macd_slow": int(os.getenv("DIVERGENCE_MACD_SLOW", "26")),
                "macd_signal": int(os.getenv("DIVERGENCE_MACD_SIGNAL", "9")),
                "weight": float(os.getenv("DIVERGENCE_WEIGHT", "0.15"))
            },
            "candlestick_patterns": {
                "enabled": os.getenv("ENABLE_CANDLESTICK_PATTERNS", "true").lower() == "true",
                "lookback": int(os.getenv("CANDLE_LOOKBACK", "3")),
                "weight": float(os.getenv("CANDLE_WEIGHT", "0.10"))
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