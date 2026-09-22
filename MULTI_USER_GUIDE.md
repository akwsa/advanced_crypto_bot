# 👥 Multi-User Setup Guide

## 📋 Overview

Bot ini **sudah support multiple users** secara native. Setiap user dapat memiliki:
- ✅ Watchlist pribadi
- ✅ Auto-trade pairs pribadi  
- ✅ Portfolio terpisah
- ✅ Balance tracking pribadi
- ✅ Signal notifications pribadi

## 🔐 User Access Levels

### 1. **Admin Users** (Full Access)
- Akses semua fitur bot
- Command priviledged (`/retrain`, `/status`, `/logs`)
- Dapat melihat data semua user
- Kontrol penuh atas bot

**Konfigurasi di `.env`:**
```bash
ADMIN_IDS=123456789,987654321,111222333
```

### 2. **Regular Users** (Limited Access)
- Dapat menggunakan bot untuk signals & portfolio pribadi
- Tidak bisa akses data user lain
- Tidak bisa command admin (retrain, system control)

**Setup:**
User biasa tidak perlu dikonfigurasi. Mereka tinggal `/start` bot dan langsung bisa pakai untuk keperluan pribadi.

## 📱 Cara Mendapatkan Telegram User ID

Setiap user perlu tahu User ID mereka:

1. Buka Telegram
2. Search: **@userinfobot**
3. Klik **Start**
4. Bot akan reply dengan User ID (contoh: `123456789`)
5. Copy ID tersebut

## 🚀 Setup Multi-User

### Skenario 1: Bot untuk Tim Trading (3-5 orang)

**File: `.env`**
```bash
# Semua anggota tim sebagai admin
ADMIN_IDS=123456789,987654321,111222333,444555666

# Telegram Bot Token (sama untuk semua)
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# Trading settings (berlaku untuk semua user)
AUTO_TRADING_ENABLED=false
AUTO_TRADE_DRY_RUN=true
WATCH_PAIRS=btcidr,ethidr,bridr,pippinidr,solidr
```

**Setiap user dapat:**
- Add pairs ke watchlist pribadi: `/watch fartcoinidr`
- View portfolio sendiri: `/portfolio`
- Get signals: `/signal btcidr`
- Trading dengan balance pribadi

### Skenario 2: Bot untuk Channel/Grup Signal

**File: `.env`**
```bash
# Hanya owner channel sebagai admin
ADMIN_IDS=123456789

# Bot token
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# Pairs yang di-monitor
WATCH_PAIRS=btcidr,ethidr,bridr,dogeidr,shibidr,solidr,pippinidr
```

**Member channel:**
- Tidak perlu didaftarkan
- Tinggal `/start` bot
- Bisa `/signal` untuk cek pair tertentu
- Tidak bisa retrain atau ubah config

### Skenario 3: Bot untuk Keluarga/Teman (Personal Use)

**File: `.env`**
```bash
# Beberapa nomor keluarga sebagai admin
ADMIN_IDS=123456789,987654321,555666777

# Bot token
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# Pairs favorit keluarga
WATCH_PAIRS=btcidr,ethidr,bridr,solidr,pippinidr

# Trading settings (simulation mode untuk safety)
AUTO_TRADING_ENABLED=false
AUTO_TRADE_DRY_RUN=true
```

**Keuntungan:**
- Setiap anggota punya watchlist sendiri
- Portfolio terpisah per user
- Notifikasi pribadi
- Saling tidak mengganggu

## 🔄 Menambah User Baru

### Method 1: Edit `.env` (Recommended)

**Di VPS:**
```bash
# Stop bot
sudo systemctl stop crypto-bot

# Edit .env
nano /opt/crypto-bot/advanced_crypto_bot/.env

# Tambahkan User ID baru
ADMIN_IDS=123456789,987654321,999888777

# Restart bot
sudo systemctl restart crypto-bot
```

### Method 2: Tanpa Restart (Runtime)

