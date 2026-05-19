# 🚀 Quick Reference - Bot Deployment

## 📁 File Structure

```
advanced_crypto_bot/
├── 📄 README.md                      → Main documentation
├── 📄 VPS_DEPLOYMENT_GUIDE.md        → Complete VPS setup guide  
├── 📄 MULTI_USER_GUIDE.md            → Multi-user configuration
├── 📄 PRE_UPLOAD_CHECKLIST.md        → Pre-upload validation
├── 📄 quick_start.sh                 → Local testing script
├── 📄 setup_vps.sh                   → VPS auto-setup script
├── 📄 package_for_vps.sh             → Create deployment package
│
└── advanced_crypto_bot/              → Main bot application
    ├── bot.py                        → Main bot file
    ├── .env.example                  → Config template
    ├── requirements.txt              → Python dependencies
    ├── core/                         → Core modules
    ├── analysis/                     → TA & ML
    ├── autotrade/                    → Trading engine
    ├── signals/                      → Signal generation
    └── api/                          → Indodax API
```

## ⚡ Quick Commands

### 🏠 Local Testing
```bash
# Quick start (auto-setup + run)
bash quick_start.sh

# Manual start
cd advanced_crypto_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env  # Configure TELEGRAM_BOT_TOKEN & ADMIN_IDS
python3 bot.py
```

### 📦 Package for VPS
```bash
# Create deployment package
bash package_for_vps.sh

# Output: dist/crypto-bot-YYYYMMDD_HHMMSS.tar.gz
```

### 🚀 VPS Deployment
```bash
# 1. Upload to VPS
scp dist/crypto-bot-*.tar.gz root@YOUR_VPS_IP:/opt/

# 2. SSH to VPS
ssh root@YOUR_VPS_IP

# 3. Extract
cd /opt
tar -xzf crypto-bot-*.tar.gz
cd crypto-bot

# 4. Auto-setup (installs everything)
bash setup_vps.sh

# 5. Configure bot
nano advanced_crypto_bot/.env

# 6. Start bot
systemctl enable crypto-bot
systemctl start crypto-bot
systemctl status crypto-bot
```

### 🔧 VPS Management
```bash
# Start/Stop/Restart
systemctl start crypto-bot
systemctl stop crypto-bot
systemctl restart crypto-bot

# View logs (real-time)
journalctl -u crypto-bot -f

# View status
systemctl status crypto-bot

# Manual backup
bash /opt/crypto-bot/backup.sh
```

## 👥 Multi-User Setup

### Add Users to Bot

**Edit .env:**
```bash
# Multiple user IDs separated by commas
ADMIN_IDS=123456789,987654321,111222333
```

### Get User ID
1. Open Telegram
2. Search: `@userinfobot`
3. Click **Start**
4. Copy your User ID

### User Features
- ✅ Personal watchlist (`/watch`, `/unwatch`)
- ✅ Personal portfolio (`/portfolio`)
- ✅ Personal auto-trade pairs (`/add_autotrade`)
- ✅ Personal balance tracking
- ✅ Private notifications

## 🔐 Security

### ⚠️ NEVER commit to Git:
- ❌ `.env` (contains secrets)
- ❌ `*.db` (database files)
- ❌ `*.log` (log files)
- ❌ API keys or tokens in code

### ✅ Safe Defaults:
- `AUTO_TRADING_ENABLED=false` (signals only)
- `AUTO_TRADE_DRY_RUN=true` (simulation mode)
- Package script auto-excludes sensitive files

## 📊 Configuration

### Required Settings (.env)
```bash
TELEGRAM_BOT_TOKEN=123456:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_IDS=123456789,987654321
```

### Optional Settings
```bash
# Trading
WATCH_PAIRS=btcidr,ethidr,bridr,pippinidr
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=4.0

# API Keys (for real trading)
INDODAX_API_KEY=your_key
INDODAX_SECRET_KEY=your_secret

# Dashboard
DASHBOARD_URL=http://YOUR_VPS_IP:8080
```

## 📱 User Commands

