# 🚀 VPS Deployment Package - COMPLETE

## 📦 What's Included

This deployment package contains everything needed to deploy the Advanced Crypto Trading Bot on a Biznet VPS (or any Ubuntu 22.04 LTS server).

### Files Created

| File | Purpose |
|------|---------|
| `deploy_biznet.sh` | Main deployment script - run once on VPS |
| `DEPLOY_BIZNET.md` | Complete deployment guide |
| `monitoring/monitor.py` | Resource monitoring with Telegram alerts |
| `scripts/validate_setup.py` | Post-deployment validation |
| `scripts/cleanup_signals.py` | Database cleanup utility |
| `VPS_DEPLOYMENT_COMPLETE.md` | This summary |

---

## 🎯 Quick Start (3 Steps)

### 1. Prepare VPS
- Beli VPS di Biznet: **4 vCPU, 8GB RAM, 50GB SSD** (minimum)
- Pilih OS: **Ubuntu 22.04 LTS**
- Dapatkan IP address dan password root

### 2. Upload & Deploy
```bash
# Dari local machine
scp deploy_biznet.sh root@YOUR_VPS_IP:/root/
scp -r /path/to/bot/* root@YOUR_VPS_IP:/opt/crypto-bot/

# SSH ke VPS
ssh root@YOUR_VPS_IP

# Jalankan deployment
cd /root
./deploy_biznet.sh
```

### 3. Configure & Start
```bash
# Edit environment
vim /opt/crypto-bot/.env
# Isi: TELEGRAM_BOT_TOKEN, ADMIN_IDS

# Start bot
cryptobot start
cryptobot follow
```

---

## 📊 Monitoring Features

### CPU/RAM Spike Alerts
- **Check interval**: Every 5 minutes (cron)
- **CPU Alert**: >80% for 5 minutes
- **RAM Alert**: >85% for 3 minutes (CRITICAL - OOM risk)
- **Disk Alert**: >90%
- **Cooldown**: 1 jam antar alert sama

### Health Checks
- **Check interval**: Every 10 minutes
- **Auto-restart**: Jika bot mati
- **Disk monitoring**: Alert jika penuh

### Manual Monitoring
```bash
# One-time check
cryptobot monitor

# Continuous (daemon mode)
cryptobot monitor-daemon

# View logs
tail -f /var/log/crypto-bot/monitor.log
```

---

## 🔧 Management Commands

After deployment, gunakan command `cryptobot`:

```bash
cryptobot start      # Start bot
cryptobot stop       # Stop bot
cryptobot restart    # Restart bot
cryptobot status     # Check status
cryptobot logs       # View logs
cryptobot follow     # Follow logs
cryptobot monitor    # Run monitor
cryptobot backup     # Manual backup
cryptobot cleanup    # Cleanup old data
cryptobot shell      # Open bot shell
```

---

## 🔒 Security Features

| Feature | Status | Description |
|---------|--------|-------------|
| **UFW Firewall** | ✅ Active | SSH (22), HTTPS (443) only |
| **Fail2Ban** | ✅ Active | 3 failed SSH = 1h ban |
| **User Isolation** | ✅ cryptobot | Runs as unprivileged user |
| **Redis Local** | ✅ localhost:6379 | No external access |
| **Env Permissions** | ✅ 600 | Owner only |
| **No Root Bot** | ✅ | Bot tidak jalan sebagai root |

---

## 📈 Resource Requirements

### Minimum (Basic)
- **vCPU**: 4 cores
- **RAM**: 8 GB
- **Disk**: 50 GB SSD
- **Network**: 100 Mbps

### Recommended (ML + Real Trading)
- **vCPU**: 4-8 cores
- **RAM**: 16 GB (ML training intensif)
- **Disk**: 100 GB SSD (historical data)
- **Network**: 200 Mbps low latency

### Why 16GB RAM?
- ML Model Training: 4-6 GB
- Price Cache Redis: 512 MB
- Database Operations: 2-3 GB
- Telegram Bot + Workers: 1-2 GB
- OS + System: 2-3 GB
- **Total**: ~10-14 GB peak usage

---

## 🔄 Real Trading Activation

