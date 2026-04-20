# 🚀 VPS Deployment Guide - Biznet (Ubuntu 22.04 LTS)

## System Requirements

### Minimum (Basic Operation)
- **vCPU**: 4 cores
- **RAM**: 8 GB
- **Storage**: 50 GB SSD
- **OS**: Ubuntu 22.04 LTS
- **Network**: 100 Mbps (untuk real-time data)

### Recommended (ML Training + Real Trading)
- **vCPU**: 4-8 cores
- **RAM**: 16 GB (ML model training butuh RAM tinggi)
- **Storage**: 100 GB SSD (untuk database historis)
- **OS**: Ubuntu 22.04 LTS
- **Network**: 200 Mbps low latency

---

## 📋 Pre-Deployment Checklist

- [ ] VPS sudah dibeli di Biznet (atau provider lain)
- [ ] Akses SSH root sudah tersedia
- [ ] Bot code sudah siap (git clone atau local upload)
- [ ] Telegram Bot Token sudah dibuat (@BotFather)
- [ ] Telegram User ID sudah diketahui (@userinfobot)
- [ ] Indodax API Key & Secret (untuk real trading - optional)

---

## 🚀 Quick Deployment

### 1. Upload Deployment Script

Dari local machine:
```bash
# Upload deploy script
scp deploy_biznet.sh root@YOUR_VPS_IP:/root/

# SSH ke VPS
ssh root@YOUR_VPS_IP
```

### 2. Run Deployment Script

Di VPS:
```bash
cd /root
chmod +x deploy_biznet.sh
./deploy_biznet.sh
```

Script ini akan:
- Update system dan install dependencies
- Setup firewall (UFW)
- Buat user `cryptobot`
- Install dan configure Redis
- Setup Python virtual environment
- Buat systemd service
- Setup monitoring cron jobs
- Configure log rotation
- Setup Fail2Ban untuk SSH protection

### 3. Upload Bot Code

Dari local machine:
```bash
# Upload semua file bot
scp -r /path/to/advanced_crypto_bot/* root@YOUR_VPS_IP:/opt/crypto-bot/

# Fix permissions (di VPS)
ssh root@YOUR_VPS_IP "chown -R cryptobot:cryptobot /opt/crypto-bot"
```

### 4. Configure Environment

Edit file `.env`:
```bash
ssh root@YOUR_VPS_IP
vim /opt/crypto-bot/.env
```

Isi dengan credentials Anda:
```env
# Telegram (WAJIB)
TELEGRAM_BOT_TOKEN=your_actual_bot_token
ADMIN_IDS=your_telegram_user_id

# Trading Mode (AMAN DEFAULT)
DRY_RUN=True
AUTO_TRADE_DRY_RUN=True

# Indodax (UNTUK REAL TRADING - optional)
INDODAX_API_KEY=your_api_key
INDODAX_API_SECRET=your_api_secret
```

### 5. Start Bot

```bash
cryptobot start
cryptobot follow  # Follow logs
```

Atau manual:
```bash
sudo systemctl start crypto-bot
sudo journalctl -u crypto-bot -f
```

---

## 📊 Management Commands

Command `cryptobot` tersedia untuk management:

```bash
cryptobot start          # Start bot
cryptobot stop           # Stop bot
cryptobot restart        # Restart bot
cryptobot status         # Status bot
cryptobot logs           # Lihat logs
cryptobot follow         # Follow logs real-time
cryptobot monitor        # Run resource monitor once
cryptobot cleanup        # Cleanup old signals
cryptobot backup         # Manual backup
cryptobot shell          # Open shell as bot user
```

---

## 🔒 Security Features

### Firewall (UFW)
- Port 22 (SSH) - open
- Port 443 (HTTPS) - outbound only
- Redis (6379) - localhost only
- Semua incoming lainnya - blocked

### Fail2Ban
- 3 failed SSH attempts = ban 1 jam
- Protect against brute force

### User Isolation
- Bot runs as `cryptobot` user (non-root)
- Limited file system access
- No shell login allowed for security

### Environment Protection
- `.env` file permissions: 600 (owner only)
- Log files: 644 (readable for debugging)
- Database files: 644 (with user ownership)

---

## 📈 Monitoring Setup

### Resource Monitor (Auto)
- Runs every 5 minutes via cron
- Checks CPU, RAM, Disk usage
- Sends Telegram alerts on spikes
- Log: `/var/log/crypto-bot/monitor.log`

### Health Check (Auto)
- Runs every 10 minutes
- Checks if bot process is running
- Auto-restart if bot dies
- Log: `/var/log/crypto-bot/health.log`

### Manual Monitor
```bash
# One-time check
cryptobot monitor

# Continuous monitoring
cryptobot monitor-daemon
```

### Alert Thresholds
- **CPU**: Alert if >80% for 5 minutes
- **RAM**: Alert if >85% for 3 minutes (CRITICAL - OOM risk)
- **Disk**: Alert if >90%
- **Bot Down**: Immediate alert

---

## 💾 Backup & Recovery

### Automatic Backup
- Daily backup at 2 AM
- Location: `/var/backups/crypto-bot/`
- Retention: 7 days
- Includes: databases + config

### Manual Backup
```bash
cryptobot backup
```