### Basic
```
/start              Start bot
/help               Help menu
/signal <pair>      Get signal for pair
/watch <pair>       Add to watchlist
/watchlist          View your watchlist
/portfolio          View your portfolio
/balance            View your balance
```

### Trading
```
/trade buy <pair> <amount>     Buy manually
/trade sell <pair> <amount>    Sell manually
/add_autotrade <pair>          Enable auto-trade
/remove_autotrade <pair>       Disable auto-trade
```

### Admin Only
```
/status             System status
/retrain            Retrain ML model
/logs               View logs
/broadcast <msg>    Broadcast to all users
```

## 🐛 Troubleshooting

### Bot Won't Start
```bash
# Check logs
journalctl -u crypto-bot -n 50

# Test manually
cd /opt/crypto-bot/advanced_crypto_bot
source venv/bin/activate
python3 bot.py
```

### Telegram Not Responding
```bash
# Validate token
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Check network
ping telegram.org
```

### Database Locked
```bash
# Stop bot
systemctl stop crypto-bot

# Check locks
lsof | grep trading.db

# Restart
systemctl start crypto-bot
```

### Memory Issues
```bash
# Check memory
free -h

# Add swap (if needed)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Main documentation & feature list |
| `VPS_DEPLOYMENT_GUIDE.md` | Complete VPS setup (A-Z) |
| `MULTI_USER_GUIDE.md` | Multi-user setup & management |
| `PRE_UPLOAD_CHECKLIST.md` | Validation before upload |

## 🎯 Deployment Workflow

```
1. Local Development
   ↓
2. Test Locally (quick_start.sh)
   ↓
3. Validate (PRE_UPLOAD_CHECKLIST.md)
   ↓
4. Package (package_for_vps.sh)
   ↓
5. Upload to VPS (scp)
   ↓
6. Auto-Setup (setup_vps.sh)
   ↓
7. Configure (.env)
   ↓
8. Start Bot (systemctl)
   ↓
9. Monitor (journalctl)
```

## ⚙️ VPS Requirements

**Minimum:**
- OS: Ubuntu 20.04+ LTS
- RAM: 2GB
- CPU: 2 cores
- Storage: 20GB SSD
- Python: 3.8+

**Recommended:**
- RAM: 4GB
- CPU: 4 cores
- Storage: 40GB SSD

## 🔄 Update Bot

### Git Pull (if using git)
```bash
cd /opt/crypto-bot/advanced_crypto_bot
git pull origin main
pip install -r requirements.txt
systemctl restart crypto-bot
```

### Manual Upload
```bash
# Package locally
bash package_for_vps.sh

# Upload to VPS
scp dist/crypto-bot-*.tar.gz root@YOUR_VPS_IP:/tmp/

# SSH to VPS
ssh root@YOUR_VPS_IP

# Stop bot
systemctl stop crypto-bot

# Backup current
cp -r /opt/crypto-bot /opt/crypto-bot-backup-$(date +%Y%m%d)

# Extract update
cd /tmp
tar -xzf crypto-bot-*.tar.gz
cp -r crypto-bot/* /opt/crypto-bot/

# Restart
systemctl start crypto-bot
```

## 📞 Support

**Questions?**
- Read full guides: `VPS_DEPLOYMENT_GUIDE.md`, `MULTI_USER_GUIDE.md`
- Check logs: `journalctl -u crypto-bot -f`
- Test locally first: `bash quick_start.sh`

**Issues?**
- Validate config: Check `.env` syntax
- Check permissions: Bot needs write access to `data/`, `logs/`
- Check network: Bot needs outbound HTTPS (443)

---

## 🎉 Ready to Deploy!

**Checklist:**
- [ ] Read `VPS_DEPLOYMENT_GUIDE.md`
- [ ] Complete `PRE_UPLOAD_CHECKLIST.md`
- [ ] Package bot: `bash package_for_vps.sh`
- [ ] Upload to VPS
- [ ] Run: `bash setup_vps.sh`
- [ ] Configure `.env`
- [ ] Start: `systemctl start crypto-bot`
- [ ] Test: Send `/start` in Telegram

**Good luck! 🚀**

---

Made with ❤️ by Advanced Crypto Bot Team
