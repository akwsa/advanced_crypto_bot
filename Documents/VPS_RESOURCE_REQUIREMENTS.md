# VPS Biznet Resource Requirements - Live Trading

## 📊 Executive Summary

**Bot Crypto Trading - Live Trading di Biznet VPS**

| Resource | Minimum | Recommended | Production |
|----------|---------|-------------|------------|
| **CPU Cores** | 2 Core | **4 Core** | 4 Core |
| **RAM** | 1 GB | **2 GB** | 4 GB |
| **Storage** | 10 GB | **20 GB SSD** | 20 GB SSD |
| **Network** | 1 Mbps | **10 Mbps** | 10 Mbps |
| **OS** | Ubuntu 20.04 | **Ubuntu 22.04 LTS** | Ubuntu 22.04 LTS |

**Estimasi Biaya Biznet** (April 2026):
- **Minimum**: ~Rp 150.000/bulan (2 Core, 1GB RAM, 10GB)
- **Recommended**: ~Rp 300.000/bulan (4 Core, 2GB RAM, 20GB SSD)
- **Production**: ~Rp 500.000/bulan (4 Core, 4GB RAM, 40GB SSD)

---

## 🔍 Detailed Resource Analysis

### 1. CPU Requirements

#### Current Usage:
```
Normal Operation (polling + signal generation):
  ├── 8 pairs polling every 15s → ~10% CPU
  ├── Telegram bot (async) → ~5% CPU
  ├── Background tasks → ~5% CPU
  └── Total average: ~20% CPU

ML Training (once per 24 hours, 1-5 minutes):
  ├── RandomForest (n_jobs=-1) → 100% CPU (all cores)
  ├── GradientBoosting → 80-100% CPU
  └── Duration: 1-5 minutes depending on data size
```

#### CPU Breakdown by Component:

| Component | Normal | Peak | Duration |
|-----------|--------|------|----------|
| **Price Polling** | 5-10% | 15% | Continuous |
| **Telegram Bot** | 2-5% | 10% | On command |
| **Signal Generation** | 5-10% | 20% | Per cycle |
| **ML Inference** | 2-5% | 15% | Per prediction |
| **ML Training** | 0% | **100%** | 1-5 min/day |
| **Database Writes** | 2-3% | 5% | Continuous |
| **Logging** | 1-2% | 3% | Continuous |

**Peak Scenario** (ML Training + Polling + User Command):
```
ML Training:     100% (all cores)
Polling:          15%
Signal Gen:       20%
Telegram Bot:     10%
Total:           145% (needs 2+ cores to handle)
```

#### Recommendation:

| Config | Cores | Why |
|--------|-------|-----|
| **Minimum** | 2 Core | Handle ML training + polling concurrently |
| **Recommended** | **4 Core** | Smooth operation, headroom for spikes |
| **Production** | 4 Core | Same as recommended (optimal) |

**⚠️ WARNING**: Dengan 1 core, ML training akan **block semua operasi lain** selama 1-5 menit!

---

### 2. RAM Requirements

#### Current Usage (Runtime):

```
Python Process (bot.py):
  ├── Base Python runtime:           50 MB
  ├── Telegram bot library:          30 MB
  ├── Pandas + NumPy:               150 MB
  ├── Scikit-learn (loaded):         40 MB
  ├── ML Model (in memory):          10 MB
  ├── Database connections:          20 MB
  ├── Price data (8 pairs):          50 MB
  ├── Historical data (200 candles): 100 MB
  ├── Asyncio event loop:            20 MB
  ├── Logging buffers:               10 MB
  └── Overhead/misc:                 50 MB
  └── TOTAL:                        ~530 MB

ML Training (peak):
  ├── Current usage:                530 MB
  ├── Training data (30 days):      200 MB
  ├── Model training temp:          300 MB
  ├── Parallel threads (n_jobs=-1): 200 MB
  └── PEAK TOTAL:                  ~1,230 MB (1.2 GB)
```

#### RAM Breakdown:

| Component | Normal | Peak (ML Training) |
|-----------|--------|-------------------|
| **Python Runtime** | 530 MB | 530 MB |
| **Price Data Cache** | 50 MB | 50 MB |
| **Historical Data** | 100 MB | 100 MB |
| **ML Model (inference)** | 10 MB | 10 MB |
| **ML Training Data** | 0 MB | 200 MB |
| **ML Training Temp** | 0 MB | 300 MB |
| **ML Parallel Threads** | 0 MB | 200 MB |
| **Database Cache** | 20 MB | 20 MB |
| **Buffer (20%)** | 106 MB | 246 MB |
| **TOTAL** | **~816 MB** | **~1,656 MB (1.6 GB)** |

