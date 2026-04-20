# Signal Enhancement Features - Technical Documentation

## Overview

Dokumen ini menjelaskan 5 fitur tambahan untuk meningkatkan kualitas signal:
1. Volume Check
2. VWAP (Volume Weighted Average Price)
3. Ichimoku Cloud
4. Divergence Detection
5. Candlestick Patterns

---

## 1. Volume Check

### Deskripsi
Memvalidasi signal berdasarkan 24h trading volume. Volume rendah menandakan signal kurang reliable karena mudah dimanipulasi.

### Konfigurasi
```python
# Di Config.py atau .env
ENABLE_VOLUME_CHECK = True          # Enable/disable feature
MIN_VOLUME_THRESHOLD = 100000000     # Min volume IDR (100jt IDR)
VOLUME_CONFIDENCE_WEIGHT = 0.15     # Bobot dalam final confidence (0.0-1.0)
```

### Logika Perhitungan
```python
def calculate_volume_confidence(volume_24h, min_threshold):
    """
    Input: volume_24h (IDR), min_threshold (IDR)
    Output: confidence multiplier (0.0 - 1.0)
    
    Logic:
    - volume < min_threshold * 0.5  → 0.0 (very low, reject)
    - volume < min_threshold         → 0.3 - 0.7 (low)
    - volume >= min_threshold        → 0.8 - 1.0 (good)
    - volume >= min_threshold * 3    → 1.0 (excellent)
    """
    if volume_24h < min_threshold * 0.5:
        return 0.0   # Terlalu rendah, signal tidak valid
    elif volume_24h < min_threshold:
        ratio = volume_24h / min_threshold
        return 0.3 + (ratio * 0.4)  # 0.3 - 0.7
    elif volume_24h < min_threshold * 3:
        ratio = volume_24h / (min_threshold * 3)
        return 0.8 + (ratio * 0.2)  # 0.8 - 1.0
    else:
        return 1.0   # Excellent volume
```

### Integration ke Signal
```
Final Confidence = Original Confidence × Volume Weight
               + Original Confidence × (1 - Volume Weight)
               
Jika Volume Confidence < 0.3 → Override signal ke HOLD
```

### Data Source
- Indodax API: `get_ticker(pair)` → `vol_btc`, `vol_idr`
- Fallback: Hitung dari price history jika API unavailable

---

## 2. VWAP (Volume Weighted Average Price)

### Deskripsi
VWAP menunjukkan harga rata-rata yang "fair" berdasarkan volume. Harga di atas VWAP = bullish, di bawah = bearish.

### Konfigurasi
```python
ENABLE_VWAP = True
VWAP_PERIOD = 14           # Jumlah candle untuk hitung VWAP
VWAP_WEIGHT = 0.10         # Bobot dalam final signal (0.0-1.0)
```

### Logika Perhitungan
```python
def calculate_vwap(df, period=14):
    """
    Input: df (DataFrame dengan 'close', 'high', 'low', 'volume')
    Output: vwap value
    
    Formula: VWAP = Σ(Price × Volume) / Σ(Volume)
    Using typical price = (High + Low + Close) / 3
    """
    # Typical Price
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    
    # Cumulative typical price × volume
    df['tpv'] = df['typical_price'] * df['volume']
    df['cum_tpv'] = df['tpv'].rolling(window=period).sum()
    df['cum_vol'] = df['volume'].rolling(window=period).sum()
    
    # VWAP
    vwap = df['cum_tpv'] / df['cum_vol']
    
    return vwap.iloc[-1]  # Latest VWAP
```

### Signal Logic
```python
def get_vwap_signal(current_price, vwap):
    """
    Output: 'bullish', 'bearish', atau 'neutral'
    """
    if current_price > vwap * 1.005:  # 0.5% above
        return 'bullish'
    elif current_price < vwap * 0.995:  # 0.5% below
        return 'bearish'
    else:
        return 'neutral'
```

