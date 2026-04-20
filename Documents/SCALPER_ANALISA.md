# 📊 Fitur Analisa Pair - Scalper Module

## ✨ Fitur Baru

Scalper module sekarang memiliki fitur **analisa teknikal** yang sama dengan bot utama!

## 📝 Cara Menggunakan

### Analisa Pair
```
/s_analisa <pair>
```

**Contoh:**
```
/s_analisa bridr
/s_analisa pippinidr
/s_analisa stoidr
```

## 📈 Output Analisa

Bot akan menampilkan:

```
⏸️ BR/IDR - Trading Signal

💰 Price: 2,448 IDR

🎯 Recommendation: HOLD

📈 Technical Indicators:
• RSI (14): NEUTRAL (52.3)
• MACD: BULLISH
• MA Trend: BEARISH
• Bollinger: NEUTRAL
• Volume: NORMAL

🤖 ML Prediction:
• Confidence: 56.0%
• Combined Strength: -0.15

💡 Analysis: ML confidence too low

⏰ 14:32:15
```

## 🔍 Indikator yang Digunakan

1. **RSI (14)** - Relative Strength Index
   - OVERSOLD (< 30) = Potensi naik
   - OVERBOUGHT (> 70) = Potensi turun
   - NEUTRAL (30-70) = Stabil

2. **MACD** - Moving Average Convergence Divergence
   - BULLISH = MACD di atas signal line
   - BEARISH = MACD di bawah signal line

3. **MA Trend** - Moving Average
   - BULLISH = Harga di atas SMA 20 & 50
   - BEARISH = Harga di bawah SMA 20 & 50
   - NEUTRAL = Campuran

4. **Bollinger Bands**
   - OVERSOLD = Harga di bawah lower band
   - OVERBOUGHT = Harga di atas upper band
   - NEUTRAL = Di tengah

5. **Volume**
   - HIGH = Volume 2x di atas rata-rata
   - LOW = Volume di bawah 50% rata-rata
   - NORMAL = Volume normal

## 🤖 ML Prediction

Meskipun scalper tidak menggunakan model ML yang sebenarnya (seperti bot utama), fitur ini memberikan **pseudo-ML prediction** berdasarkan:
- Jumlah sinyal bullish vs bearish
- Confidence score (0-100%)
- Combined strength (-1 sampai +1)

## 📊 Rekomendasi

- **STRONG BUY** 🚀 - Semua indikator bullish
- **BUY** 📈 - Mayoritas bullish
- **HOLD** ⏸️ - Campuran atau confidence rendah
- **SELL** 📉 - Mayoritas bearish
- **STRONG_SELL** 🔻 - Semua indikator bearish

## 💡 Tips

1. Gunakan sebelum entry untuk konfirmasi sinyal
2. Pair harus sudah ditambahkan dengan `/s_pair add`
3. Minimal 60 candle data diperlukan
4. Data diambil dari Indodax API (trade history)
5. Resample ke candle 1 menit

## ⚠️ Catatan Penting

- Analisa bersifat **informatif**, bukan saran trading
- Selalu gunakan risk management (TP/SL)
- Confidence < 60% = sinyal lemah, tunggu konfirmasi
- Gunakan bersama dengan command lain: `/s_pair`, `/s_posisi`, `/s_menu`

## 🔄 Command Scalper Lainnya

```
/s_menu - Menu utama
/s_pair - Manajemen pair
/s_posisi - Lihat posisi aktif
/s_buy <pair> - Buy manual
/s_sell <pair> - Sell manual
/s_sltp <pair> <tp> <sl> - Set TP/SL
/s_cancel <pair> - Cancel TP/SL
/s_info <pair> - Info posisi
/s_analisa <pair> - Analisa teknikal (BARU!)
/s_reset - Reset semua posisi
```
