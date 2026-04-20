# 🚀 PRE-DEPLOYMENT SUMMARY

**Date:** 2026-04-11
**Target:** VPS Biznet GIO (4 vCPU, 4GB RAM, 60GB SSD)

---

## ✅ CHECKS PASSED (Local)

### File Structure (27/27)
```
✅ All 23 required files present
✅ All 4 directories created (data, logs, models, backups)
```

### Environment
```
✅ TELEGRAM_BOT_TOKEN configured
✅ ADMIN_IDS configured
```

### Python Dependencies
```
✅ python-telegram-bot
✅ pandas
✅ numpy
✅ scikit-learn
✅ requests
✅ python-dotenv
✅ aiohttp
✅ psutil
✅ joblib
✅ redis (optional)
```

### Docker
```
✅ Docker Desktop installed (Windows)
✅ Docker Compose v2.40.3
⚠️  Redis NOT installed locally (will be installed on VPS via Docker)
```

---

## 🔧 FIXES APPLIED BEFORE DEPLOYMENT

### 1. ML Model Fix (`ml_model.py`)
- **Bug:** `'NoneType' object has no attribute 'tree_'`
- **Fix:** Added `_is_fitted` flag to track training state
- **Result:** Bot now gracefully falls back to TA-only signals

### 2. TA Strength Fix (`technical_analysis.py`)
- **Bug:** TA = -1.0 when only 1 of 5 indicators bearish
- **Fix:** Weighted average per indicator (scores: -1, -0.5, 0, +0.5, +1)
- **Result:** Realistic TA values

### 3. Signal Threshold Fix (`trading_engine.py`)
- **Bug:** STRONG signals too easy to trigger
- **Fix:** Raised threshold to ±0.6 + ML confidence > 70%
- **Result:** Fewer false positives

### 4. Signal Stabilizer (`bot.py`)
- **Bug:** HOLD → STRONG_SELL in 1 cycle
- **Fix:** Level-based jump detection (5+ levels → HOLD, 3+ → downgrade)
- **Result:** Smooth signal transitions

### 5. ML Training Data Improvement (`bot.py`)
- **Changed:** Load 5000 candles per pair (was 1000)
- **Changed:** Auto-retrain ALWAYS (was only when trading enabled)
- **Changed:** Marginal training at 100+ candles with warning
- **Changed:** Better logging with pair count and accuracy

### 6. Auto-Restart Health Monitor (`bot.py`)
- **Added:** Memory watcher via psutil
- **Added:** Auto-restart if memory > 2GB (VPS safety)
- **Added:** Max 5 restarts per hour (prevent restart loop)
- **Added:** Memory logging every 5 minutes

### 7. Dependencies (`requirements.txt`)
- **Removed:** TensorFlow (saves 1-2GB RAM)
- **Added:** redis (required for cache + queue)

### 8. Docker Stack (`docker-compose.yml`)
- **Services:** bot + worker + redis
- **Memory:** 1.5GB (bot) + 1GB (worker) + 256MB (redis) = 2.75GB max
- **Auto-restart:** `restart: unless-stopped`

---

## 📊 ML TRAINING DATA STATUS

| Metric | Value | Status |
|--------|-------|--------|
| Min candles needed | 100 | - |
| Recommended | 200+ | - |
| Data load per pair | 5000 candles | ✅ |
| Auto-retrain | Every 24h (always) | ✅ |
| Startup training | Yes (if needed) | ✅ |
| Cleanup old data | 30 days | ✅ |

**Behavior on fresh deploy:**
1. Bot starts → no model → uses TA-only signals
2. Price poller collects data every 15s
3. After ~50 minutes: 200 candles collected → auto-train
4. Every 24h: retrain with all accumulated data

---

## 🐳 DEPLOYMENT STEPS (VPS)

```bash
# 1. SSH to VPS
ssh root@<vps-ip>

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker

# 3. Create directory and upload files
mkdir -p /opt/crypto_bot
# Upload via SCP from Windows:
# scp -r c:\advanced_crypto_bot\* root@<vps-ip>:/opt/crypto_bot/

# 4. Setup environment
cd /opt/crypto_bot
cp .env.example .env
nano .env  # Fill in your actual values

# 5. Run pre-deploy check
python pre_deploy_check.py

# 6. Build and deploy
docker compose up -d --build

# 7. Verify
docker compose ps
docker compose logs -f bot
```

---

## 🔒 SECURITY CHECKLIST

- [x] `.env` in `.gitignore`
- [x] No hardcoded secrets in code
- [x] Docker runs as non-root user
- [x] Redis only accessible internally (127.0.0.1)
- [x] Memory limits enforced (2GB hard cap for bot)
- [ ] **⚠️ ROTATE Indodax API keys** (exposed in chat history)
- [ ] Set `.env` permissions: `chmod 600 .env`

---

## 📈 EXPECTED VPS RESOURCE USAGE

```
Service       RAM       CPU       Disk
─────────────────────────────────────────
redis         100MB     -         50MB
bot           400-600MB 1-2 cores 200MB
worker        200-400MB 0.5-1 core 100MB
─────────────────────────────────────────
TOTAL         ~1-1.4GB  ~3 cores  ~350MB
FREE          ~2.6-3GB  ~1 core   ~59.6GB  ✅
```

---

## ⏱️ TIMELINE AFTER DEPLOYMENT

```
T+0s     : Bot starts, connects to Telegram
T+5s     : Price poller starts collecting data
T+10s    : Redis cache starts
T+15s    : First price data available
T+30s    : First signals can be generated (TA-only)
T+1min   : Auto-retrain checks data availability
T+50min  : ~200 candles collected → ML model trained
T+24h    : Auto-retrain #1 with full day data
```

---

## 📞 POST-DEPLOYMENT COMMANDS

```bash
# Check everything
docker compose ps && docker stats --no-stream

# View bot logs
docker compose logs -f bot

# View worker logs
docker compose logs -f worker

# Check Redis
docker exec crypto-redis redis-cli INFO memory

# Restart bot
docker compose restart bot

# Update code
# Upload new files via SCP, then:
docker compose up -d --build

# Emergency stop
docker compose down
```

---

**Status:** ✅ READY FOR DEPLOYMENT (after API key rotation)