### Integration ke Signal
```
Indicator yang ditambahkan:
- vwap_value: float
- vwap_signal: 'bullish' | 'bearish' | 'neutral'
- vwap_distance_pct: (price - vwap) / vwap × 100

Confluence: Jika VWAP signal searah dengan rekomendasi → +confidence
```

---

## 3. Ichimoku Cloud

### Deskripsi
Ichimoku memberikan gambaran trend dan S/R secara komprehensif. Sering digunakan trader profesional.

### Konfigurasi
```python
ENABLE_ICHIMOKU = True
ICHIMOKU_CONVERSION_PERIOD = 9    # Tenkan-sen
ICHIMOKU_BASE_PERIOD = 26         # Kijun-sen
ICHIMOKU_SPAN_B_PERIOD = 52       # Senkou Span B
ICHIMOKU_DELAY = 26               # Chikou Span shift
ICHIMOKU_WEIGHT = 0.12            # Bobot dalam signal
```

### Logika Perhitungan
```python
def calculate_ichimoku(df, conv=9, base=26, span_b=52, delay=26):
    """
    Output: dict dengan:
    - tenkan_sen (Conversion Line)
    - kijun_sen (Base Line)
    - senkou_a (Leading Span A)
    - senkou_b (Leading Span B)
    - chikou_span (Lagging Span)
    - cloud_top, cloud_bottom (Cloud boundaries)
    """
    
    # Tenkan-sen (Conversion Line) = (Highest High + Lowest Low) / 2
    high_9 = df['high'].rolling(window=conv).max()
    low_9 = df['low'].rolling(window=conv).min()
    tenkan_sen = (high_9 + low_9) / 2
    
    # Kijun-sen (Base Line) = (Highest High + Lowest Low) / 2
    high_26 = df['high'].rolling(window=base).max()
    low_26 = df['low'].rolling(window=base).min()
    kijun_sen = (high_26 + low_26) / 2
    
    # Senkou Span A (Leading Span A) = (Tenkan-sen + Kijun-sen) / 2
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(delay)
    
    # Senkou Span B (Leading Span B) = (Highest High + Lowest Low) / 2
    high_52 = df['high'].rolling(window=span_b).max()
    low_52 = df['low'].rolling(window=span_b).min()
    senkou_b = ((high_52 + low_52) / 2).shift(delay)
    
    # Cloud
    cloud_top = senkou_a.combine(senkou_b, max)
    cloud_bottom = senkou_a.combine(senkou_b, min)
    
    # Chikou Span (Lagging Span) = Close price, shifted back
    chikou_span = df['close'].shift(-delay)
    
    return latest values
```

### Signal Logic
```python
def get_ichimoku_signal(price, tenkan, kijun, cloud_top, cloud_bottom):
    """
    Output: 'bullish', 'bearish', atau 'neutral'
    
    Bullish Conditions:
    - Price above cloud
    - Tenkan crosses above Kijun
    - Cloud is green (senkou_a > senkou_b)
    
    Bearish Conditions:
    - Price below cloud
    - Tenkan crosses below Kijun
    - Cloud is red (senkou_a < senkou_b)
    """
    
    # Check cloud position
    above_cloud = price > cloud_top
    below_cloud = price < cloud_bottom
    
    # Check crossover
    tenkan_above_kijun = tenkan > kijun
    
    # Determine trend
    if above_cloud and tenkan_above_kijun:
        return 'bullish'
    elif below_cloud and not tenkan_above_kijun:
        return 'bearish'
    else:
        return 'neutral'
```

### Integration
```
Indicator yang ditambahkan:
- ichimoku_tenkan_sen
- ichimoku_kijun_sen
- ichimoku_cloud_top
- ichimoku_cloud_bottom
- ichimoku_signal: bullish | bearish | neutral

Confluence: +0.1 jika ichimoku searah dengan rekomendasi
```

---

