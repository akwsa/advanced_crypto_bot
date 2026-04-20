# 🚀 Panduan Deployment VPS Biznet GIO

## Spesifikasi VPS
- **vCPU:** 4 Core
- **RAM:** 4 GB
- **Storage:** 60 GB SSD
- **OS:** Ubuntu 22.04/24.04 LTS

---

## ✅ Perbaikan yang Sudah Dilakukan

### 1. **Dependencies (`requirements.txt`)**
- ❌ **TensorFlow DIHAPUS** - Tidak dipakai aktif, menghemat 1-2GB RAM
- ✅ **Redis DITAMBAH** - Diperlukan untuk `redis_price_cache.py` dan task queue

### 2. **WebSocket Disabled (`bot.py`)**
- WebSocket tidak dipakai (Indodax public channels tidak reliable)
- Inisialisasi WebSocket dihapus untuk hemat resource

### 3. **Memory Safeguard (`bot.py`)**
- Batas maksimal **50 pairs** di `historical_data` untuk mencegah memory exhaustion
- Setiap pair dibatasi **200 candles** (~16 menit data)

### 4. **Systemd Service (`crypto-bot.service`)**
- Memory limit: **2GB max** (`MemoryMax=2G`)
- Auto-restart dengan delay 30 detik
- Security hardening (NoNewPrivileges, ProtectSystem, dll)

### 5. **Signal Fixes (TA Calculation + Threshold + Stabilizer)** 🆕

#### Fix #1: TA Strength Calculation Bug (`technical_analysis.py`)
**Masalah lama:** TA strength = -1.0 padahal 4/5 indicators NEUTRAL
```
# OLD BUG:
buy=0, sell=0.5 (just MACD) → strength = (0-0.5)/0.5 = -1.0 ❌

# NEW:
score per indicator: [-1, -0.5, 0, +0.5, +1] → average
4 NEUTRAL (0) + 1 BEARISH (-0.5) → -0.5/5 = -0.1 ✅
```

#### Fix #2: Raised Thresholds (`trading_engine.py`)
```
OLD: STRONG_BUY/SELL at ±0.4 combined strength
NEW: STRONG_BUY/SELL at ±0.6 AND ML confidence > 70%

Result: STRONG signals hanya muncul kalau benar-benar kuat
```

#### Fix #3: Signal Stabilization Filter (`bot.py`)
```
Mencegah loncatan drastis antar cycle:
- HOLD → STRONG_SELL → diturunkan ke SELL
- BUY → STRONG_BUY → diturunkan ke HOLD
- STRONG_BUY ↔ STRONG_SELL → diturunkan ke HOLD

Pattern lama: HOLD → STRONG_BUY → STRONG_SELL (dalam 16 menit) ❌
Pattern baru: HOLD → BUY → SELL → SELL (gradual) ✅
```

---

## 📋 Langkah Deployment

### Step 1: Persiapan VPS

```bash
# SSH ke VPS
ssh root@<vps-ip-address>

# Update system
apt update && apt upgrade -y

# Install Git (opsional)
apt install -y git
```

### Step 2: Upload Bot Files

**Option A: Via SCP dari Windows**
```powershell
# Dari folder c:\advanced_crypto_bot di Windows
scp -r * root@<vps-ip>:/opt/crypto_bot/
```

**Option B: Via Git**
```bash
# Di VPS
cd /opt
git clone <your-repo-url> crypto_bot
cd crypto_bot
```

**Option C: Manual Upload**
- Zip folder `c:\advanced_crypto_bot`
- Upload via SFTP (WinSCP, FileZilla) ke `/opt/crypto_bot/`

### Step 3: Jalankan Deployment Script

```bash
cd /opt/crypto_bot
chmod +x deploy_vps.sh

# Edit script untuk sesuaikan path
nano deploy_vps.sh
# Cari baris: sudo cp -r /path/to/your/bot/* /opt/crypto_bot/
# Ganti dengan: sudo cp -r ./* /opt/crypto_bot/

# Jalankan
sudo ./deploy_vps.sh
```

### Step 4: Konfigurasi Environment

```bash
# Copy template
sudo -u cryptobot cp /opt/crypto_bot/.env.example /opt/crypto_bot/.env

# Edit dengan nilai Anda
sudo nano /opt/crypto_bot/.env
```

**Isi yang WAJIB diisi:**
```env
TELEGRAM_BOT_TOKEN=8686845264:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_IDS=256024600

# Untuk DRY RUN (testing) - API keys boleh kosong
AUTO_TRADE_DRY_RUN=true

# Untuk REAL TRADING - isi API keys dari Indodax
INDODAX_API_KEY=your_key_here
INDODAX_SECRET_KEY=your_secret_here
AUTO_TRADE_DRY_RUN=false
```

### Step 5: Verifikasi Deployment

```bash
# Cek status bot
sudo systemctl status crypto-bot

# Cek logs
sudo journalctl -u crypto-bot -f --lines=50

# Cek Redis
redis-cli ping  # Harus reply: PONG

# Cek resource usage
htop
```

---

## 🔧 Command Reference

### Bot Management
```bash
sudo systemctl start crypto-bot      # Start bot
sudo systemctl stop crypto-bot       # Stop bot
sudo systemctl restart crypto-bot    # Restart bot
sudo systemctl status crypto-bot     # Check status
```