#### Recommendation:

| Config | RAM | Why |
|--------|-----|-----|
| **Minimum** | 1 GB | Risky - may OOM during ML training |
| **Recommended** | **2 GB** | Safe, handles ML training comfortably |
| **Production** | 4 GB | Extra headroom, future-proof |

**⚠️ WARNING**: Dengan 1GB RAM, ML training bisa trigger **Out of Memory (OOM) kill**!

---

### 3. Storage Requirements

#### Current Disk Usage:

| Component | Current Size | Growth Rate | With Cleanup |
|-----------|--------------|-------------|--------------|
| **Python + Packages** | ~500 MB | Static | ~500 MB |
| **trading.db** | 17.1 MB | +10-14 MB/day | ~400 MB (30 days) |
| **signals.db** | 245 KB | +1-2 MB/day | ~50 MB (30 days) |
| **ML Model (.pkl)** | 2.68 MB | Static (overwrite) | ~3 MB |
| **Logs (all)** | ~17 MB | +15-25 MB/day | ~500 MB/month |
| **Session Files** | ~1 MB | Static | ~1 MB |
| **Code + Config** | ~5 MB | Static | ~5 MB |
| **SQLite WAL Files** | ~500 KB | Dynamic | ~1 MB |
| **Buffer (20%)** | ~110 MB | - | ~200 MB |
| **TOTAL** | **~650 MB** | **+25-40 MB/day** | **~1.7 GB** |

#### Storage Growth Projection:

| Time | Without Cleanup | With Cleanup |
|------|-----------------|--------------|
| **Day 1** | 650 MB | 650 MB |
| **Day 7** | 830 MB | 750 MB |
| **Day 30** | 1.8 GB | 1.7 GB |
| **Day 90** | 4.2 GB | 2.0 GB |
| **Day 365** | 15 GB | 2.5 GB |

**Cleanup Active:**
- `cleanup_old_price_data(days=30)` → Price history capped at 30 days
- Log rotation → Logs capped at ~500 MB/month
- `signals.db` → Auto-vacuum on fetch

#### Recommendation:

| Config | Storage | Why |
|--------|---------|-----|
| **Minimum** | 10 GB | Tight but workable with cleanup |
| **Recommended** | **20 GB SSD** | Comfortable, 2+ years headroom |
| **Production** | 40 GB SSD | Extra space for backups, exports |

**💡 SSD vs HDD**: Pilih **SSD** untuk database performance (SQLite I/O intensive)

---

### 4. Network Requirements

#### Bandwidth Usage:

**Inbound (Download):**
```
Price Polling (8 pairs, every 15s):
  ├── API request: ~200 bytes
  ├── API response: ~2 KB
  ├── 4 cycles/min × 60 min × 24 hrs = 5,760 cycles/day
  └── Daily: 5,760 × 2.2 KB = ~12.7 MB/day

Telegram Bot:
  ├── Commands: ~50/day × 5 KB = 250 KB/day
  └── Notifications: ~100/day × 10 KB = 1 MB/day

Total Inbound: ~14 MB/day = ~420 MB/month
```

**Outbound (Upload):**
```
Price Polling:
  └── API requests: 5,760 × 200 bytes = ~1.2 MB/day

Telegram Bot:
  ├── Responses: ~150/day × 3 KB = 450 KB/day
  └── Signal messages: ~50/day × 5 KB = 250 KB/day

Total Outbound: ~1.9 MB/day = ~57 MB/month
```

**Total Network**: ~16 MB/day = **~477 MB/month** (< 1 GB)

#### Recommendation:

| Config | Network | Why |
|--------|---------|-----|
| **Minimum** | 1 Mbps | Sufficient for API + Telegram |
| **Recommended** | **10 Mbps** | Low latency, stable connection |
| **Production** | 10 Mbps | Same (network not bottleneck) |

**⚠️ Penting**: **Stability > Speed** - Connection drop = missed price updates!

---

### 5. OS Requirements

**Recommended**: **Ubuntu 22.04 LTS**

**Why:**
- ✅ Long Term Support (until 2027)
- ✅ Python 3.10+ included
- ✅ All packages available (pandas, sklearn, etc)
- ✅ systemd for auto-start
- ✅ Wide documentation