**Kirim command dari admin existing:**
```
/add_admin 999888777
```

Bot akan add user baru ke admin list tanpa perlu restart.

## 📊 Fitur Per-User

### Watchlist (Personal)

**User A:**
```
/watch btcidr,ethidr
/watchlist
→ BTC/IDR, ETH/IDR
```

**User B:**
```
/watch pippinidr,solidr
/watchlist
→ PIPPIN/IDR, SOLID/IDR
```

**Watchlist mereka terpisah!** User A tidak lihat watchlist User B, dan sebaliknya.

### Portfolio (Personal)

**User A:**
```
/trade buy btcidr 1000000
/portfolio
→ Shows User A's portfolio only
```

**User B:**
```
/trade buy ethidr 500000
/portfolio
→ Shows User B's portfolio only
```

**Portfolio terpisah per user!** Tidak saling overlap.

### Auto-Trade (Personal)

**User A:**
```
/add_autotrade btcidr,ethidr
/autotrade list
→ BTC/IDR, ETH/IDR
```

**User B:**
```
/add_autotrade pippinidr
/autotrade list
→ PIPPIN/IDR
```

**Auto-trade pairs terpisah!** Bot akan execute trades sesuai konfigurasi masing-masing user.

## 🔔 Notification System

### Signal Notifications (Personal)

Bot mengirim notifikasi signal **hanya** ke user yang watch pair tersebut.

**Contoh:**
- **User A** watch: `btcidr, ethidr`
- **User B** watch: `pippinidr`

Jika signal **BTC/IDR** muncul:
- ✅ User A dapat notifikasi
- ❌ User B tidak dapat notifikasi

### Broadcast (Admin Only)

Admin dapat broadcast message ke semua user:
```
/broadcast Halo semua, bot akan maintenance 10 menit
```

Semua user yang pernah `/start` bot akan menerima message.

## 🛡️ Security & Privacy

### Data Isolation

✅ **Setiap user memiliki:**
- Watchlist pribadi (di DB: `user_watchlist` table)
- Portfolio pribadi (di DB: `user_trades` table)
- Balance tracking pribadi (di DB: `user_balance` table)

✅ **User A tidak bisa:**
- Lihat portfolio User B
- Ubah watchlist User B
- Akses balance User B

### Admin Privileges

✅ **Admin dapat:**
- Retrain ML model (`/retrain`)
- View system status (`/status`)
- View logs (`/logs`)
- Broadcast messages (`/broadcast`)
- View all users data (untuk monitoring)

❌ **Regular user tidak bisa:**
- Akses command admin
- Ubah config bot
- Retrain model
- Broadcast message

### API Key Isolation (Important!)

⚠️ **PERHATIAN:** Semua user menggunakan **API key yang sama** dari `.env`

**Jika AUTO_TRADING_ENABLED=true:**
- Semua trades execute dengan API key yang sama
- Semua user share balance di akun Indodax yang sama

**Solusi untuk Multi-User Real Trading:**
1. **Per-User API Keys** (requires code modification):
   - Store API keys per user di database
   - Each user input their own API key
   - Bot execute dengan API key masing-masing user

2. **Simulation Mode per Default** (Recommended):
   - Set `AUTO_TRADE_DRY_RUN=true`
   - Setiap user trading di simulation mode
   - Tidak ada real money involved

## 📝 Best Practices

### 1. Start with Simulation Mode
```bash
AUTO_TRADING_ENABLED=false    # Signals only
AUTO_TRADE_DRY_RUN=true       # Simulation
```

### 2. Limit Admin Access
Hanya berikan admin access ke orang yang dipercaya:
```bash
ADMIN_IDS=123456789           # Only owner
```

Regular users cukup `/start` bot tanpa perlu di-add ke ADMIN_IDS.

### 3. Set Watch Pairs Limit
Terlalu banyak pairs = rate limit dari Indodax:
```bash
WATCH_PAIRS=btcidr,ethidr,bridr,pippinidr,solidr  # Max 10 recommended
```

