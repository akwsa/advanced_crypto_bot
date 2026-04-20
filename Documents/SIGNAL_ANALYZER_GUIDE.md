# 📊 Signal Analyzer Module - User Guide

**Modul**: `analysis/signal_analyzer.py`  
**Command Telegram**: `/signal_quality`, `/signal_report`  
**Status**: ✅ FIXED & READY

---

## Overview

Signal Analyzer adalah modul yang menganalisis **historical signal accuracy** untuk membantu user membuat keputusan trading (BUY / HOLD / SELL).

**Apa yang dianalisis:**
- Win rate per pair dan per signal type (BUY/SELL)
- Rata-rata profit/loss
- Optimal hold time
- Signal quality score (1-10)
- Grade (A/B/C/D/F)

**Data Source:**
- `data/signals.db` - Historical signals
- `data/trading.db` - Price history untuk validasi

---

## 🚀 Cara Penggunaan

### Command Telegram

#### 1. `/signal_quality <PAIR> [TYPE]`
Analisis kualitas signal untuk pair tertentu.

**Contoh:**
```
/signal_quality btcidr           # Analisis semua signal types
/signal_quality btcidr BUY       # Analisis BUY signals saja
/signal_quality ethidr SELL      # Analisis SELL signals saja
```

**Output:**
```
🔍 BTCIDR Signal Quality (BUY)
════════════════════════════════════════════════════
📊 Signals: 45 analyzed (30 days)
🎯 Win Rate: 68.9%
💰 Avg Profit: +3.2%
📉 Avg Loss: -1.9%
⏱️ Optimal Hold: 3.5h
⭐ Score: 7/10 — 👍 GOOD
Grade: B
════════════════════════════════════════════════════
✅ RECOMMENDED for trading
```

#### 2. `/signal_report`
Laporan komprehensif untuk semua pair.

---

## 📈 Understanding the Metrics

### 1. Win Rate
Persentase signal yang profitable.
- **>70%**: Excellent
- **60-70%**: Good
- **50-60%**: Average
- **<50%**: Poor (avoid)

### 2. Average Profit
Rata-rata profit dari winning signals.
- **>3%**: Strong
- **2-3%**: Good
- **<2%**: Weak

### 3. Average Loss
Rata-rata loss dari losing signals (estimasi).
- Gunakan untuk risk/reward calculation

### 4. Optimal Hold Time
Rata-rata waktu optimal untuk hold position.
- Berdasarkan kapan harga terbaik tercapai
- Format: jam

### 5. Score (1-10)
Kombinasi dari:
- Win rate (40%)
- Average profit (20%)
- Total signals/data volume (20%)
- ML confidence (20%)

### 6. Grade
- **A (8-10)**: Excellent — Auto-trade recommended
- **B (6-7)**: Good — Trade with standard position size
- **C (4-5)**: Average — Trade with reduced size or skip
- **D (1-3)**: Poor — Avoid trading this pair
- **F**: Error/No data

---

## 🎯 How to Use for Trading Decisions

### Scenario 1: Signal Baru Muncul

**Bot**: "🔔 BTCIDR STRONG_BUY detected!"

**Action**: Check signal quality dulu
```
/signal_quality btcidr BUY
```

**Decision Matrix:**
| Score | Grade | Decision |
|-------|-------|----------|
| 8-10 | A | ✅ Trade immediately — High confidence |
| 6-7 | B | ✅ Trade dengan position size normal |
| 4-5 | C | ⚠️ Reduced size atau tunggu konfirmasi |
| 1-3 | D | ❌ Skip — Pair tidak perform dengan baik |

### Scenario 2: Compare Multiple Pairs

```
/signal_quality btcidr BUY
/signal_quality ethidr BUY
/signal_quality solidr BUY
```

Pilih pair dengan **highest score**.

### Scenario 3: Check SELL Opportunities

```
/signal_quality btcidr SELL
```

**Important**: SELL signals menggunakan **short selling logic** — profit ketika harga turun.

---

## 🔧 Technical Details

### Profit Calculation Logic

**BUY Signals:**
```
profit_pct = ((max_price - entry_price) / entry_price) * 100
```
- Entry: Signal price
- Exit: Highest price dalam 24 jam
- Profit: Price naik ✓

