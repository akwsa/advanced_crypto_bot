# 🧪 Cara Enable Auto-Trade Dry Run

## Masalah: Auto-Trade Belum Running

Jika di Telegram muncul pesan posisi tapi **tidak ada tanda auto-trade running**, ikuti langkah ini:

---

## ✅ Langkah-langkah Enable Dry Run

### Step 1: Enable Auto-Trade Mode

Kirim command di Telegram:
```
/autotrade dryrun
```

**Expected Response:**
```
🧪 AUTO-TRADING: DRY RUN MODE 🧪

✅ Simulation Mode ACTIVE

🤖 Bot will simulate:
• Scanning watched pairs every 5 minutes
• Generating BUY/SELL signals (confidence >65%)
• Applying Stop Loss (-2%) & Take Profit (+5%)
• Enforcing risk limits (max 5% daily loss)

📋 What happens in DRY RUN:
• ✅ Signals generated and analyzed
• ✅ Trades SIMULATED (no real orders)
• ✅ Virtual balance tracked
• ✅ P&L calculated (simulated only)
• ❌ NO real money used
• ❌ NO actual orders sent to Indodax
```

### Step 2: Tambahkan Pair ke Watchlist

Bot hanya akan scan pair yang ada di watchlist:
```
/watch BTC/IDR
/watch ETH/IDR
/watch DOGE/IDR
```

**Expected Response:**
```
✅ Watching BTC/IDR

• Real-time updates: 🟢 Active
• ML predictions: 🟢 Enabled
• Auto-trading: 🟢 On

You'll receive instant notifications!
```

### Step 3: Tunggu Data Masuk (5-10 menit)

Bot perlu:
- WebSocket connect ke Indodax
- Collect minimal 60 candles data
- ML model generate signals

### Step 4: Cek Status

```
/autotrade_status
```

**Expected Response (Dry Run Active):**
```
🤖 AUTO-TRADING STATUS

📊 Status: 🟢 ACTIVE

🧪 Mode: DRY RUN (Simulation)
• ⚠️ NO real money being used
• ✅ All trades are simulated for testing

📈 Today's Activity (2026-04-04):
• Total Auto Trades: 3
  - 🧪 Dry Run: 3
• Wins: 2 | Losses: 1
• P&L: `+75,000` IDR

📋 Recent Auto-Trades:
🧪 ✅ BUY BTC/IDR
   P&L: +50,000 IDR
🧪 ❌ BUY ETH/IDR
   P&L: -25,000 IDR
```

---

## 🔍 Verifikasi Dry Run Sedang Running

### Check 1: di /position atau /signals

Sekarang di setiap command `/position` dan `/signals` akan muncul:

```
🤖 AUTO-TRADE STATUS:
🧪 DRY RUN MODE - Aktif (Simulasi)
• ✅ Bot scanning setiap 5 menit
• ✅ Simulasi trade (no real money)
• 📊 Use /autotrade_status untuk detail
```

### Check 2: di Logs

Check file `logs/trading_bot.log`:
```
🧪 DRY RUN Scanning BTC/IDR for auto-trade opportunity...
🧪 [DRY RUN] Simulated BUY for BTC/IDR: 0.0015 @ 1650000000
```

### Check 3: Telegram Notification

Jika ada signal kuat, akan muncul:
```
🧪 DRY RUN: SIMULATED TRADE 🧪

📊 Pair: BTC/IDR
💡 Action: BUY (SIMULATED)
💰 Price: 1,650,000,000 IDR
...

⚠️ This is a SIMULATION
• No real money used
• No actual order placed
• For testing only
```

---

## ❌ Troubleshooting

### Problem 1: "Auto-Trade: OFF" di message

**Solution:**
```
/autotrade dryrun
```

### Problem 2: Tidak ada trade muncul setelah 10+ menit

**Possible causes:**

1. **Tidak ada pair di watchlist**
   ```
   /watch BTC/IDR
   ```

2. **Data belum cukup (butuh 60+ candles)**
   - Tunggu 10-15 menit
   - Bot collect data dari WebSocket

3. **Signal confidence terlalu rendah**
   - Bot hanya trade jika confidence > 65%
   - Market mungkin sedang sideways/choppy

4. **Daily trade limit reached**
   - Max 10 trades per hari
   - Tunggu besok atau reset

### Problem 3: Error di logs

Check `logs/trading_bot.log`:
```bash
tail -f logs/trading_bot.log | grep -i "dry run"
```

### Problem 4: WebSocket tidak connect

Restart bot:
```bash
python bot.py
```

---

## 🎯 Quick Command Reference

| Command | Fungsi |
|---------|--------|
| `/autotrade dryrun` | Enable simulasi mode |
| `/autotrade real` | Enable real trading ⚠️ |
| `/autotrade off` | Disable auto-trade |
| `/autotrade` | Toggle (keep current mode) |
| `/autotrade_status` | Check detail status |
| `/watch <PAIR>` | Add pair ke watchlist |
| `/position <PAIR>` | Check posisi + status |
| `/signals` | Lihat semua signals |

---

## 📊 Contoh Flow Lengkap

```
1. /autotrade dryrun
   ✅ DRY RUN MODE enabled

2. /watch BTC/IDR
   ✅ Watching BTC/IDR

3. /watch ETH/IDR
   ✅ Watching ETH/IDR

4. [Tunggu 10 menit]

5. /autotrade_status
   📊 Status: 🟢 ACTIVE
   🧪 Mode: DRY RUN
   • Total Auto Trades: 2
   • Wins: 1 | Losses: 1
   • P&L: +25,000 IDR

6. /position BTC/IDR
   🤖 AUTO-TRADE STATUS:
   🧪 DRY RUN MODE - Aktif (Simulasi)
   • ✅ Bot scanning setiap 5 menit

7. [Terima notifikasi]
   🧪 DRY RUN: SIMULATED TRADE 🧪
   📊 Pair: BTC/IDR
   💡 Action: BUY (SIMULATED)
```

---

## 🔒 Safety Checklist

Sebelum switch ke REAL trading:

- [ ] Dry run sudah jalan minimal 1-2 minggu
- [ ] Win rate > 50%
- [ ] Virtual P&L positif
- [ ] Paham cara kerja SL/TP
- [ ] API keys Indodax sudah ready
- [ ] Siap start dengan amount kecil

---

## 💡 Tips

1. **Gunakan Dry Run minimal 1 minggu** sebelum real trading
2. **Monitor P&L virtual** di `/autotrade_status`
3. **Tambahkan lebih banyak pairs** untuk lebih banyak opportunities
4. **Check logs** untuk verify scanning jalan
5. **Jangan lupa**: Dry run TIDAK menggunakan uang sungguhan

---

**Dry Run adalah safety net kamu. Gunakan dengan bijak!** 🛡️
