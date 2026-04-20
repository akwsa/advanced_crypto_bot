# 🐳 Docker Deployment Guide

## Arsitektur Docker Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    VPS Biznet GIO 4GB                       │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   crypto-    │  │   crypto-    │  │    crypto-       │  │
│  │    redis     │  │     bot      │  │     worker       │  │
│  │              │  │              │  │                  │  │
│  │  Redis 7     │  │  bot.py      │  │  worker.py       │  │
│  │  Alpine      │  │  Telegram    │  │  Queue Processor │  │
│  │  256MB max   │  │  REST Poller │  │  Heavy Tasks     │  │
│  │              │  │  1.5GB max   │  │  1GB max         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └─────────────────┼────────────────────┘            │
│                   Docker Network: crypto-net                │
│                                                             │
│  Volumes (Persistent):                                      │
│  redis-data, bot-data, bot-logs, bot-models, bot-backups   │
│                                                             │
│  Total Memory: ~2.5GB / 4GB  ✅                             │
└─────────────────────────────────────────────────────────────┘
```

### Resource Allocation

| Service | Memory Limit | CPU Limit | Purpose |
|---------|-------------|-----------|---------|
| **redis** | 256MB | - | Cache + Queue |
| **bot** | 1.5GB | 2.0 cores | Telegram + REST Poller |
| **worker** | 1GB | 1.5 cores | Heavy tasks (s_posisi, s_menu, signals) |
| **Total** | **~2.5GB** | **3.5 cores** | ✅ Fits in 4GB VPS |

---

## 🚀 Quick Start

### 1. Install Docker di VPS

```bash
# SSH ke VPS
ssh root@<vps-ip>

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
sudo apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker
```

### 2. Setup Project

```bash
# Create directory
sudo mkdir -p /opt/crypto_bot
cd /opt/crypto_bot

# Upload files (via SCP/SFTP dari Windows)
# scp -r c:\advanced_crypto_bot\* root@<vps-ip>:/opt/crypto_bot/

# Create .env file
cp .env.example .env
nano .env  # Edit dengan nilai Anda
```

### 3. Build & Run

```bash
# Build images
sudo docker compose build

# Start all services
sudo docker compose up -d

# Check status
sudo docker compose ps

# View logs
sudo docker compose logs -f
```

### 4. Verify

```bash
# Check all services running
sudo docker compose ps

# Expected output:
# NAME             STATUS         PORTS
# crypto-bot       Up (healthy)
# crypto-worker    Up
# crypto-redis     Up (healthy)   127.0.0.1:6379->6379/tcp

# Check Redis
sudo docker exec crypto-redis redis-cli ping
# Output: PONG

# Check bot logs
sudo docker logs crypto-bot --tail 50 -f

# Check worker logs
sudo docker logs crypto-worker --tail 20 -f
```

---

## 📋 Command Reference

### Docker Compose Commands

```bash
# Start all services
sudo docker compose up -d

# Stop all services
sudo docker compose down

# Restart specific service
sudo docker compose restart bot

# View logs
sudo docker compose logs -f           # All services
sudo docker compose logs -f bot       # Bot only
sudo docker compose logs -f worker    # Worker only
sudo docker compose logs -f redis     # Redis only

# Rebuild after code changes
sudo docker compose build
sudo docker compose up -d

# Update (pull new code + rebuild)
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d

# Check resource usage
sudo docker stats

# Enter bot container
sudo docker exec -it crypto-bot bash

# Enter worker container
sudo docker exec -it crypto-worker bash

# Enter Redis container
sudo docker exec -it crypto-redis redis-cli
```

### Maintenance

```bash
# Backup database
sudo docker exec crypto-bot cp /app/data/trading.db /app/backups/trading_$(date +%Y%m%d).db

# Copy backup to host
sudo docker cp crypto-bot:/app/backups/trading_20260411.db ./backups/

# Clean old images
sudo docker image prune -f

# Clean stopped containers
sudo docker container prune -f

# Full cleanup
sudo docker system prune -f
```

---

## 🔄 Update Bot Code

```bash
# 1. Upload new files ke VPS
scp -r c:\advanced_crypto_bot\* root@<vps-ip>:/opt/crypto_bot/

# 2. Di VPS, rebuild dan restart
cd /opt/crypto_bot
sudo docker compose build
sudo docker compose up -d

# 3. Verify
sudo docker compose ps
sudo docker compose logs -f bot
```

**Atau lebih cepat (tanpa rebuild jika hanya code change):**
```bash
cd /opt/crypto_bot
sudo docker compose down
sudo docker compose up -d --build
```

---

## 🐛 Troubleshooting

### Bot tidak start

```bash
# Check logs
sudo docker compose logs bot