**SELL Signals:**
```
profit_pct = ((entry_price - min_price) / entry_price) * 100
```
- Entry: Signal price (short sell)
- Exit: Lowest price dalam 24 jam (buy back)
- Profit: Price turun ✓

**HOLD Signals:**
```
profit_pct = ((exit_price - signal_price) / signal_price) * 100
```
- Analyzed sebagai "would have been good BUY opportunity?"

### Minimum Data Requirements
- Minimum 5 signals untuk analisis dasar
- Minimum 20 signals untuk reliable grade
- Data dari 30 hari terakhir

---

## 📊 Sample Analysis Report

```
📊 SIGNAL QUALITY REPORT — BTCIDR
════════════════════════════════════════════════════

🔍 BUY Analysis:
  📊 Signals: 124 (30 days)
  🎯 Win Rate: 72.6%
  💰 Avg Profit: +3.8%
  📉 Avg Loss: -2.3%
  ⏱️ Optimal Hold: 4.2h
  ⭐ Score: 8/10 — ✅ EXCELLENT

🔍 SELL Analysis:
  📊 Signals: 45 (30 days)
  🎯 Win Rate: 64.4%
  💰 Avg Profit: +2.9%
  📉 Avg Loss: -1.8%
  ⏱️ Optimal Hold: 3.1h
  ⭐ Score: 6/10 — 👍 GOOD

🔍 HOLD Analysis:
  📊 Signals: 89 (30 days)
  🎯 Win Rate: 51.7% (price went up)
  💰 Avg Profit: +1.2%
  ⭐ Score: 5/10 — ⚠️ AVERAGE

💡 RECOMMENDATION:
✅ BUY signals on BTCIDR — Excellent track record
⚠️ SELL signals — Good but limited data
⚠️ HOLD → BUY conversion: Average, be cautious

════════════════════════════════════════════════════
```

---

## 🎓 Best Practices

### 1. Always Check Quality Before Trading
```
/signal_quality <pair> <type>
```
Jangan trade tanpa cek signal quality terlebih dahulu.

### 2. Focus on Grade A & B
- Grade A: 8-10 score — Highest confidence
- Grade B: 6-7 score — Good opportunities
- Skip Grade C/D kecuali ada alasan kuat

### 3. Consider Win Rate + Profit Together
- High win rate + Low profit = Consistent small wins
- Lower win rate + High profit = Big wins but inconsistent
- Prefer: High win rate (60%+) dengan avg profit >2%

### 4. Monitor Optimal Hold Time
- Jangan hold terlalu lama dari rekomendasi
- Set auto exit setelah optimal hold time

### 5. Review Regularly
```
/signal_report
```
Lakukan weekly review untuk identify pairs dengan degrading performance.

---

## 🐛 Troubleshooting

### "No data available"
- Pair baru atau belum ada signal history
- Tunggu beberapa hari sampai cukup data terkumpul

### "Grade C/F"
- Pair tidak perform dengan baik
- Consider stop trading pair tersebut

### "Low win rate but high profit"
- Volatile pair dengan big wins dan big losses
- Use reduced position size

### "High win rate but low profit"
- Safe pair dengan consistent small wins
- Good untuk compounding

---

## 🔗 Integration with Bot

Signal Analyzer digunakan di:
- `/signal_quality` command (bot.py:5638)
- `/signal_report` command (bot.py:5779)
- Auto-quality check sebelum trade (opsional)

---

## 📁 Files

| File | Purpose |
|------|---------|
| `analysis/signal_analyzer.py` | Core analysis module |
| `tools/analyze_signals.py` | Standalone analysis script |
| `data/signals.db` | Signal history data |
| `data/trading.db` | Price history data |

---

## ✅ Recent Fixes (2026-04-14)

### Fix #1: SELL Signal Logic
**Problem**: Perhitungan profit untuk SELL signals salah — menggunakan logika BUY.
**Fix**: SELL signals sekarang menggunakan short selling logic (profit ketika harga turun).

### Fix #2: HOLD Signal Analysis
**Problem**: HOLD signals tidak dianalisis dengan baik.
**Fix**: HOLD signals sekarang dianalisis sebagai "would have been good BUY opportunity?"

---

**Last Updated**: 2026-04-14  
**Version**: 1.1.0
