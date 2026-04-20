# ML Trading Model V3 - PRO Version

## Overview

ML Model V3 is a professional-grade machine learning trading model with:
- Risk/Reward based target labeling
- 60+ technical indicators
- Professional backtesting with all costs
- Kelly Criterion position sizing
- Market regime detection
- Dry-run simulation mode

## Improvements over V2

| Feature | V2 | V3 (PRO) |
|--------|-----|----------|
| Target Label | Return % based | R/R based (>2:1) |
| Features | ~40 | 60+ |
| Backtesting | Basic | Full with fees |
| Position Sizing | Fixed % | Kelly Criterion |
| Market Regime | None | Full detection |
| Dry-Run | Manual | Automated |

## Target Labeling Logic

V3 uses **Risk/Reward ratio** instead of simple returns:

```python
# Minimum 2:1 R/R required for BUY signal
# SL = 2 * ATR
# TP = 4 * ATR (2 * SL = 4% for 2:1 R/R)

BUY signal = IF:
  - Best future return >= 2% (MIN_PROFIT_PCT)
  - AND R/R achieved >= 2.0 (MIN_RR_RATIO)

SELL signal = IF:
  - Worst future return <= -2%
  - OR R/R < 1.0
```

## Features (60+)

### 1. Price Momentum & Returns (10)
- return_1, return_3, return_5, return_10, return_20
- momentum_5, momentum_10, momentum_20
- roc_5, roc_10, roc_20

### 2. Moving Averages & Trends (15)
- sma_5, sma_9, sma_20, sma_50, sma_200
- price_sma5, price_sma9, price_sma20...
- sma_cross_5_20, sma_cross_9_50...
- trend_strength
- ema_12, ema_26, ema_diff

### 3. Volatility (8)
- volatility_20, volatility_50, volatility_ratio
- atr_14, atr_14_pct
- bb_width, bb_position
- kc_position

### 4. Volume Analysis (7)
- volume_sma_20, volume_sma_50
- volume_ratio, volume_trend
- volume_zscore
- vol_price_corr
- obv, obv_sma

### 5. RSI (4)
- rsi_14
- rsi_ma, rsi_diff
- rsi_overbought, rsi_oversold

### 6. MACD (5)
- macd, macd_signal
- macd_hist, macd_hist_change
- macd_cross_up, macd_cross_down

### 7. Stochastic (3)
- stoch_k, stoch_d
- stoch_cross

### 8. Support & Resistance (7)
- support_20, support_50
- resistance_20, resistance_50
- dist_to_support, dist_to_resistance
- support_tests, resistance_tests
- pivot, pivot_r1, pivot_s1

### 9. Market Regime (3)
- vol_regime
- trend_regime
- volume_regime

### 10. Momentum (4)
- cci
- williams_r
- adx

## Backtesting

V3 backtest includes ALL costs:

```python
TRADING_FEE_RATE = 0.003  # 0.3% per trade
WITHDRAWAL_FEE = 10000   # 10K IDR flat
SLIPPAGE_PCT = 0.001     # 0.1% assumption
```

### Metrics Generated

- Initial/Final Balance
- Total Profit (IDR + %)
- Total Trades
- Winning/Losing Trades
- Win Rate
- Max Drawdown
- Sharpe Ratio
- Profit Factor
- Total Fees Paid
- Avg Profit/Loss per Trade
- Largest Win/Loss

## Kelly Criterion Position Sizing

Formula: `K% = W - (1-W)/R`

Where:
- W = Win Rate
- R = Win/Loss Ratio

Example:
- Win Rate = 50%
- Avg Win = 400K
- Avg Loss = 200K
- R = 2.0
- K% = 0.50 - (0.50/2.0) = 0.50 - 0.25 = 25%

Using fractional Kelly (50%):
- Position Size = 12.5%

## Commands

### /backtest_v3

```
Usage: /backtest_v3 <PAIR> <DAYS>

Examples:
/backtest_v3 btcidr 30
/backtest_v3 ethidr 7
/backtest_v3 solidr 90
```

### /dryrun

```
Usage: /dryrun <PAIR> <INITIAL_BALANCE>

Examples:
/dryrun btcidr
/dryrun ethidr 10000000
```

### /regime

```
Usage: /regime <PAIR>

Examples:
/regime btcidr
/regime
```

## Usage in Bot

V3 is automatically initialized at bot startup:

```python
# Initialize V3
self.ml_model_v3 = create_ml_v3()

# Use for prediction
prediction, confidence, signal_str = self.ml_model_v3.predict(df)

# Use for backtest
result = self.ml_model_v3.backtest(df, initial_balance=10000000)

# Get market regime
regime = self.ml_model_v3.get_market_regime(df)
```

## Training

To train V3:

```python
# Get data
df = db.get_price_history('btcidr', limit=5000)

# Train
success = ml_model_v3.train(df, use_multi_class=True)
```

## Backtest Example Output

```
📊 PRO Backtest Results (ML V3) 

💰 Balance:
• Initial: 10,000,000 IDR
• Final: 12,450,000 IDR
• Profit: +2,450,000 IDR (+24.5%)

📈 Trading:
• Total Trades: 45
• Winning: 28
• Losing: 17
• Win Rate: 62.22%

📉 Risk Metrics:
• Max Drawdown: 8.45%
• Profit Factor: 2.15
• Sharpe Ratio: 1.32

💵 Costs:
• Total Fees: 285,000 IDR
• Avg Profit: 175,000 IDR
• Avg Loss: -85,000 IDR
```

## Limitations

1. **Past performance ≠ future results**
2. **Backtest uses historical data** - market conditions change
3. **No guarantee of profit** - always use proper risk management
4. **Start with dry-run** before live trading