# Common issues:
# 1. Missing .env
ls -la .env

# 2. Redis not healthy
sudo docker compose logs redis
sudo docker exec crypto-redis redis-cli INFO server

# 3. Build error
sudo docker compose build --no-cache
```

### Worker crash

```bash
# Check worker logs
sudo docker compose logs worker

# Restart worker only
sudo docker compose restart worker
```

### Redis memory full

```bash
# Check Redis memory
sudo docker exec crypto-redis redis-cli INFO memory

# Flush cache (if needed)
sudo docker exec crypto-redis redis-cli FLUSHDB
```

### Database corrupt

```bash
# Stop bot
sudo docker compose stop bot

# Restore from backup
sudo docker cp ./backups/trading_20260410.db crypto-bot:/app/data/trading.db

# Start bot
sudo docker compose start bot
```

### High memory usage

```bash
# Check resource usage
sudo docker stats

# If bot > 1.5GB, restart
sudo docker compose restart bot

# Check inside container
sudo docker exec crypto-bot ps aux
sudo docker exec crypto-bot free -h
```

---

## 📊 Monitoring

### Resource Monitoring

```bash
# Real-time stats
sudo docker stats

# One-shot
sudo docker stats --no-stream

# Memory only
sudo docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"
```

### Health Checks

```bash
# Bot health
sudo docker inspect --format='{{.State.Health.Status}}' crypto-bot

# Redis health
sudo docker exec crypto-redis redis-cli ping

# Worker status
sudo docker inspect --format='{{.State.Status}}' crypto-worker
```

### Log Rotation (Automatic)

Docker compose sudah config log rotation:
- Bot: max 10MB × 3 files = 30MB
- Worker: max 5MB × 2 files = 10MB

**Total logs: < 50MB** ✅

---

## 🔒 Security

### Docker-specific

```bash
# Run as non-root (sudah di Dockerfile)
USER cryptobot

# Isolate network (sudah di docker-compose.yml)
networks:
  crypto-net:
    driver: bridge

# Redis only accessible internally (tidak expose ke public)
ports:
  - "127.0.0.1:6379:6379"
```

### .env Protection

```bash
# .env TIDAK di-copy ke container (sudah di .dockerignore)
# Tapi tetap diperlukan di host untuk docker compose

# Set restrictive permissions
chmod 600 .env
```

---

## ⚡ Performance Tuning

### Redis Optimization (sudah di docker-compose.yml)

```yaml
command: >
  redis-server
  --maxmemory 256mb
  --maxmemory-policy allkeys-lru  # Evict least recently used
  --save 60 1000                   # Save every 60s if 1000+ keys changed
  --appendonly yes                 # Persistent AOF
```

### Bot Memory Limit (sudah di docker-compose.yml)

```yaml
deploy:
  resources:
    limits:
      memory: 1536M    # Hard limit
      cpus: '2.0'
```

### Worker CPU Priority

```yaml
deploy:
  resources:
    limits:
      cpus: '1.5'      # Can use up to 1.5 cores
    reservations:
      cpus: '0.25'     # Guaranteed minimum
```

---

## 📝 Development Workflow

### Local Testing (Windows)

```powershell
# Build locally
docker compose build

# Run locally
docker compose up

# Test bot
# Kirim pesan ke bot di Telegram

# Stop
docker compose down
```

### Production Deploy

```bash
# Di VPS
cd /opt/crypto_bot
docker compose up -d --build

# Verify
docker compose ps
docker compose logs -f
```

---

## 🎯 vs systemd (Non-Docker)

| Aspect | Docker | systemd |
|--------|--------|---------|
| **Setup** | `docker compose up -d` | Script manual |
| **Isolation** | ✅ Container isolated | ❌ Shared environment |
| **Redis** | ✅ Auto-setup | Manual install |
| **Worker** | ✅ Auto-run | Manual config |
| **Updates** | Rebuild + restart | Manual file copy |
| **Rollback** | `docker compose down` + old image | Manual |
| **Logs** | `docker compose logs -f` | journalctl |
| **Memory Limit** | ✅ Built-in | ✅ systemd MemoryMax |
| **Overhead** | ~100MB | ~0MB |
| **Learning Curve** | Medium | Low |

**Kesimpulan: Docker recommended untuk VPS ini** karena:
1. Multi-service (bot + worker + redis) otomatis
2. Resource limits built-in
3. Easy updates & rollbacks
4. Isolation = lebih aman

---

**Last updated:** 2026-04-11