**Alternative**:
- Debian 11/12 (lighter, but less support)
- CentOS 9 (enterprise, but heavier)

---

## 💰 Biznet VPS Paket Recommendations

### Paket 1: MINIMUM (Rp ~150.000/bulan)
```
Specs:
  ├── CPU: 2 Core
  ├── RAM: 1 GB
  ├── Storage: 10 GB SSD
  └── Network: 10 Mbps

Pros:
  ✅ Cheapest option
  ✅ Can run bot

Cons:
  ❌ Risky during ML training (OOM possible)
  ❌ Storage tight (need aggressive cleanup)
  ❌ No headroom for growth

Verdict: ⚠️ NOT RECOMMENDED (too risky)
```

### Paket 2: RECOMMENDED (Rp ~300.000/bulan) ⭐
```
Specs:
  ├── CPU: 4 Core
  ├── RAM: 2 GB
  ├── Storage: 20 GB SSD
  └── Network: 10 Mbps

Pros:
  ✅ Safe for ML training
  ✅ Comfortable storage headroom
  ✅ Good performance
  ✅ Cost-effective

Cons:
  ⚠️ Limited headroom for major scaling

Verdict: ✅ BEST VALUE (recommended)
```

### Paket 3: PRODUCTION (Rp ~500.000/bulan)
```
Specs:
  ├── CPU: 4 Core
  ├── RAM: 4 GB
  ├── Storage: 40 GB SSD
  └── Network: 10 Mbps

Pros:
  ✅ Plenty of headroom
  ✅ Future-proof
  ✅ Can run multiple bots
  ✅ Extra space for backups

Cons:
  ⚠️ Overkill for single bot

Verdict: 🟡 NICE TO HAVE (if budget allows)
```

---

## 🛠️ Setup Guide untuk VPS Biznet

### Step 1: Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3 python3-pip python3-venv -y

# Install system dependencies
sudo apt install git build-essential -y

# Create project directory
mkdir -p ~/crypto_bot
cd ~/crypto_bot

# Clone or upload your code
# ... (upload bot files)

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip
pip install -r requirements.txt
```

### requirements.txt:
```txt
python-telegram-bot==20.7
pandas==2.1.4
numpy==1.26.2
scikit-learn==1.3.2
scipy==1.11.4
joblib==1.3.2
websocket-client==1.7.0
requests==2.31.0
aiohttp==3.9.1
python-dotenv==1.0.0
telethon==1.33.1
openpyxl==3.1.2
psutil==5.9.6
```

### Step 2: Configure Environment

```bash
# Create .env file
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_token_here
ADMIN_IDS=your_admin_id_here
WATCH_PAIRS=btcidr,ethidr,bridr,solidr,dogeidr,xrpidr,adaidr
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=5.0
INITIAL_BALANCE=10000000
AUTO_TRADING_ENABLED=false
AUTO_TRADE_DRY_RUN=true
DATABASE_PATH=data/trading.db
LOG_LEVEL=INFO
EOF
```

### Step 3: Setup Systemd Service

```bash
# Create service file
sudo cat > /etc/systemd/system/crypto-bot.service << EOF
[Unit]
Description=Crypto Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto_bot
ExecStart=/home/ubuntu/crypto_bot/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/crypto_bot/logs/service.log
StandardError=append:/home/ubuntu/crypto_bot/logs/service-error.log

# Resource limits
MemoryMax=2G
CPUQuota=150%

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable crypto-bot
sudo systemctl start crypto-bot

# Check status
sudo systemctl status crypto-bot

# View logs
sudo journalctl -u crypto-bot -f
```

### Step 4: Setup Log Rotation

```bash
# Create logrotate config
sudo cat > /etc/logrotate.d/crypto-bot << EOF
/home/ubuntu/crypto_bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    postrotate
        systemctl reload crypto-bot > /dev/null 2>&1 || true
    endscript
}
EOF
```

### Step 5: Setup Database Cleanup Cron

```bash
# Edit crontab
crontab -e

# Add these lines:
# Cleanup old price data every Sunday at 3 AM
0 3 * * 0 cd /home/ubuntu/crypto_bot && /home/ubuntu/crypto_bot/venv/bin/python -c "from database import Database; db = Database(); db.cleanup_old_price_data(days=30)"

