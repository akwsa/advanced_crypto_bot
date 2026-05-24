# 🖥️ VPS RECOMMENDATIONS FOR CRYPTO TRADING BOT

**Last Updated:** 2026-05-17  
**Purpose:** Deploy Advanced Crypto Trading Bot to VPS

---

## 📊 BOT REQUIREMENTS (From Analysis)

Berdasarkan analisis bot, berikut adalah kebutuhan minimum dan recommended:

### Minimum Requirements
- **CPU:** 1 core
- **RAM:** 2 GB
- **Storage:** 1 GB (minimal), 5 GB (recommended)
- **Bandwidth:** 1 TB/month
- **OS:** Ubuntu 20.04+ / Debian 10+

### Recommended Requirements
- **CPU:** 2+ cores
- **RAM:** 4 GB
- **Storage:** 10-20 GB SSD
- **Bandwidth:** Unlimited atau 2+ TB/month
- **OS:** Ubuntu 22.04 LTS

### Performance Notes
- **Memory Usage:** 200-500 MB normal, spike to 1-2 GB during ML retrain
- **CPU Usage:** 10-20% normal, spike to 50-80% during signal generation
- **Database Size:** ~100 MB (akan grow over time)
- **Network:** Moderate (REST API polling, Telegram bot)

---

## 🏆 TOP VPS RECOMMENDATIONS (2026)

### 🥇 TIER 1: BEST VALUE (Indonesia)

#### 1. **Contabo VPS** ⭐⭐⭐⭐⭐
**Location:** Germany, Singapore, USA

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| VPS S | 4 vCores | 8 GB | 200 GB SSD | Unlimited | €4.99 (~Rp 85,000) |
| VPS M | 6 vCores | 16 GB | 400 GB SSD | Unlimited | €8.99 (~Rp 153,000) |
| VPS L | 8 vCores | 30 GB | 800 GB SSD | Unlimited | €14.99 (~Rp 255,000) |

**Pros:**
- ✅ Harga SANGAT murah untuk specs tinggi
- ✅ Unlimited bandwidth
- ✅ SSD storage besar
- ✅ Singapore datacenter (low latency ke Indonesia)
- ✅ 24/7 support

**Cons:**
- ⚠️ Setup fee €4.99 (one-time)
- ⚠️ Shared resources (overselling)
- ⚠️ Support response bisa lambat

**Recommendation:** ✅ **VPS S (4 vCores, 8 GB RAM)** - BEST VALUE!

**Website:** https://contabo.com

---

#### 2. **Hetzner Cloud** ⭐⭐⭐⭐⭐
**Location:** Germany, Finland, USA

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| CX21 | 2 vCPU | 4 GB | 40 GB SSD | 20 TB | €4.90 (~Rp 83,000) |
| CX31 | 2 vCPU | 8 GB | 80 GB SSD | 20 TB | €8.90 (~Rp 151,000) |
| CX41 | 4 vCPU | 16 GB | 160 GB SSD | 20 TB | €15.90 (~Rp 270,000) |

**Pros:**
- ✅ Excellent performance (dedicated resources)
- ✅ Fast network (20 TB bandwidth)
- ✅ Hourly billing (pay as you go)
- ✅ Great uptime (99.9%+)
- ✅ Easy to scale

**Cons:**
- ⚠️ No Asia datacenter (latency ~150-200ms ke Indonesia)
- ⚠️ Sedikit lebih mahal dari Contabo

**Recommendation:** ✅ **CX21 (2 vCPU, 4 GB RAM)** - BEST PERFORMANCE!

**Website:** https://www.hetzner.com/cloud

---

#### 3. **Vultr** ⭐⭐⭐⭐
**Location:** Singapore, Tokyo, Sydney, USA, Europe

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| Regular Performance | 1 vCPU | 1 GB | 25 GB SSD | 1 TB | $6 (~Rp 96,000) |
| Regular Performance | 1 vCPU | 2 GB | 55 GB SSD | 2 TB | $12 (~Rp 192,000) |
| Regular Performance | 2 vCPU | 4 GB | 80 GB SSD | 3 TB | $24 (~Rp 384,000) |

**Pros:**
- ✅ Singapore & Tokyo datacenter (low latency)
- ✅ Hourly billing
- ✅ Easy to use
- ✅ Good network performance
- ✅ Instant deployment

**Cons:**
- ⚠️ Lebih mahal dari Contabo/Hetzner
- ⚠️ Storage lebih kecil

**Recommendation:** ✅ **2 vCPU, 4 GB RAM** - BEST LATENCY!

**Website:** https://www.vultr.com

---

### 🥈 TIER 2: INDONESIA LOCAL (Low Latency)

