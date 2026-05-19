# 🚀 Advanced Crypto Bot - VPS Deployment Guide

## 📋 Daftar Isi
1. [Multi-User Setup (Beberapa Nomor Telegram)](#1-multi-user-setup)
2. [Persiapan Bot untuk VPS](#2-persiapan-bot-untuk-vps)
3. [Upload ke VPS](#3-upload-ke-vps)
4. [Instalasi di VPS](#4-instalasi-di-vps)
5. [Running Bot 24/7](#5-running-bot-247)
6. [Monitoring & Maintenance](#6-monitoring--maintenance)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Multi-User Setup (Beberapa Nomor Telegram)

### ✅ Bot SUDAH SUPPORT Multi-User!

Bot ini **sudah mendukung multiple users** secara native. Setiap user dapat:
- Memiliki watchlist sendiri (`/watch`, `/unwatch`)
- Memiliki auto-trade pairs sendiri (`/add_autotrade`, `/remove_autotrade`)
- Menerima signal notifications pribadi
- Menjalankan trading dengan balance terpisah

### 🔐 Konfigurasi Admin & User Access

**File: `.env`**
```bash
# Admin IDs - pisahkan dengan koma
# Admin dapat akses semua fitur + command priviledged
ADMIN_IDS=123456789,987654321,555666777

# Telegram Bot Token (sama untuk semua user)
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### 📝 Cara Mendapatkan Telegram User ID

**Untuk setiap user yang akan menggunakan bot:**

1. Buka Telegram
2. Search: `@userinfobot`
3. Klik **Start**
4. Bot akan reply dengan User ID Anda (angka 9-10 digit)
5. Copy ID tersebut ke `.env` → `ADMIN_IDS`

**Contoh:**
```bash
# 3 user dengan akses admin
ADMIN_IDS=123456789,987654321,111222333
```

### 🎯 Perbedaan Admin vs Regular User

| Fitur | Admin | Regular User |
|-------|-------|--------------|
| View signals | ✅ | ✅ |
| Personal watchlist | ✅ | ✅ |
| Auto-trade personal pairs | ✅ | ✅ |
| View portfolio | ✅ | ✅ Own only |
| Manual trade | ✅ | ✅ |
| ML retrain | ✅ | ❌ |
| System commands | ✅ | ❌ |
| View all users data | ✅ | ❌ |

**Non-admin users**: Boleh menggunakan bot, tapi hanya command dasar (signals, portfolio sendiri, watchlist sendiri)

**Admin users**: Full access termasuk `/retrain`, `/status`, `/logs`, dll

### 🔄 Menambah User Baru (Setelah Bot Running)

**Cara 1: Update `.env` (Recommended)**
```bash
# Edit .env
nano .env

# Tambahkan ID baru
ADMIN_IDS=123456789,987654321,999888777

# Restart bot
sudo systemctl restart crypto-bot
```

**Cara 2: Tanpa Restart (Runtime)**
```python
# Kirim command dari admin existing:
/add_admin 999888777

# Atau edit database langsung (advanced)
sqlite3 data/trading.db
INSERT INTO admins (user_id) VALUES (999888777);
```

---

## 2. Persiapan Bot untuk VPS

### 📦 File yang Perlu Di-Upload

```
advanced_crypto_bot/
├── advanced_crypto_bot/     # Folder utama bot
│   ├── bot.py              # Main bot file
│   ├── core/               # Core modules
│   ├── analysis/           # TA & ML modules
│   ├── autotrade/          # Trading engine
│   ├── signals/            # Signal generation
│   ├── api/                # Indodax API
│   ├── workers/            # Background workers
│   ├── cache/              # Redis cache
│   ├── requirements.txt    # Python dependencies
│   └── .env               # Configuration (DIBUAT DI VPS)
├── data/                   # Database & logs (auto-created)
├── models/                 # ML models (auto-created)
└── logs/                   # Log files (auto-created)
```

### 🔒 File yang TIDAK Boleh Di-Upload (Sensitive)

```bash
# .gitignore (untuk keamanan)
.env                    # API keys & secrets
*.db                    # Database files
*.log                   # Log files
__pycache__/           # Python cache
*.pyc
.DS_Store
manual_sr_levels.json  # Manual S/R (jika ada)
```

### 🛠️ Create `.gitignore`

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
cat > .gitignore << 'EOF'
# Environment
.env
.env.local

# Database
*.db
*.sqlite
*.sqlite3
data/*.db

# Logs
*.log
logs/

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/

# Models
models/*.pkl
models/*.h5
models/*.pt

# Manual configs
manual_sr_levels.json

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo
EOF
```

---

## 3. Upload ke VPS

### 🌐 Method 1: Git (Recommended)

**A. Setup Repository (Local)**
```bash
cd /home/officer/advanced_crypto_bot

# Initialize git (jika belum)
git init

# Add gitignore
git add .gitignore

# Add files
git add .

# Commit
git commit -m "Initial commit - Advanced Crypto Bot"

# Push to GitHub/GitLab (private repo!)
git remote add origin https://github.com/yourusername/crypto-bot.git
git branch -M main
git push -u origin main
```

**B. Clone di VPS**
```bash
# SSH to VPS
ssh root@your-vps-ip

# Clone repository
cd /opt
git clone https://github.com/yourusername/crypto-bot.git
cd crypto-bot/advanced_crypto_bot
```

### 📤 Method 2: SCP/SFTP (Alternative)

**A. Compress locally**
```bash
cd /home/officer
tar -czf crypto-bot.tar.gz advanced_crypto_bot/ \
  --exclude='*.db' \
  --exclude='*.log' \
  --exclude='__pycache__' \
  --exclude='.env'
```

**B. Upload to VPS**
```bash
# SCP
scp crypto-bot.tar.gz root@your-vps-ip:/opt/

# SSH to VPS
ssh root@your-vps-ip

# Extract
cd /opt
tar -xzf crypto-bot.tar.gz
cd advanced_crypto_bot/advanced_crypto_bot
```

### 🔐 Method 3: rsync (Advanced)

```bash
# Sync dari local ke VPS (real-time updates)
rsync -avz --exclude='.env' --exclude='*.db' --exclude='*.log' \
  /home/officer/advanced_crypto_bot/ \
  root@your-vps-ip:/opt/crypto-bot/
```

---

## 4. Instalasi di VPS

### 🐧 VPS Requirements

**Minimum Specs:**
- **OS**: Ubuntu 20.04 / 22.04 LTS (Recommended)
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 20GB SSD
- **CPU**: 2 cores minimum
- **Python**: 3.8+

### 📋 Step-by-Step Installation

**1. Update System**
```bash
sudo apt update && sudo apt upgrade -y
```

**2. Install Python 3 & Dependencies**
```bash
# Python 3.9+ (recommended)
sudo apt install -y python3 python3-pip python3-venv

# System dependencies
sudo apt install -y build-essential libssl-dev libffi-dev \
  python3-dev git wget curl nano htop

# Optional: Redis (for caching)
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

**3. Setup Bot Directory**
```bash
cd /opt/crypto-bot/advanced_crypto_bot

# Create virtual environment
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

**4. Configure Bot**
```bash
# Copy .env.example to .env
cp .env.example .env

# Edit .env
nano .env
```

**Edit `.env` dengan konfigurasi Anda:**
```bash
# WAJIB DIISI:
TELEGRAM_BOT_TOKEN=123456:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_IDS=123456789,987654321

# OPSIONAL (untuk auto-trading):
INDODAX_API_KEY=your_api_key
INDODAX_SECRET_KEY=your_secret_key

# Trading settings
AUTO_TRADING_ENABLED=false    # false = signals only
AUTO_TRADE_DRY_RUN=true       # true = simulation
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=4.0

# Watch pairs
WATCH_PAIRS=btcidr,ethidr,bridr,pippinidr,solidr

# Dashboard URL (ganti dengan IP VPS Anda)
DASHBOARD_URL=http://YOUR_VPS_IP:8080
```

**5. Test Bot**
```bash
# Activate venv
source venv/bin/activate

# Run bot (test mode)
cd /opt/crypto-bot/advanced_crypto_bot
python3 bot.py
```

Jika berhasil, Anda akan melihat:
```
🚀 Starting Advanced Crypto Trading Bot...
✅ Bot initialized successfully!
📱 Starting Telegram bot with POLLING...
```

**Test di Telegram:**
- Buka bot Anda di Telegram
- Send `/start`
- Jika bot reply, berarti sukses! ✅

Press `Ctrl+C` untuk stop bot (kita akan setup auto-start di step berikutnya)

---

## 5. Running Bot 24/7

### ⚙️ Method 1: systemd Service (Recommended)

**A. Create Service File**
```bash
sudo nano /etc/systemd/system/crypto-bot.service
```

**Paste konfigurasi ini:**
```ini
[Unit]
Description=Advanced Crypto Trading Bot
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/crypto-bot/advanced_crypto_bot
Environment="PATH=/opt/crypto-bot/advanced_crypto_bot/venv/bin"
ExecStart=/opt/crypto-bot/advanced_crypto_bot/venv/bin/python3 bot.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/crypto-bot.log
StandardError=append:/var/log/crypto-bot-error.log

# Limit memory (adjust based on your VPS)
MemoryMax=2G
MemoryHigh=1.5G

[Install]
WantedBy=multi-user.target
```

**B. Enable & Start Service**
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable crypto-bot

# Start bot
sudo systemctl start crypto-bot

# Check status
sudo systemctl status crypto-bot
```

**C. Service Commands**
```bash
# Start bot
sudo systemctl start crypto-bot

# Stop bot
sudo systemctl stop crypto-bot

# Restart bot
sudo systemctl restart crypto-bot

# View status
sudo systemctl status crypto-bot

# View logs (real-time)
sudo journalctl -u crypto-bot -f

# View recent logs
sudo journalctl -u crypto-bot -n 100 --no-pager
```

### 🔄 Method 2: Screen (Alternative)

```bash
# Install screen
sudo apt install -y screen

# Create screen session
screen -S crypto-bot

# Run bot
cd /opt/crypto-bot/advanced_crypto_bot
source venv/bin/activate
python3 bot.py

# Detach: Press Ctrl+A, then D

# Re-attach later
screen -r crypto-bot

# List sessions
screen -ls
```

### 🐳 Method 3: Docker (Advanced)

**A. Create Dockerfile**
```bash
cd /opt/crypto-bot/advanced_crypto_bot
nano Dockerfile
```

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY . .

# Run bot
CMD ["python3", "bot.py"]
```

**B. Create docker-compose.yml**
```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: crypto-bot
    restart: always
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./models:/app/models
      - ./.env:/app/.env
    environment:
      - TZ=Asia/Jakarta
    mem_limit: 2g
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  redis:
    image: redis:alpine
    container_name: crypto-redis
    restart: always
    ports:
      - "6379:6379"
```

**C. Run with Docker**
```bash
# Build & start
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop
docker-compose down

# Restart
docker-compose restart
```

---

## 6. Monitoring & Maintenance

### 📊 View Logs

**systemd logs:**
```bash
# Real-time
sudo journalctl -u crypto-bot -f

# Last 100 lines
sudo journalctl -u crypto-bot -n 100

# Today's logs
sudo journalctl -u crypto-bot --since today

# Logs with timestamps
sudo journalctl -u crypto-bot --since "1 hour ago"
```

**Log files:**
```bash
# Bot logs
tail -f /var/log/crypto-bot.log

# Error logs
tail -f /var/log/crypto-bot-error.log

# Application logs
tail -f /opt/crypto-bot/advanced_crypto_bot/logs/bot.log
```

### 🔍 Check Bot Status

**From Telegram:**
```
/status        - System status
/stats         - Trading stats
/portfolio     - Your portfolio
/balance       - Your balance
```

**From VPS:**
```bash
# Service status
sudo systemctl status crypto-bot

# Check if running
ps aux | grep bot.py

# Check memory usage
free -h

# Check disk usage
df -h

# Check CPU usage
htop
```

### 🔄 Update Bot

**Method 1: Git Pull (if using git)**
```bash
cd /opt/crypto-bot/advanced_crypto_bot

# Pull updates
git pull origin main

# Install new dependencies (if any)
source venv/bin/activate
pip install -r requirements.txt

# Restart bot
sudo systemctl restart crypto-bot
```

**Method 2: Manual Upload**
```bash
# Upload new files via SCP/SFTP
# Then restart:
sudo systemctl restart crypto-bot
```

### 🗄️ Database Backup

**Auto-backup script:**
```bash
nano /opt/crypto-bot/backup.sh
```

```bash
#!/bin/bash
# Backup script for crypto bot database

BACKUP_DIR="/opt/crypto-bot/backups"
DB_FILE="/opt/crypto-bot/advanced_crypto_bot/data/trading.db"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
cp $DB_FILE $BACKUP_DIR/trading_${DATE}.db

# Keep only last 7 days
find $BACKUP_DIR -name "trading_*.db" -mtime +7 -delete

echo "✅ Backup completed: trading_${DATE}.db"
```

```bash
# Make executable
chmod +x /opt/crypto-bot/backup.sh

# Add to cron (daily backup at 2 AM)
crontab -e

# Add line:
0 2 * * * /opt/crypto-bot/backup.sh >> /var/log/crypto-backup.log 2>&1
```

### 📈 Resource Monitoring

**Install monitoring tools:**
```bash
# Install htop (process monitor)
sudo apt install -y htop

# Install iotop (disk I/O monitor)
sudo apt install -y iotop

# Install nethogs (network monitor)
sudo apt install -y nethogs
```

**Auto-restart on crash:**
Bot sudah dikonfigurasi untuk auto-restart di systemd service (`Restart=always`)

---

## 7. Troubleshooting

### ❌ Bot Tidak Start

**1. Check logs:**
```bash
sudo journalctl -u crypto-bot -n 50
```

**2. Check .env:**
```bash
cd /opt/crypto-bot/advanced_crypto_bot
cat .env | grep TELEGRAM_BOT_TOKEN
```

**3. Test manual:**
```bash
cd /opt/crypto-bot/advanced_crypto_bot
source venv/bin/activate
python3 bot.py
```

### ❌ Telegram Not Responding

**1. Check bot token:**
```bash
# Test token validity
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

**2. Check firewall:**
```bash
# Allow outbound HTTPS
sudo ufw allow out 443/tcp
```

**3. Check network:**
```bash
ping telegram.org
```

### ❌ Database Locked Error

```bash
# Stop bot
sudo systemctl stop crypto-bot

# Check locks
sudo lsof | grep trading.db

# Kill process if needed
sudo kill -9 <PID>

# Restart bot
sudo systemctl start crypto-bot
```

### ❌ Memory Issues

**1. Check memory:**
```bash
free -h
```

**2. Add swap (if RAM < 4GB):**
```bash
# Create 2GB swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**3. Restart bot:**
```bash
sudo systemctl restart crypto-bot
```

### ❌ API Rate Limit

Bot sudah mengimplementasikan rate limiting otomatis. Jika masih kena limit:

**1. Kurangi watch pairs:**
```bash
nano .env
# Edit WATCH_PAIRS (max 10 pairs recommended)
```

**2. Increase polling interval:**
Bot akan otomatis slow down jika detect rate limit

### 🔧 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Bot restart loop | Check logs: `journalctl -u crypto-bot -n 100` |
| Signal tidak keluar | Pastikan watchlist terisi: `/watchlist` |
| API error 401 | Check API keys di `.env` |
| Database corrupt | Restore dari backup |
| High CPU usage | Normal saat ML training, akan turun setelah selesai |
| Redis connection failed | Bot akan fallback ke in-memory cache |

---

## 📝 Quick Reference Card

### 🎯 Essential Commands

```bash
# SERVICE
sudo systemctl start crypto-bot      # Start bot
sudo systemctl stop crypto-bot       # Stop bot
sudo systemctl restart crypto-bot    # Restart bot
sudo systemctl status crypto-bot     # Status check

# LOGS
sudo journalctl -u crypto-bot -f     # Real-time logs
tail -f /var/log/crypto-bot.log      # Application logs

# UPDATE
cd /opt/crypto-bot/advanced_crypto_bot
git pull                             # Pull updates
sudo systemctl restart crypto-bot    # Restart

# BACKUP
/opt/crypto-bot/backup.sh            # Manual backup

# MONITORING
htop                                 # Process monitor
df -h                                # Disk usage
free -h                              # Memory usage
```

### 📞 Telegram Commands (for users)

```
/start         - Start bot
/help          - Help menu
/signal PAIR   - Get signal
/watch PAIR    - Add to watchlist
/watchlist     - View watchlist
/portfolio     - View portfolio
/balance       - View balance
/stats         - Trading statistics
```

---

## 🎉 Setup Complete!

Bot Anda sekarang sudah:
- ✅ Support multiple users (beberapa nomor Telegram)
- ✅ Running 24/7 di VPS
- ✅ Auto-restart on crash
- ✅ Auto-backup database
- ✅ Monitored & logged

**Next Steps:**
1. Share bot username ke users lain
2. Tambahkan user IDs ke `ADMIN_IDS` di `.env`
3. Test signals dengan `/signal btcidr`
4. Monitor logs: `sudo journalctl -u crypto-bot -f`

**Support:**
- Telegram: @yourusername (ganti dengan support channel Anda)
- Documentation: `/home/officer/advanced_crypto_bot/README.md`

---

**Made with ❤️ by Advanced Crypto Bot Team**