### 4. Backup Database Regularly
Database berisi semua data user:
```bash
# Auto backup daily
0 2 * * * /opt/crypto-bot/backup.sh
```

### 5. Monitor Bot Logs
Check jika ada user abuse atau anomaly:
```bash
sudo journalctl -u crypto-bot -f | grep ERROR
```

## 🔧 Advanced: Custom Per-User Settings

Jika ingin per-user API keys atau per-user trading settings, perlu modifikasi code.

**Lokasi file:**
- `core/config.py` - Configuration management
- `core/database.py` - Add user_api_keys table
- `autotrade/trading_engine.py` - Use per-user API keys

**Contact developer untuk custom implementation.**

## 📞 Command Reference

### User Commands
```
/start              - Start bot
/help               - Show help
/signal <pair>      - Get signal for pair
/watch <pair>       - Add to personal watchlist
/unwatch <pair>     - Remove from watchlist
/watchlist          - View personal watchlist
/portfolio          - View personal portfolio
/balance            - View personal balance
/stats              - Personal trading stats
/trade              - Manual trading
```

### Admin Commands (ADMIN_IDS only)
```
/status             - System status
/retrain            - Retrain ML model
/logs               - View bot logs
/broadcast <msg>    - Broadcast to all users
/add_admin <id>     - Add new admin
/remove_admin <id>  - Remove admin
```

## 💡 Tips & Tricks

### Tip 1: User Groups
Create Telegram groups untuk team collaboration:
1. Add bot ke grup
2. Set bot sebagai admin
3. Semua member bisa interact dengan bot di grup

### Tip 2: Personal Bot Instance
Setiap user bisa clone bot dan run sendiri:
```bash
# User A's bot
TELEGRAM_BOT_TOKEN=tokenA
ADMIN_IDS=userA_id

# User B's bot
TELEGRAM_BOT_TOKEN=tokenB
ADMIN_IDS=userB_id
```

### Tip 3: Shared Signals, Personal Trading
Setup bot untuk broadcast signals ke channel, tapi personal trading:
1. Bot send signals ke public channel
2. User decision: trade atau tidak
3. User trading dengan bot pribadi masing-masing

## ❓ FAQ

**Q: Berapa banyak user yang bisa pakai 1 bot?**
A: Tidak ada limit. Tapi untuk performa optimal, recommended max 50 concurrent users.

**Q: Apakah setiap user perlu API key sendiri?**
A: Tidak. Tapi jika ingin real trading per-user, recommended API key terpisah (requires custom code).

**Q: Bagaimana user baru bisa akses bot?**
A: Tinggal search username bot di Telegram, lalu `/start`. Tidak perlu approval.

**Q: Bisa limit access hanya untuk user tertentu?**
A: Ya. Implementasikan whitelist di code (contact developer).

**Q: Database aman untuk multi-user?**
A: Ya. SQLite sudah handle concurrent access dengan locking mechanism.

**Q: Bagaimana backup data user?**
A: Database di-backup daily otomatis (via cron). Manual backup: `bash /opt/crypto-bot/backup.sh`

## 🚨 Important Notes

1. **Simulation Mode Default**: Bot default `DRY_RUN=true` untuk safety
2. **Shared API Keys**: Semua user share API key dari `.env`
3. **Data Privacy**: User A tidak bisa lihat data User B
4. **Admin Access**: Hanya ADMIN_IDS yang bisa command priviledged
5. **Rate Limiting**: Indodax limit API calls, jangan terlalu banyak pairs

## 📚 Additional Resources

- Main Documentation: `README.md`
- VPS Deployment: `VPS_DEPLOYMENT_GUIDE.md`
- Quick Start: `quick_start.sh`
- API Documentation: `advanced_crypto_bot/api/`

---

**Setup Complete!** Bot Anda sudah siap untuk multi-user usage 🎉

Jika ada pertanyaan atau butuh custom implementation, contact developer team.