#### 4. **Dewaweb** ⭐⭐⭐⭐
**Location:** Jakarta, Indonesia

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| VPS Lite | 1 Core | 1 GB | 25 GB SSD | Unlimited | Rp 50,000 |
| VPS Standard | 2 Core | 2 GB | 50 GB SSD | Unlimited | Rp 100,000 |
| VPS Pro | 2 Core | 4 GB | 80 GB SSD | Unlimited | Rp 200,000 |

**Pros:**
- ✅ Indonesia datacenter (latency <10ms)
- ✅ Support Bahasa Indonesia
- ✅ Unlimited bandwidth
- ✅ Good uptime

**Cons:**
- ⚠️ Lebih mahal dari provider internasional
- ⚠️ Specs lebih rendah untuk harga sama

**Recommendation:** ✅ **VPS Pro (2 Core, 4 GB RAM)** - BEST LOCAL!

**Website:** https://www.dewaweb.com

---

#### 5. **Niagahoster** ⭐⭐⭐⭐
**Location:** Jakarta, Indonesia

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| VPS Bayi | 1 Core | 1 GB | 25 GB SSD | Unlimited | Rp 69,000 |
| VPS Pelajar | 2 Core | 2 GB | 50 GB SSD | Unlimited | Rp 139,000 |
| VPS Personal | 2 Core | 4 GB | 75 GB SSD | Unlimited | Rp 279,000 |

**Pros:**
- ✅ Indonesia datacenter
- ✅ Support 24/7 Bahasa Indonesia
- ✅ Unlimited bandwidth
- ✅ Easy to use (cPanel available)

**Cons:**
- ⚠️ Lebih mahal
- ⚠️ Specs lebih rendah

**Recommendation:** ✅ **VPS Personal (2 Core, 4 GB RAM)**

**Website:** https://www.niagahoster.co.id

---

#### 6. **IDCloudHost** ⭐⭐⭐⭐
**Location:** Jakarta, Indonesia

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| VPS Lite | 1 Core | 1 GB | 20 GB SSD | Unlimited | Rp 60,000 |
| VPS Standard | 2 Core | 2 GB | 40 GB SSD | Unlimited | Rp 120,000 |
| VPS Pro | 2 Core | 4 GB | 60 GB SSD | Unlimited | Rp 240,000 |

**Pros:**
- ✅ Indonesia datacenter
- ✅ Support Bahasa Indonesia
- ✅ Unlimited bandwidth

**Cons:**
- ⚠️ Storage lebih kecil
- ⚠️ Harga lebih tinggi

**Recommendation:** ✅ **VPS Pro (2 Core, 4 GB RAM)**

**Website:** https://idcloudhost.com

---

### 🥉 TIER 3: BUDGET OPTIONS

#### 7. **DigitalOcean** ⭐⭐⭐⭐
**Location:** Singapore, USA, Europe

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| Basic | 1 vCPU | 1 GB | 25 GB SSD | 1 TB | $6 (~Rp 96,000) |
| Basic | 1 vCPU | 2 GB | 50 GB SSD | 2 TB | $12 (~Rp 192,000) |
| Basic | 2 vCPU | 4 GB | 80 GB SSD | 4 TB | $24 (~Rp 384,000) |

**Pros:**
- ✅ Singapore datacenter
- ✅ Excellent documentation
- ✅ Easy to use
- ✅ Good community

**Cons:**
- ⚠️ Lebih mahal
- ⚠️ Specs standar

**Website:** https://www.digitalocean.com

---

#### 8. **Linode (Akamai)** ⭐⭐⭐⭐
**Location:** Singapore, Tokyo, USA, Europe

| Plan | CPU | RAM | Storage | Bandwidth | Price/Month |
|------|-----|-----|---------|-----------|-------------|
| Nanode | 1 vCPU | 1 GB | 25 GB SSD | 1 TB | $5 (~Rp 80,000) |
| Linode 2GB | 1 vCPU | 2 GB | 50 GB SSD | 2 TB | $12 (~Rp 192,000) |
| Linode 4GB | 2 vCPU | 4 GB | 80 GB SSD | 4 TB | $24 (~Rp 384,000) |

**Pros:**
- ✅ Singapore & Tokyo datacenter
- ✅ Good performance
- ✅ Reliable

**Cons:**
- ⚠️ Harga standar

**Website:** https://www.linode.com

---

## 🏆 BEST RECOMMENDATIONS BY CRITERIA

### 💰 Best Value (Price/Performance)
**Winner:** 🥇 **Contabo VPS S**
- **Specs:** 4 vCores, 8 GB RAM, 200 GB SSD
- **Price:** €4.99/month (~Rp 85,000)
- **Why:** Specs tertinggi untuk harga termurah

