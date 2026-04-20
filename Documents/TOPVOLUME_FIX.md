# Fix: Command `/topvolume` → Top 50 Volume (Descending)

## Masalah
Command `/topvolume` sebelumnya menampilkan Top 20 pair by volume.

## Solusi
Command `/topvolume` sekarang menampilkan **Top 50 pair by Volume 24h** dari Indodax, diurutkan descending (tertinggi ke terendah).

## Perubahan

### File: `bot.py`
- **Function:** `top_volume()`
- **Sebelum:** `top_20 = all_tickers[:20]`
- **Setelah:** `top_50 = all_tickers[:50]`
- **Header:** "TOP 20 VOLUME" → "TOP 50 VOLUME"
- **Loading message:** "Loading Top Volume" → "Loading Top 50 Volume"

### File: `COMMANDS_GUIDE.md`
- Updated deskripsi: "Top 20 pair by Volume 24h" → "Top 50 pair by Volume 24h (descending)"

## Cara Kerja

```
1. Bot fetch semua ticker dari Indodax API (/api/summaries)
2. Sort by volume (descending) → volume tertinggi di atas
3. Ambil Top 50 pair
4. Tampilkan dalam format tabel:
   • Rank | Pair | Volume 24h (IDR) | Price | 24h Change
5. Format volume:
   • >= 1M IDR → "1.23M" (Juta)
   • >= 1Jt IDR → "1.2Jt" (Juta)
   • >= 1Rb IDR → "1,234Rb" (Ribu)
```

## Response Bot

```
📊 TOP 50 VOLUME (24h)

🕐 14:32:15 WIB

Rank | Pair | Volume 24h (IDR) | Price | 24h Change
━━━━━━┿━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━┿━━━━━━━━━━━━
 1. BTC/IDR      2.45M    1,456,789,012 🟢 +2.34%
 2. ETH/IDR      1.87M      87,654,321 🔴 -1.23%
 3. SOL/IDR      1.23M       3,456,789 🟢 +5.67%
...
50. XYZ/IDR     12.3K           1,234 ⚪ -

💡 Tips:
• Volume tinggi = Likuiditas bagus
• 🟢/+ = Naik dari low 24h | 🔴/- = Turun
• ⚪/- = Tidak ada pergerakan (pair tidak aktif)
• Gunakan /watch <pair> untuk monitoring
• Gunakan /signal <pair> untuk analisa
• ⚠️ DYOR! Volume ≠ Profit guarantee
```

## Testing
- ✅ Syntax check: `python -m py_compile bot.py` - PASSED
- ⏳ Runtime test: Jalankan bot → `/topvolume`

## Expected Behavior
✅ **Command `/topvolume`:**
- Menampilkan Top 50 pair by volume 24h
- Diurutkan descending (tertinggi di atas)
- Volume dalam format Rupiah (M, Jt, Rb)
- Include harga terakhir & perubahan 24h
- Tips penggunaan di bagian bawah
