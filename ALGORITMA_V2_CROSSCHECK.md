# ALGORITMA V2 - CROSSCHECK REFERENCE

## Quick Reference

### Signal Thresholds
```
STRONG_BUY:  combined_strength > 0.20 AND ml_confidence >= 0.45
BUY:        combined_strength > 0.12
SELL:       combined_strength < -0.12
STRONG_SELL: combined_strength < -0.20 AND ml_confidence >= 0.45
HOLD:       otherwise
```

### Risk Management
```
MAX_POSITION: 20% of balance
STOP_LOSS:   -2%
TP1:         +2% (sell 50%)
TP2:         +5% (sell 50% remaining)
TRAILING:    activate at +1%, trail 1%
```

### Filters
```
VOLATILITY:  Block if ATR > 3x average
TREND:      BUY only in uptrend (SMA20>SMA50)
REGIME:     TRENDING=100%, RANGING=50%, VOLATILE=0%
```

---

## Code Locations

### Trading Engine (`autotrade/trading_engine.py`)
- Line ~120: Signal thresholds
- Line ~301: SL/TP calculation
- Line ~349: Multi-timeframe trend check
- Line ~385: Volatility filter
- Line ~410: Combined filter
- Line ~453: Market regime detection

### Price Monitor (`autotrade/price_monitor.py`)
- Line ~28: set_price_level (with TP1, TP2)
- Line ~163: Trailing stop update
- Line ~261: Auto-sell execution
- Line ~283: Partial TP calculation

### Config (`core/config.py`)
- Line ~38: STOP_LOSS_PCT = 2.0
- Line ~43: TRAILING_STOP_PCT = 1.0
- Line ~48: PARTIAL_TAKE_PROFIT_1 = 2.0
- Line ~49: PARTIAL_TAKE_PROFIT_2 = 5.0
- Line ~98: SLIPPAGE_MAX_PCT = 0.005

### Utils (`core/utils.py`)
- Line ~216: format_confidence_emoji
- Line ~232: format_confidence_text
- Line ~250: format_signal_badge
- Line ~270: clean_price_data
- Line ~298: detect_outliers

### Indodax API (`api/indodax_api.py`)
- Line ~366: create_order (with slippage check)
- Line ~378: Slippage calculation

---

## Test Commands

```bash
# Test imports
python -c "from autotrade.trading_engine import TradingEngine; from core.utils import Utils; print('OK')"

# Test signal threshold
python -c "
from autotrade.trading_engine import TradingEngine
te = TradingEngine(None, None)
signal = te.generate_signal('btcidr', {'strength': 0.25, 'price': 1000000, 'indicators': {}}, None, 0.5)
print(f'Signal: {signal[\"recommendation\"]}')"

# Test volatility filter
python -c "
import pandas as pd
from autotrade.trading_engine import TradingEngine
te = TradingEngine(None, None)
df = pd.DataFrame({'close': [100]*60, 'atr': [1.0]*60})
result = te.check_volatility_filter(df)
print(f'Volatile: {result}')"

# Test regime detection
python -c "
import pandas as pd
from autotrade.trading_engine import TradingEngine
te = TradingEngine(None, None)
df = pd.DataFrame({'close': [100+i for i in range(60)], 'atr': [1.0]*60})
result = te.detect_market_regime(df)
print(f'Regime: {result}')"

# Test utils
python -c "
from core.utils import Utils
print(Utils.format_confidence_emoji(0.8))
print(Utils.format_confidence_text(0.3))
print(Utils.format_signal_badge('BUY', 0.7))"
```