## 4. Divergence Detection

### Deskripsi
Divergence terjadi ketika price dan indicator bergerak berbeda. Ini sering menjadi early warning untuk reversal.

### Konfigurasi
```python
ENABLE_DIVERGENCE = True
DIVERGENCE_LOOKBACK = 20        # Jumlah candle untuk cek divergence
DIVERGENCE_RSI_PERIOD = 14      # RSI period
DIVERGENCE_MACD_FAST = 12        # MACD fast
DIVERGENCE_MACD_SLOW = 26       # MACD slow
DIVERGENCE_MACD_SIGNAL = 9       # MACD signal
DIVERGENCE_WEIGHT = 0.15        # Bobot
```

### Logika Perhitungan

#### Regular Divergence (Trend Reversal)
```python
def detect_regular_divergence(df, indicator='rsi'):
    """
    Regular Bullish Divergence:
    - Price membuat lower low
    - Indicator membuat higher low
    
    Regular Bearish Divergence:
    - Price membuat higher high
    - Indicator membuat lower high
    """
    
    # Get price and indicator
    prices = df['close'].values
    if indicator == 'rsi':
        indicators = calculate_rsi(df, 14)
    elif indicator == 'macd':
        indicators = calculate_macd(df)['macd']
    
    # Find pivot points
    price_pivots = find_pivots(prices, threshold=0.03)  # 3% pivot
    indicator_pivots = find_pivots(indicators, threshold=0.05)  # 5% pivot
    
    # Compare last pivot directions
    last_price_pivot = price_pivots[-1]  # {type: 'low' or 'high', index: n}
    last_indicator_pivot = indicator_pivots[-1]
    
    # Bullish divergence: price lower low, indicator higher low
    if last_price_pivot['type'] == 'low' and last_indicator_pivot['type'] == 'low':
        if prices[last_price_pivot['index']] < prices[last_indicator_pivot['index']]:  # lower low
            if indicators[last_indicator_pivot['index']] > indicators[last_price_pivot['index']]:  # higher low
                return 'bullish'
    
    # Bearish divergence: price higher high, indicator lower high
    if last_price_pivot['type'] == 'high' and last_indicator_pivot['type'] == 'high':
        if prices[last_price_pivot['index']] > prices[last_indicator_pivot['index']]:  # higher high
            if indicators[last_indicator_pivot['index']] < indicators[last_price_pivot['index']]:  # lower high
                return 'bearish'
    
    return 'none'
```

#### Hidden Divergence (Trend Continuation)
```python
def detect_hidden_divergence(df, indicator='rsi'):
    """
    Hidden Bullish Divergence:
    - Price membuat higher low
    - Indicator membuat lower low
    
    Hidden Bearish Divergence:
    - Price membuat lower high
    - Indicator membuat higher high
    """
    # Similar logic but reversed
    # Indicates continuation, not reversal
```

### Signal Logic
```python
def get_divergence_signal(rsi_div, macd_div):
    """
    Output: 'bullish', 'bearish', 'neutral'
    
    Priority: RSI divergence > MACD divergence
    """
    # Weight regular vs hidden divergence
    if rsi_div in ['bullish', 'bearish']:
        return rsi_div
    elif macd_div in ['bullish', 'bearish']:
        return macd_div
    else:
        return 'neutral'
```

### Integration
```
Indicator yang ditambahkan:
- rsi_divergence: bullish | bearish | none
- macd_divergence: bullish | bearish | none
- divergence_signal: bullish | bearish | none
- divergence_type: regular | hidden | none

Signal Impact:
- Bullish divergence + BUY signal = +confidence
- Bearish divergence + SELL signal = +confidence
- Divergence + opposite direction = strong warning (reduce confidence)
```

---

## 5. Candlestick Patterns

### Deskripsi
Pattern candlestick memberikan sinyal visual tentang sentimen pasar dan potential reversal.