### Monitoring
```bash
# View live logs
sudo journalctl -u crypto-bot -f

# View recent errors
sudo journalctl -u crypto-bot -p err --no-pager

# Check memory usage
ps -o pid,rss,vsz,cmd -p $(pgrep -f 'python.*bot.py') | head -20
# RSS = Resident Set Size (KB), bagi 1024 untuk MB

# Check Redis cache
redis-cli INFO memory | grep used_memory_human
redis-cli DBSIZE

# Check disk usage
du -sh /opt/crypto_bot/data/
du -sh /opt/crypto_bot/logs/
```

### Database Maintenance
```bash
# Backup database
cp /opt/crypto_bot/data/trading.db /opt/crypto_bot/backups/trading_$(date +%Y%m%d).db

# Cleanup old data (manual)
sqlite3 /opt/crypto_bot/data/trading.db "DELETE FROM price_data WHERE timestamp < datetime('now', '-30 days');"
```

---

## ⚠️ PENTING: Security Actions

### 1. ROTATE API KEYS (SEGERA!)
API keys Indodax Anda **terekspor di chat session sebelumnya**. Segera:

1. Login ke Indodax → Settings → API Key
2. **Delete** API key yang lama
3. **Create New API Key**
4. Update di `.env`:
   ```env
   INDODAX_API_KEY=new_key_here
   INDODAX_SECRET_KEY=new_secret_here
   ```

### 2. Protect .env File
```bash
# Set restrictive permissions
sudo chmod 600 /opt/crypto_bot/.env
sudo chown cryptobot:cryptobot /opt/crypto_bot/.env
```

### 3. Jangan Commit .env ke Git
File `.gitignore` sudah ada, tapi verifikasi:
```bash
cat /opt/crypto_bot/.gitignore | grep .env
# Harus ada: .env
```

---

## 📊 Resource Monitoring (4GB VPS)

### Expected Memory Usage
| Component | Usage |
|-----------|-------|
| OS + System | ~400MB |
| Redis | ~100MB |
| Python Bot | ~400-600MB |
| **Total** | **~1-1.1GB** |
| **Free** | **~2.9GB** ✅ |

### Alert Thresholds
```bash
# Check if bot exceeds 2GB
ps -o rss= -p $(pgrep -f 'python.*bot.py') | awk '{if ($1/1024 > 2048) print "⚠️ WARNING: Bot using " $1/1024 "MB"}'

# Auto-restart if memory > 2.5GB (add to crontab)
crontab -e
# Add: */5 * * * * /usr/bin/python3 /opt/crypto_bot/monitor_memory.py
```

### Log Rotation
Sudah dikonfigurasi di `/etc/logrotate.d/crypto-bot`:
- Daily rotation
- Keep 7 days
- Compress old logs

---

## 🐛 Troubleshooting

### Bot tidak start
```bash
# Check logs
sudo journalctl -u crypto-bot --no-pager -n 100

# Common issues:
# 1. Missing .env file
ls -la /opt/crypto_bot/.env

# 2. Python dependency error
sudo -u cryptobot /opt/crypto_bot/venv/bin/pip install -r requirements.txt

# 3. Redis not running
sudo systemctl status redis-server
sudo systemctl start redis-server
```

### Rate Limit 429 dari Indodax
- Bot sudah punya cooldown mechanism
- Jika masih terjadi, kurangi `WATCH_PAIRS` di `.env`
- Atau naikkan `poll_interval` di `price_poller.py`

### Memory Tinggi
```bash
# Check for memory leaks
sudo -u cryptobot /opt/crypto_bot/venv/bin/python3 -c "
import tracemalloc, sys
tracemalloc.start()
# ... run bot briefly ...
current, peak = tracemalloc.get_traced_memory()
print(f'Peak memory: {peak / 1024 / 1024:.2f} MB')
"

# Restart bot to clear memory
sudo systemctl restart crypto-bot
```

### Database Membengkak
```bash
# Check size
du -sh /opt/crypto_bot/data/trading.db

# Cleanup manually
sqlite3 /opt/crypto_bot/data/trading.db << EOF
DELETE FROM price_data WHERE timestamp < datetime('now', '-30 days');
VACUUM;
EOF
```

---

## 🎯 DRY RUN Mode (Recommended untuk Testing)

Bot Anda **sudah dikonfigurasi untuk DRY RUN** di `.env`:
```env
AUTO_TRADE_DRY_RUN=true
```

**Artinya:**
- ✅ Semua sinyal dan analisa tetap jalan
- ✅ Portfolio tracking tetap aktif
- ✅ SL/TP tetap dicek
- ❌ **TIDAK ada trade sungguhan di Indodax**
- ❌ **TIDAK ada uang sungguhan yang digunakan**

**Untuk enable REAL trading:**
1. Pastikan API keys Indodax sudah diisi
2. Ubah di `.env`:
   ```env
   AUTO_TRADE_DRY_RUN=false
   ```
3. Restart bot:
   ```bash
   sudo systemctl restart crypto-bot
   ```
4. Atau via Telegram:
   ```
   /autotrade real
   ```

---

## 📞 Support

Jika ada masalah:
1. Check logs: `sudo journalctl -u crypto-bot -f`
2. Check status: `sudo systemctl status crypto-bot`
3. Check resources: `htop`
4. Check Redis: `redis-cli INFO`

---

**Last updated:** 2026-04-11