---

### ⚡ Best Performance
**Winner:** 🥇 **Hetzner CX21**
- **Specs:** 2 vCPU, 4 GB RAM, 40 GB SSD
- **Price:** €4.90/month (~Rp 83,000)
- **Why:** Dedicated resources, excellent uptime

---

### 🌏 Best Latency (Indonesia)
**Winner:** 🥇 **Vultr Singapore**
- **Specs:** 2 vCPU, 4 GB RAM, 80 GB SSD
- **Price:** $24/month (~Rp 384,000)
- **Why:** Singapore datacenter, low latency (<50ms)

---

### 🇮🇩 Best Local (Indonesia)
**Winner:** 🥇 **Dewaweb VPS Pro**
- **Specs:** 2 Core, 4 GB RAM, 80 GB SSD
- **Price:** Rp 200,000/month
- **Why:** Jakarta datacenter, support Bahasa Indonesia

---

### 🏅 Best Overall (Balanced)
**Winner:** 🥇 **Contabo VPS S** or **Hetzner CX21**
- **Contabo:** Best value, high specs
- **Hetzner:** Best performance, reliable

---

## 📊 COMPARISON TABLE

| Provider | Location | CPU | RAM | Storage | Bandwidth | Price/Month | Score |
|----------|----------|-----|-----|---------|-----------|-------------|-------|
| **Contabo VPS S** | Singapore | 4 vCores | 8 GB | 200 GB | Unlimited | Rp 85,000 | ⭐⭐⭐⭐⭐ |
| **Hetzner CX21** | Germany | 2 vCPU | 4 GB | 40 GB | 20 TB | Rp 83,000 | ⭐⭐⭐⭐⭐ |
| **Vultr** | Singapore | 2 vCPU | 4 GB | 80 GB | 3 TB | Rp 384,000 | ⭐⭐⭐⭐ |
| **Dewaweb Pro** | Jakarta | 2 Core | 4 GB | 80 GB | Unlimited | Rp 200,000 | ⭐⭐⭐⭐ |
| **Niagahoster** | Jakarta | 2 Core | 4 GB | 75 GB | Unlimited | Rp 279,000 | ⭐⭐⭐⭐ |
| **DigitalOcean** | Singapore | 2 vCPU | 4 GB | 80 GB | 4 TB | Rp 384,000 | ⭐⭐⭐⭐ |

---

## 🎯 MY TOP 3 RECOMMENDATIONS

### 🥇 #1: Contabo VPS S (BEST VALUE)
**Price:** €4.99/month (~Rp 85,000)
**Specs:** 4 vCores, 8 GB RAM, 200 GB SSD, Unlimited bandwidth

**Why Choose:**
- ✅ Specs tertinggi untuk harga termurah
- ✅ Singapore datacenter available
- ✅ Unlimited bandwidth
- ✅ Cukup untuk bot + future scaling

**Best For:** Budget-conscious users yang mau specs tinggi

**Setup Fee:** €4.99 (one-time)

---

### 🥈 #2: Hetzner CX21 (BEST PERFORMANCE)
**Price:** €4.90/month (~Rp 83,000)
**Specs:** 2 vCPU, 4 GB RAM, 40 GB SSD, 20 TB bandwidth

**Why Choose:**
- ✅ Dedicated resources (no overselling)
- ✅ Excellent uptime & reliability
- ✅ Hourly billing (flexible)
- ✅ Great performance

**Best For:** Users yang prioritas stability & performance

**Setup Fee:** None

---

### 🥉 #3: Dewaweb VPS Pro (BEST LOCAL)
**Price:** Rp 200,000/month
**Specs:** 2 Core, 4 GB RAM, 80 GB SSD, Unlimited bandwidth

**Why Choose:**
- ✅ Jakarta datacenter (latency <10ms)
- ✅ Support Bahasa Indonesia 24/7
- ✅ Unlimited bandwidth
- ✅ Easy payment (transfer bank lokal)

**Best For:** Users yang butuh low latency & local support

**Setup Fee:** None

---

## 💡 RECOMMENDATION BY USE CASE

### 🧪 Testing & Learning (DRY RUN Mode)
**Recommended:** Hetzner CX21 atau Contabo VPS S
**Why:** Murah, specs cukup, bisa cancel kapan saja

---

### 💰 Real Trading (Small Capital: 10-50M IDR)
**Recommended:** Hetzner CX21
**Why:** Reliable, dedicated resources, good uptime

---

### 💰 Real Trading (Medium Capital: 50-100M IDR)
**Recommended:** Contabo VPS S atau Vultr Singapore
**Why:** High specs, low latency, scalable

---

