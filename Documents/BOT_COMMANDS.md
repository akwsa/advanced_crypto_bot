# Advanced Crypto Bot - Documentation Lengkap

## Daftar Isi

1. [ML Model V3](#ml-model-v3)
2. [Commands Biasa](#commands-biasa)
3. [Priority 1 - Backtest Commands](#priority-1---backtest-commands)
4. [Priority 2 - Advanced Commands](#priority-2---advanced-commands)
5. [Troubleshooting](#troubleshooting)

---

## ML Model V3

### Apa bedanya dari V2?

| Feature | ML V2 | ML V3 (PRO) |
|---------|-------|-------------|
| Target | Return % | Risk/Reward based (>2:1) |
| Features | ~40 | 50+ |
| Backtesting | Basic | Full with fees |
| Position Sizing | Fixed % | Kelly Criterion |
| Market Regime | None | Full detection |
| Dry-Run | Manual | Automated |

### Training ML V3

```bash
/retrain
```

- Sebelum: Hanya baca dari `Config.WATCH_PAIRS` (statis)
- Sesudah: Baca dari semua pair di database (termasuk auraidr, pixelidr, zenidr, dll)

---

## Commands Biasa

### `/status`
Cek status bot keseluruhan.

### `/watch`
Lihat watchlist pair.

### `/trades`
List semua trades.

### `/add_autotrade <PAIR>`
Tambahkan pair ke auto-trade list.

### `/remove_autotrade <PAIR>`
Hapus pair dari auto-trade list.

### `/autotrade`
Toggle auto-trading (dry-run/live).

---

## Priority 1 - Backtest Commands

### `/backtest_v3 <PAIR> <DAYS>`

PRO backtest menggunakan ML V3 dengan semua biaya disimulasikan.

```
Usage: /backtest_v3 <PAIR> <DAYS>

Examples:
/backtest_v3 btcidr 30
/backtest_v3 ethidr 7
/backtest_v3 solidr 90
```

**Features:**
- Risk/Reward based signals
- All fees simulated (0.3% + slippage)
- Kelly Criterion position sizing
- Comprehensive metrics

**Output:**
- Initial/Final Balance
- Total Profit
- Win Rate
- Max Drawdown
- Profit Factor
- Sharpe Ratio
- Total Fees

---

### `/dryrun <PAIR> <INITIAL_BALANCE>`

Dry-run simulation - simulate trades WITHOUT executing real orders.

```
Usage: /dryrun <PAIR> <INITIAL_BALANCE>

Examples:
/dryrun btcidr
/dryrun ethidr 10000000
```

**Note:** No real orders placed. Untuk testing strategy only.

---

### `/regime <PAIR>`

Detect current market regime.

```
Usage: /regime <PAIR>

Examples:
/regime btcidr
/regime
```

**Output:**
- Volatility (HIGH/NORMAL/LOW)
- Trend (UPTREND/DOWNTREND/SIDEWAYS)
- Volume (HIGH/NORMAL/LOW)
- Recommended Position Size

---

### `/retrain`

Training ulang ML model dengan semua pair di database.

```
/retrain
```

- Otomatis detect semua pair yang ada di database
- Termasuk pairs baru seperti auraidr, pixelidr, zenidr, chillguyidr
- Training di background - bot tetap responsive

---

## Priority 2 - Advanced Commands

### `/kelly`

Kelly Criterion position sizing calculator.

```
Usage: /kelly <WIN_RATE> <AVG_WIN> <AVG_LOSS>

Examples:
/kelly                    # Auto dari trade history
/kelly 0.6 200000 100000  # Manual input
```

**Formula:**
```
K% = W - (1-W)/R

Dimana:
W = Win Rate
R = Win/Loss Ratio
```

**Output:**
- Win Rate
- Average Win/Loss
- Kelly Percentage (full)
- Kelly Percentage (50% fractional)
- Recommended Position Size
- Expected Value per trade

**Note:** Menggunakan 50% Kelly untuk safety. Max recommended: 30%

---

### `/compare <DAYS>`

Multi-pair backtest comparison.

```
Usage: /compare <DAYS>

Examples:
/compare 30
/compare 7
```

**Features:**
- Backtest semua pair di database
- Sort by profit percentage
- Show win rate & profit factor
- Highlight best performer

**Output:**
```
📊 Pair Comparison (30 days)

🟢 btcidr     +5.2%  WR:60%  Pf:1.8
🔴 ethidr    -2.1%  WR:45%  Pf:0.9
🔴 dogeidr   -8.5%  WR:35%  Pf:0.7

🏆 Top Performer: btcidr (+5.2%)
```

---

## Signal Enhancement Features

### VWAP (Volume Weighted Average Price)
- **Arti**: Harga rata-rata transaksi dibobot dengan volume
- **Guna**:
  - Harga > VWAP = Trend naik (Bullish)
  - Harga < VWAP = Trend turun (Bearish)

### Ichimoku Cloud
- **Arti**: Indikator teknikal Japanese
- **Guna**: Detect trend & momentum
- **Components**:
  - Tenkan-sen (conversion line)
  - Kijun-sen (base line)
  - Senkou Span (cloud)

### Enhancement Adjustment
- Confidence bisa di-adjust berdasarkan feature analysis
- Contoh: `Confidence adjusted 50.0% → 62.0% (adjustment: +0.12, features: ['vwap', 'ichimoku'])`

---

## S/R Validation

### Threshold (di .env)
```
SR_MIN_RR_RATIO=0.8
```

- Signals dengan Risk/Reward ratio < 0.8 akan di-reject
- Akan ada message: `Signal rejected: Risk/Reward ratio too low (0.57 < 0.80)`

---

## Troubleshooting

### Error: 'NoneType' object has no attribute 'tree_'
**Cause**: Model V2 belum di-train
**Fix**: Run `/retrain` dulu

### Error: 'MLTradingModelV3' object has no attribute 'get_market_regime'
**Cause**: Bot belum di-restart setelah update
**Fix**: Restart bot

### Signal colors tidak bekerja
**Cause**: Cache lama
**Fix**: Restart bot

### /retrain tidak dapat pair baru
**Cause**: Menggunakan Config.WATCH_PAIRS yang statis
**Fix**: sudah diperbaiki - sekarang baca dari database

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `/status` | Bot status |
| `/watch` | Watchlist |
| `/trades` | Trade history |
| `/backtest_v3` | PRO backtest |
| `/dryrun` | Dry-run simulation |
| `/regime` | Market regime |
| `/retrain` | Training |
| `/kelly` | Kelly sizing |
| `/compare` | Pair comparison |

---

## Catatan

- Semua commands pake prefix `/`
- Untuk pair, gunakan format `btcidr` (bukan `BTCIDR`)
- Untuk Days, gunakan angka 1-365
- Admin only: `/backtest_v3`, `/retrain`, `/compare`

---

*Last updated: 19/04/2026*