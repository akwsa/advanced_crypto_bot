# 📖 Panduan Sinyal Kripto - Framework Komplit

## Inikator yang Digunakan Bot Ini

### ✅ Inikator Trend
- **Moving Average (SMA: 9,20,50,200)** → Arah trend
- **MACD (12,26,9)** → Crossover signal
- **EMA (9,20,50)** → Exponential MA

### ✅ Inikator Momentum
- **RSI (14)** → Overbought/Oversold
  - RSI < 30: OVERSOLD → BUY
  - RSI 30-70: NEUTRAL → HOLD
  - RSI > 70: OVERBOUGHT → SELL

### ✅ Inikator Volatility
- **Bollinger Bands (20,2)** → Upper/Lower band
  - Price di lower band → BUY
  - Price di upper band → SELL
  - Band width → Volatility indicator

### ✅ Inikator Volume
- **Volume SMA (20)** → Rata2 volume
- **Volume > 1.5x SMA** → HIGH (konfirmasi trend)

### ✅ Additional
- **ATR (14)** → Average True Range (volatility)
- **Stochastic (%K, %D)** → Momentum
- **ADX (14)** → Trend strength
- **OBV** → On-Balance Volume

---

## Cara Menentukan Signal

### 🚀 BUY Signal
- RSI Oversold (< 30)
- RSI Oversold + MACD Bullish Cross
- Price di lower Bollinger Band
- MACD Golden Cross (EMA 12 cross above EMA 26)
- Price > SMA 50 & SMA 50 > SMA 200 (Golden Cross)
- Volume spike + harga naik
- Oversold + MA bullish alignment

### ⏸️ HOLD Signal
- RSI Neutral (30-70)
- MACD Neutral (tidak ada crossover)
- Price di tengah Bollinger Band
- Volume normal (tidak ada spike)
- Price di antara support & resistance

### 📉 SELL Signal
- RSI Overbought (> 70)
- RSI Overbought + MACD Bearish Cross
- Price di upper Bollinger Band
- MACD Death Cross (EMA 12 cross below EMA 26)
- Price < SMA 50 & SMA 50 < SMA 200 (Death Cross)
- Volume spike + harga turun
- Overbought + MA bearish alignment

---

## Scoring System (Confirmation)

| Indikator | BUY Score | SELL Score |
|-----------|---------|----------|
| RSI Oversold | +1.0 | 0 |
| RSI Overbought | 0 | -1.0 |
| MACD Golden Cross | +1.0 | 0 |
| MACD Death Cross | 0 | -1.0 |
| MACD Bullish | +0.5 | 0 |
| MACD Bearish | 0 | -0.5 |
| Price > SMA > EMA | +1.0 | 0 |
| Price < SMA < EMA | 0 | -1.0 |
| BB Lower Band | +1.0 | 0 |
| BB Upper Band | 0 | -1.0 |
| Volume UP | +0.5 | 0 |
| Volume DOWN | 0 | -0.5 |

**Final Strength** = sum(scores) / 5  
**Range**: -1.0 s/d +1.0

---

## Threshold untuk Signal

| Signal | Strength | Conditions |
|--------|---------|-----------|
| 🚀 STRONG_BUY | > +0.50 | RSI<30 + MACD Bullish |
| 📈 BUY | > +0.05 | RSI<40 atau bullish MA |
| ⏸️ HOLD | -0.05 s/d +0.05 | Neutral / sideways |
| 📉 SELL | < -0.05 | RSI>60 atau bearish MA |
| 🔻 STRONG_SELL | < -0.50 | RSI>70 + MACD Bearish |

---

## Command untuk Trading

### Auto-Trade
- `/autotrade dryrun` - Enable simulation mode (AMAN)
- `/autotrade real` - Enable real trading
- `/autotrade off` - Disable
- `/autotrade_status` - Check status

### Smart Hunter
- `/smarthunter on` - Start
- `/smarthunter off` - Stop
- `/smarthunter_status` - Check positions

### Manual Commands
- `/signal <PAIR>` - Get signal analysis
- `/price <PAIR>` - Check price
- `/watch <PAIR>` - Add to watchlist

---

## ✅ Kesimpulan

Bot Ini Menggunakan Framework yang Sama dengan Profesional:

1. **RSI** - Momentum (Overbought/Oversold)
2. **MACD** - Trend (Crossover)
3. **Moving Averages** - Trend Direction
4. **Bollinger Bands** - Volatility
5. **Volume** - Confirmation

**Combination System**:
- Minimum 2-3 indikator harus agree untuk signal kuat
- Confluence scoring untuk validasi

✅ Framework Sudah Kompatibel dengan Panduan Ini!