# Vacuum signals.db every Monday at 4 AM
0 4 * * 1 cd /home/ubuntu/crypto_bot && /home/ubuntu/crypto_bot/venv/bin/python -c "from signal_db import SignalDatabase; db = SignalDatabase(); db.vacuum()"

# Export signals backup 1st of every month
0 5 1 * * cd /home/ubuntu/crypto_bot && /home/ubuntu/crypto_bot/venv/bin/python signal_history_viewer.py --export /home/ubuntu/backups/signals_\$(date +\%Y\%m\%d).xlsx
```

---

## 📊 Resource Monitoring

### Check Current Usage:

```bash
# CPU & RAM
htop

# Disk usage
df -h
du -sh /home/ubuntu/crypto_bot/data/*
du -sh /home/ubuntu/crypto_bot/logs/*

# Network
iftop

# Process details
ps aux | grep python
```

### Setup Monitoring Alert:

```bash
# Create monitoring script
cat > ~/check_bot_health.sh << 'EOF'
#!/bin/bash

# Check if bot is running
if ! systemctl is-active --quiet crypto-bot; then
    echo "⚠️ Bot is NOT running! Restarting..."
    systemctl restart crypto-bot
fi

# Check disk usage
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 85 ]; then
    echo "⚠️ Disk usage high: ${DISK_USAGE}%"
fi

# Check RAM
RAM_USAGE=$(free | awk '/Mem:/ {printf "%d", $3/$2 * 100}')
if [ $RAM_USAGE -gt 90 ]; then
    echo "⚠️ RAM usage high: ${RAM_USAGE}%"
fi

# Check database size
DB_SIZE=$(du -sm /home/ubuntu/crypto_bot/data/trading.db | awk '{print $1}')
if [ $DB_SIZE -gt 500 ]; then
    echo "⚠️ Database size large: ${DB_SIZE}MB"
fi
EOF

chmod +x ~/check_bot_health.sh

# Run every hour
(crontab -l 2>/dev/null; echo "0 * * * * /home/ubuntu/check_bot_health.sh") | crontab -
```

---

## 🎯 Final Recommendation

### For Biznet VPS - Live Trading:

**Paket**: **RECOMMENDED (4 Core, 2GB RAM, 20GB SSD)**

**Estimasi Biaya**: ~Rp 300.000/bulan

**Why This Package:**
- ✅ 4 Core → Handle ML training smoothly
- ✅ 2GB RAM → Safe for peak usage (1.6GB peak)
- ✅ 20GB SSD → 2+ years headroom with cleanup
- ✅ 10 Mbps → More than enough for API calls
- ✅ Cost-effective (best price/performance ratio)

**Budget Breakdown (Monthly):**
```
VPS Biznet:           Rp 300.000
Domain (optional):    Rp   15.000
Backup storage:       Rp   50.000
Total:                Rp 365.000/bulan
```

---

## ✅ Pre-Launch Checklist

- [ ] VPS provisioned (4 Core, 2GB RAM, 20GB SSD)
- [ ] Ubuntu 22.04 LTS installed
- [ ] Python 3.10+ installed
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` configured with correct values
- [ ] Database files uploaded (or fresh start)
- [ ] Systemd service created and enabled
- [ ] Log rotation configured
- [ ] Database cleanup cron setup
- [ ] Monitoring script deployed
- [ ] Test run in DRY_RUN mode first
- [ ] Verify auto-restart on crash
- [ ] Backup strategy in place
- [ ] SSH keys configured (no password auth)
- [ ] Firewall configured (only allow SSH + necessary ports)

---

## 📞 Support Resources

**Biznet Support**:
- Ticket System: https://biznetnetworks.com/support
- Phone: (021) 3000-9888
- Email: support@biznetgiocloud.com

**Monitoring Tools**:
- `htop` - CPU/RAM monitoring
- `df -h` - Disk usage
- `systemctl status crypto-bot` - Bot status
- `journalctl -u crypto-bot -f` - Bot logs

**Troubleshooting**:
- Bot not starting: `journalctl -u crypto-bot -n 100`
- High RAM: `ps aux --sort=-%mem | head -10`
- High CPU: `ps aux --sort=-%cpu | head -10`
- Disk full: `du -sh /home/ubuntu/crypto_bot/* | sort -h`

---

**Created**: 2026-04-10  
**Status**: ✅ **READY FOR DEPLOYMENT**  
**Recommended Package**: **4 Core, 2GB RAM, 20GB SSD (~Rp 300K/month)**