### Konfigurasi
```python
ENABLE_CANDLESTICK_PATTERNS = True
CANDLE_LOOKBACK = 3           # Jumlah candle untuk pattern detection
CANDLE_WEIGHT = 0.10          # Bobot dalam signal

# Pattern yang di-detect
BULLISH_PATTERNS = [
    'hammer', 'inverted_hammer', 'bullish_engulfing',
    'morning_star', 'piercing_line', 'three_white_soldiers'
]

BEARISH_PATTERNS = [
    'shooting_star', 'bearish_engulfing',
    'evening_star', 'dark_cloud_cover', 'three_black_crows'
]
```

### Logika Perhitungan
```python
def detect_candlestick_patterns(df, lookback=3):
    """
    Detect common candlestick patterns
    
    Output: dict dengan pattern yang terdeteksi + strength
    """
    patterns = []
    
    latest = df.iloc[-1]
    prev1 = df.iloc[-2] if len(df) > 1 else None
    prev2 = df.iloc[-3] if len(df) > 2 else None
    
    # Body dan shadow calculations
    latest_body = abs(latest['close'] - latest['open'])
    latest_upper_shadow = latest['high'] - max(latest['close'], latest['open'])
    latest_lower_shadow = min(latest['close'], latest['open']) - latest['low']
    
    # HAMMER: Small body, long lower shadow, little upper shadow
    if (latest_body / latest['close'] < 0.02 and  # small body
        latest_lower_shadow > latest_body * 2 and  # long lower shadow
        latest_upper_shadow < latest_body):  # little upper
        patterns.append('hammer')
    
    # SHOOTING STAR: Opposite of hammer
    if (latest_body / latest['close'] < 0.02 and
        latest_upper_shadow > latest_body * 2 and
        latest_lower_shadow < latest_body):
        patterns.append('shooting_star')
    
    # BULLISH ENGULFING: Current green, prev red, current body engulfs prev
    if prev1 and latest['close'] > latest['open'] and prev1['close'] < prev1['open']:
        if (latest['open'] < prev1['close'] and latest['close'] > prev1['open']):
            patterns.append('bullish_engulfing')
    
    # BEARISH ENGULFING: Current red, prev green, current body engulfs prev
    if prev1 and latest['close'] < latest['open'] and prev1['close'] > prev1['open']:
        if (latest['open'] > prev1['close'] and latest['close'] < prev1['open']):
            patterns.append('bearish_engulfing')
    
    # MORNING STAR: 3-candle pattern
    if prev2 and prev1:
        # Candle 1: red (long)
        # Candle 2: small body (doji/spinning)
        # Candle 3: green (closes into candle 1 body)
        if (prev2['close'] < prev2['open'] and  # red
            abs(prev1['close'] - prev1['open']) < abs(prev2['body']) * 0.3 and  # small
            latest['close'] > (prev2['open'] + prev2['close']) / 2):  # green
            patterns.append('morning_star')
    
    # EVENING STAR: Opposite
    if prev2 and prev1:
        if (prev2['close'] > prev2['open'] and  # green
            abs(prev1['close'] - prev1['open']) < abs(prev2['body']) * 0.3 and  # small
            latest['close'] < (prev2['open'] + prev2['close']) / 2):  # red
            patterns.append('evening_star')
    
    return patterns
```

### Signal Logic
```python
def get_candle_signal(patterns):
    """
    Output: 'bullish', 'bearish', 'neutral'
    
    Logic:
    - Jika ada bullish pattern → bullish
    - Jika ada bearish pattern → bearish
    - Jika ada keduanya → neutralize
    """
    bullish_count = sum(1 for p in patterns if p in BULLISH_PATTERNS)
    bearish_count = sum(1 for p in patterns if p in BEARISH_PATTERNS)
    
    if bullish_count > bearish_count:
        return 'bullish'
    elif bearish_count > bullish_count:
        return 'bearish'
    else:
        return 'neutral'
```

