import asyncio
import logging
from unittest.mock import MagicMock, patch
from signals.signal_pipeline import generate_signal_for_pair
import pandas as pd
from datetime import datetime

logging.basicConfig(level=logging.INFO)

class DummyBot:
    def __init__(self):
        self.historical_data = {
            'BTCIDR': pd.DataFrame({
                'close': [1000] * 60,
                'high': [1010] * 60,
                'low': [990] * 60,
                'open': [1000] * 60,
                'volume': [100] * 60,
            })
        }
        self.price_data = {'BTCIDR': {'last': 1000, 'timestamp': datetime.now()}}
        self.ml_model = MagicMock()
        self.ml_model.predict.return_value = (True, 0.8, 'BUY')
        self.ml_model._is_fitted = True
        
        self.ml_model_v4 = MagicMock()
        self.ml_model_v4.is_fitted = True
        self.ml_model_v4.predict.return_value = ('BAD_BUY', 0.9)
        
        self.trading_engine = MagicMock()
        self.trading_engine.generate_signal.return_value = {
            'recommendation': 'BUY',
            'ml_confidence': 0.8,
            'combined_strength': 0.5,
            'price': 1000,
        }
        
        self.signal_quality_engine = MagicMock()
        self.signal_quality_engine.check_volatility_filter.return_value = (True, "OK")
        self.signal_quality_engine.detect_market_regime.return_value = ("TREND", 1.0)
        self.signal_quality_engine.generate_signal.return_value = {'type': 'BUY', 'confluence': 3}
        
        self.sr_detector = MagicMock()
        self.sr_detector.detect_levels.return_value = {
            'support_1': 900,
            'resistance_1': 1100,
            'price_zone': 'MIDDLE',
            'risk_reward_ratio': 2.0
        }
        
        self.signal_enhancement = MagicMock()
        self.signal_enhancement.analyze.return_value = {
            'final_confidence_adjustment': 0.05,
            'should_override': False,
        }
        
        self.previous_signals = {}
        self._signal_db = MagicMock()
        self._signal_db.insert_signal.return_value = 1
        self.ml_version = 'V2'

async def test_pipeline():
    with patch('api.indodax_api.IndodaxAPI') as MockIndodax:
        mock_instance = MockIndodax.return_value
        mock_instance.get_ticker.return_value = {'last': 1000}
        
        bot = DummyBot()
        signal = await generate_signal_for_pair(bot, 'BTCIDR')
        print("FINAL SIGNAL:", signal['recommendation'])
        print("REASON:", signal.get('reason'))

if __name__ == '__main__':
    asyncio.run(test_pipeline())