### ⚠️ SAFETY FIRST

1. **Test DRY RUN minimal 7 hari**
2. **Verifikasi signal quality >65%**
3. **Mulai dengan amount kecil**

### Activation Steps
```bash
# 1. Edit config
vim /opt/crypto-bot/.env

# 2. Change mode
DRY_RUN=False
AUTO_TRADE_DRY_RUN=False
INDODAX_API_KEY=your_key
INDODAX_API_SECRET=your_secret

# 3. Restart
cryptobot restart

# 4. Verify
# Telegram: /mode → "REAL TRADING"
```

---

## 🛠️ Troubleshooting

### Bot tidak start
```bash
# Check logs
sudo journalctl -u crypto-bot -n 50

# Validate setup
python scripts/validate_setup.py

# Check permissions
ls -la /opt/crypto-bot/
```

### RAM/CPU tinggi
```bash
# Check monitor logs
tail -f /var/log/crypto-bot/monitor.log

# Check processes
htop

# Restart
systemctl restart crypto-bot
```

### Database besar
```bash
# Cleanup old signals
cryptobot cleanup

# Or manual
python scripts/cleanup_signals.py --days 30

# Vacuum database
sqlite3 /opt/crypto-bot/data/signals.db "VACUUM;"
```

---

## 📞 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Mulai interaksi |
| `/status` | Status bot |
| `/mode` | Check trading mode |
| `/health` | System health |
| `/signal_stats` | Signal performance |
| `/cleanup_signals` | Cleanup old data |
| `/buy_test` | Test buy (real mode) |
| `/positions` | View positions |

---

## 📝 Validation Checklist

Jalankan setelah deployment:
```bash
python scripts/validate_setup.py --verbose
```

Expected output:
```
✅ All required packages installed
✅ User 'cryptobot' exists
✅ Redis is running
✅ Service enabled for auto-start
✅ Trading mode: DRY RUN (safe)
🎉 All checks passed! Setup is ready.
```

---

## 🎯 Deployment Checklist

- [ ] VPS purchased (4 vCPU, 8GB RAM, 50GB SSD)
- [ ] Ubuntu 22.04 LTS installed
- [ ] `deploy_biznet.sh` uploaded
- [ ] Bot code uploaded ke `/opt/crypto-bot/`
- [ ] Deployment script executed
- [ ] `.env` configured dengan Telegram token
- [ ] Bot started: `cryptobot start`
- [ ] Telegram commands tested
- [ ] `/status` shows correct mode (DRY RUN)
- [ ] Monitor running (check logs)
- [ ] Backup job scheduled
- [ ] Health check scheduled
- [ ] Validation passed: `validate_setup.py`
- [ ] (Optional) Indodax API configured
- [ ] (Optional) Ready for real trading

---

## 📋 File Structure After Deployment

```
/opt/crypto-bot/
├── bot.py                 # Main entry point
├── .env                   # Environment config (600 permissions)
├── venv/                  # Python virtual environment
├── core/                  # Core modules
├── signals/               # Signal generation
├── analysis/              # Analysis tools
├── trading/               # Trading modules
├── monitoring/
│   └── monitor.py         # Resource monitoring
├── scripts/
│   ├── validate_setup.py  # Setup validation
│   ├── cleanup_signals.py   # DB cleanup
│   └── backup.sh          # Backup script
├── data/
│   ├── signals.db         # Signal database
│   ├── trading.db         # Trading database
│   └── cache.db           # Cache database
└── logs/                  # Log files

/var/log/crypto-bot/       # System logs
/var/backups/crypto-bot/   # Backup storage
```

---

## 🚀 Ready for Production

Dengan setup ini, bot Anda siap untuk:
- ✅ **Dry Run Testing** - Safe simulation mode
- ✅ **Real Trading** - When ready
- ✅ **Auto Monitoring** - CPU/RAM/Disk alerts
- ✅ **Auto Backup** - Daily backups
- ✅ **Auto Restart** - If bot crashes
- ✅ **Security** - Firewall + Fail2Ban + User isolation

---

**Deployment Package Version**: 1.0.0
**Last Updated**: 2026-04-14
**Compatible**: Bot Version 3.0+