### Integration
```
Indicator yang ditambahkan:
- candle_patterns: [list of patterns detected]
- candle_signal: bullish | bearish | neutral
- candle_strength: count of patterns

Signal Impact:
- Pattern searah recommendation → +confidence
- Pattern sebaliknya → warning, mungkin override ke HOLD
```

---

## Integration Summary

### Final Signal Calculation

```python
def calculate_final_confidence(base_confidence, features):
    """
    base_confidence: float (0.0 - 1.0)
    features: dict dengan semua feature results
    
    Output: adjusted confidence + reasons
    """
    adjustments = []
    
    # 1. Volume Check
    if features['volume_confidence'] < 0.3:
        return 0.0, "Volume too low"
    adjustments.append(('volume', features['volume_confidence'], 0.15))
    
    # 2. VWAP
    if features['vwap_signal'] != 'neutral':
        adjustments.append((features['vwap_signal'], 0.10))
    
    # 3. Ichimoku
    if features['ichimoku_signal'] != 'neutral':
        adjustments.append((features['ichimoku_signal'], 0.12))
    
    # 4. Divergence
    if features['divergence_signal'] != 'neutral':
        adjustments.append((features['divergence_signal'], 0.15))
    
    # 5. Candlestick
    if features['candle_signal'] != 'neutral':
        adjustments.append((features['candle_signal'], 0.10))
    
    # Apply adjustments
    final_conf = base_confidence
    for direction, weight in adjustments:
        if direction == 'bullish':
            final_conf += weight
        elif direction == 'bearish':
            final_conf -= weight
    
    # Clamp
    final_conf = max(0.0, min(1.0, final_conf))
    
    return final_conf, adjustments
```

### Override Conditions

Signal di-override ke HOLD jika:
1. Volume confidence < 0.3
2. Confluence score < 0.5 (terlalu banyak conflicting signals)
3. Divergence menunjukkan arah berlawanan

---

## Configuration File Structure

```python
# advanced_crypto_bot/core/signal_config.py

SIGNAL_ENHANCEMENT_CONFIG = {
    "volume_check": {
        "enabled": True,
        "min_volume_idr": 100_000_000,  # 100 juta IDR
        "weight": 0.15
    },
    "vwap": {
        "enabled": True,
        "period": 14,
        "weight": 0.10
    },
    "ichimoku": {
        "enabled": True,
        "conversion_period": 9,
        "base_period": 26,
        "span_b_period": 52,
        "delay_period": 26,
        "weight": 0.12
    },
    "divergence": {
        "enabled": True,
        "lookback": 20,
        "rsi_period": 14,
        "weight": 0.15
    },
    "candlestick_patterns": {
        "enabled": True,
        "lookback": 3,
        "weight": 0.10
    }
}
```

### Environment Variables
```
# .env additions
ENABLE_VOLUME_CHECK=true
ENABLE_VWAP=true
ENABLE_ICHIMOKU=true
ENABLE_DIVERGENCE=true
ENABLE_CANDLESTICK_PATTERNS=true

# Thresholds
MIN_VOLUME_IDR=100000000
VWAP_PERIOD=14
ICHIMOKU_CONVERSION=9
```

---

## Testing Plan

1. **Unit Tests**: Setiap feature sendiri
2. **Integration Test**: Semua feature berjalan bersama
3. **Backtest**: Test di data historis untuk validasi
4. **Live Test**: Monitor signal selama 1-2 minggu

---

## Estimated Impact

| Feature | Complexity | Impact | Priority |
|---------|------------|--------|----------|
| Volume Check | Low | Medium | 1 |
| VWAP | Low | Medium | 2 |
| Candlestick | Medium | High | 3 |
| Divergence | High | High | 4 |
| Ichimoku | Medium | High | 5 |

---

Dokumen ini akan di-update seiring implementasi. Silakan review dan approve sebelum saya implementasikan.