### Restore from Backup
```bash
# Stop bot
cryptobot stop

# Restore database
tar -xzf /var/backups/crypto-bot/databases_YYYYMMDD_HHMMSS.tar.gz -C /opt/crypto-bot/

# Restore config
cp /var/backups/crypto-bot/env_YYYYMMDD_HHMMSS.backup /opt/crypto-bot/.env

# Start bot
cryptobot start
```

---

## 🔄 Log Rotation

Logs rotated daily, 14 days retention:
- `/var/log/crypto-bot/trading_bot.log`
- `/var/log/crypto-bot/monitor.log`
- `/var/log/crypto-bot/health.log`

View logs:
```bash
# Bot logs
sudo journalctl -u crypto-bot -f

# Monitor logs
tail -f /var/log/crypto-bot/monitor.log

# All logs
tail -f /var/log/crypto-bot/*.log
```

---

## 🔄 Real Trading Activation

### ⚠️ DANGER ZONE - READ CAREFULLY

**PREREQUISITES:**
- [ ] Bot running in DRY RUN for minimum 7 days
- [ ] All features tested via Telegram commands
- [ ] Signal quality verified via `/signal_stats`
- [ ] Indodax API key dengan permission trading
- [ ] Sufficient balance di Indodax (start small!)

### Activation Steps

1. **Get API Credentials**
   - Login ke Indodax
   - Settings → API Settings
   - Buat API Key dengan permission: View Balance, Trade
   - Simpan Key dan Secret

2. **Edit Environment**
   ```bash
   sudo vim /opt/crypto-bot/.env
   ```

3. **Change Trading Mode**
   ```env
   # DARI:
   DRY_RUN=True
   AUTO_TRADE_DRY_RUN=True

   # MENJADI:
   DRY_RUN=False
   AUTO_TRADE_DRY_RUN=False

   # Tambahkan API credentials:
   INDODAX_API_KEY=your_api_key_here
   INDODAX_API_SECRET=your_api_secret_here
   ```

4. **Restart Bot**
   ```bash
   cryptobot restart
   ```

5. **Verify Real Trading**
   - Telegram: `/mode` → harus show "REAL TRADING"
   - Telegram: `/status` → check trading mode
   - Test dengan `/buy_test` (small amount)

### Safety Limits (Recommended)
```env
MAX_POSITIONS=3
POSITION_SIZE_PERCENT=5.0  # Max 5% portfolio per trade
STOP_LOSS_PERCENT=2.0
TAKE_PROFIT_PERCENT=4.0
```

---

## 🛠️ Troubleshooting

### Bot Won't Start
```bash
# Check logs
sudo journalctl -u crypto-bot -n 50

# Check permissions
ls -la /opt/crypto-bot/

# Check .env exists
cat /opt/crypto-bot/.env

# Manual test
sudo -u cryptobot bash
cd /opt/crypto-bot
source venv/bin/activate
python -m bot
```

### High CPU/RAM
```bash
# Check process
htop

# Check bot stats
cat /var/log/crypto-bot/monitor.log

# Restart if needed
cryptobot restart
```

### Database Issues
```bash
# Check database size
du -sh /opt/crypto-bot/data/

# Cleanup old signals
cryptobot cleanup

# Vacuum database
sqlite3 /opt/crypto-bot/data/signals.db "VACUUM;"
```

### Telegram Bot Not Responding
```bash
# Check bot token
curl -s "https://api.telegram.org/botYOUR_TOKEN/getMe"

# Check if bot is running
cryptobot status

# Restart
cryptobot restart
```

### Redis Issues
```bash
# Check Redis status
systemctl status redis-server
redis-cli ping

# Restart Redis
systemctl restart redis-server
```

---

## 📞 Support Commands

Via Telegram Bot:
```
/start          - Start bot interaction
/status         - Check bot status
/health         - System health check
/mode           - Check trading mode
/cleanup_signals - Clean old signal data
/signal_stats   - Signal performance stats
```

Via SSH:
```bash
cryptobot status
cryptobot logs
cat /var/log/crypto-bot/monitor.log
```

---

## 📝 Post-Deployment Checklist

- [ ] `.env` configured with Telegram token
- [ ] Bot started successfully
- [ ] Telegram commands responding
- [ ] `/status` shows correct trading mode (DRY RUN)
- [ ] Monitor running (check logs)
- [ ] Backup job scheduled
- [ ] Health check scheduled
- [ ] Firewall active (ufw status)
- [ ] Fail2Ban active
- [ ] Tested `/signal_stats` command
- [ ] (Optional) Indodax API configured
- [ ] (Optional) Ready for real trading test

---

## 🎯 Production Checklist

Before going fully live:

- [ ] Run minimum 7 days in DRY RUN
- [ ] Verify signal accuracy >65%
- [ ] Test all Telegram commands
- [ ] Monitor resource usage patterns
- [ ] Setup Telegram alerts (CPU/RAM)
- [ ] Configure backup verification
- [ ] Document emergency stop procedures
- [ ] Test real trading dengan small amount
- [ ] Setup monitoring dashboard (optional)
- [ ] Configure log shipping (optional)

---

**Last Updated**: 2026-04-14
**Version**: 1.0.0
**Compatible with**: Bot Version 3.0+