### 💰 Real Trading (Large Capital: 100M+ IDR)
**Recommended:** Vultr Singapore atau Dewaweb VPS Pro
**Why:** Low latency critical, local support, high reliability

---

## 🛠️ SETUP GUIDE

### Step 1: Choose VPS Provider
Based on your budget and requirements

### Step 2: Order VPS
- Choose Ubuntu 22.04 LTS
- Select datacenter closest to Indonesia (Singapore preferred)
- Add SSH key for security

### Step 3: Initial Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3 python3-pip python3-venv -y

# Install Redis
sudo apt install redis-server -y

# Install Git
sudo apt install git -y

# Install screen or tmux (untuk keep bot running)
sudo apt install screen -y
```

### Step 4: Deploy Bot
```bash
# Clone bot repository
git clone <your-repo-url>
cd advanced_crypto_bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure .env
cp .env.example .env
nano .env  # Edit with your API keys

# Run bot in screen
screen -S trading_bot
python3 bot.py

# Detach: Ctrl+A, then D
# Reattach: screen -r trading_bot
```

### Step 5: Setup Auto-start (Optional)
```bash
# Create systemd service
sudo nano /etc/systemd/system/trading-bot.service
```

Add:
```ini
[Unit]
Description=Advanced Crypto Trading Bot
After=network.target redis.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/advanced_crypto_bot
ExecStart=/home/your-username/advanced_crypto_bot/venv/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

---

## 🔒 SECURITY RECOMMENDATIONS

### 1. Firewall Setup
```bash
# Install UFW
sudo apt install ufw -y

# Allow SSH
sudo ufw allow 22/tcp

# Allow Redis (localhost only)
sudo ufw allow from 127.0.0.1 to any port 6379

# Enable firewall
sudo ufw enable
```

### 2. SSH Security
```bash
# Disable password authentication
sudo nano /etc/ssh/sshd_config

# Set:
# PasswordAuthentication no
# PermitRootLogin no

# Restart SSH
sudo systemctl restart sshd
```

### 3. Fail2Ban
```bash
# Install fail2ban
sudo apt install fail2ban -y

# Enable
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 📊 COST COMPARISON (1 Year)

| Provider | Monthly | Setup Fee | Annual Total | Specs |
|----------|---------|-----------|--------------|-------|
| **Contabo VPS S** | Rp 85,000 | Rp 85,000 | **Rp 1,105,000** | 4 vCores, 8 GB, 200 GB |
| **Hetzner CX21** | Rp 83,000 | Rp 0 | **Rp 996,000** | 2 vCPU, 4 GB, 40 GB |
| **Vultr** | Rp 384,000 | Rp 0 | **Rp 4,608,000** | 2 vCPU, 4 GB, 80 GB |
| **Dewaweb Pro** | Rp 200,000 | Rp 0 | **Rp 2,400,000** | 2 Core, 4 GB, 80 GB |

**Winner:** 🥇 **Hetzner CX21** - Rp 996,000/year (~Rp 83,000/month)

---

## ✅ FINAL RECOMMENDATION

### For Most Users:
**🥇 Hetzner CX21** (€4.90/month ~ Rp 83,000)
- Best balance of price, performance, and reliability
- Dedicated resources
- No setup fee
- Hourly billing (flexible)

### For Budget Users:
**🥇 Contabo VPS S** (€4.99/month ~ Rp 85,000)
- Highest specs for lowest price
- Singapore datacenter
- Unlimited bandwidth
- One-time setup fee €4.99

### For Indonesia Users:
**🥇 Dewaweb VPS Pro** (Rp 200,000/month)
- Jakarta datacenter (low latency)
- Support Bahasa Indonesia
- Easy payment (bank transfer)
- Unlimited bandwidth

---

## 📞 NEXT STEPS

1. ✅ Choose VPS provider based on your needs
2. ✅ Order VPS with Ubuntu 22.04 LTS
3. ✅ Follow setup guide above
4. ✅ Deploy bot in DRY RUN mode first
5. ✅ Test for 2-4 weeks
6. ✅ Enable real trading (after fixes)

---

## ⚠️ IMPORTANT NOTES

- ⚠️ **Always start with DRY RUN mode** on VPS
- ⚠️ **Setup proper security** (firewall, SSH keys, fail2ban)
- ⚠️ **Monitor resource usage** (CPU, RAM, disk)
- ⚠️ **Setup auto-restart** (systemd service)
- ⚠️ **Backup database regularly** (trading.db, signals.db)
- ⚠️ **Keep .env file secure** (never commit to git)

---

**Last Updated:** 2026-05-17  
**Prepared by:** Professional Trader AI  
**Status:** ✅ READY TO USE

---

*Good luck with your VPS deployment! 🚀*
