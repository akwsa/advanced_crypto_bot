"""
Quick Analysis: Apakah signals menghasilkan profit?
"""
import sqlite3
import pandas as pd
import numpy as np

# Load data
conn = sqlite3.connect('data/signals.db')
df = pd.read_sql("""
    SELECT symbol, price, recommendation, rsi, macd, ma_trend, bollinger, volume,
           ml_confidence, combined_strength, received_at
    FROM signals
    WHERE ml_confidence > 0
""", conn)
conn.close()

print("=" * 70)
print("  ANALISIS: KAPAN BUY/SELL TERJADI?")
print("=" * 70)

# 1. Distribusi recommendation
print("\n📊 DISTRIBUSI RECOMMENDATION:")
print(df['recommendation'].value_counts().to_string())

# 2. Average price per recommendation
print("\n💰 RATA-RATA HARGA PER RECOMMENDATION:")
avg_prices = df.groupby('recommendation')['price'].agg(['mean', 'median', 'min', 'max'])
print(avg_prices.to_string())

# 3. TA conditions per recommendation
print("\n📈 KONDISI TA PER RECOMMENDATION:")
for rec in ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']:
    subset = df[df['recommendation'] == rec]
    print(f"\n{rec} ({len(subset)} signals):")
    print(f"   RSI:        {subset['rsi'].value_counts().head(3).to_dict()}")
    print(f"   MACD:       {subset['macd'].value_counts().head(3).to_dict()}")
    print(f"   MA Trend:   {subset['ma_trend'].value_counts().head(3).to_dict()}")
    print(f"   Confidence: {subset['ml_confidence'].mean():.3f} (avg)")
    print(f"   Strength:   {subset['combined_strength'].mean():.3f} (avg)")

# 4. Price ranges - when does STRONG_BUY vs BUY happen?
print("\n" + "=" * 70)
print("  PERBANDINGAN: STRONG_BUY vs BUY")
print("=" * 70)

strong_buy = df[df['recommendation'] == 'STRONG_BUY']
buy = df[df['recommendation'] == 'BUY']

print(f"\nSTRONG_BUY avg confidence: {strong_buy['ml_confidence'].mean():.3f}")
print(f"BUY avg confidence:        {buy['ml_confidence'].mean():.3f}")
print(f"STRONG_BUY avg strength:   {strong_buy['combined_strength'].mean():.3f}")
print(f"BUY avg strength:          {buy['combined_strength'].mean():.3f}")

# 5. Check: Apakah STRONG_BUY selalu di harga rendah (good entry)?
print("\n💡 PRICE DISTRIBUTION BY RECOMMENDATION:")
for rec in ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']:
    subset = df[df['recommendation'] == rec]
    median_price = subset['price'].median()
    print(f"   {rec:<15} Median: Rp {median_price:>15,.0f}")

# 6. Time-based analysis
df['received_at'] = pd.to_datetime(df['received_at'])
df['hour'] = df['received_at'].dt.hour
print("\n⏰ SIGNALS BY HOUR:")
hourly = df.groupby(['hour', 'recommendation']).size().unstack(fill_value=0)
print(hourly.to_string())

print("\n" + "=" * 70)
print("  KESIMPULAN SEMENTARA")
print("=" * 70)
print("""
Masalah yang terdeteksi:
1. ml_confidence & combined_strength SUDAH berisi "jawaban"
2. Model tidak belajar dari TA (RSI, MACD, MA)
3. Tidak ada ground truth "apakah signal ini profit?"
   - Bot cuma save recommendation, bukan apakah trade berhasil

Solusi:
- Hapus ml_confidence & combined_strength dari features
- Model harus belajar dari TA murni (RSI, MACD, MA, BB, Volume)
""")
