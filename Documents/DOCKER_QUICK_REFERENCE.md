# 🚀 Quick Reference - Docker Deployment

## 1-Line Commands

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh && sudo systemctl enable docker

# Setup & Run
mkdir -p /opt/crypto_bot && cd /opt/crypto_bot
# Upload files via SCP
sudo docker compose up -d --build

# Check
sudo docker compose ps && sudo docker compose logs -f
```

## Resource Usage (4GB VPS)

| Service | RAM | CPU | Purpose |
|---------|-----|-----|---------|
| redis | 256MB | - | Cache + Queue |
| bot | 1.5GB | 2 cores | Telegram + REST |
| worker | 1GB | 1.5 cores | Heavy tasks |
| **Total** | **~2.5GB** | **3.5 cores** | ✅ |

## Daily Commands

```bash
docker compose ps              # Status
docker compose logs -f         # Logs
docker compose logs -f bot     # Bot logs
docker stats                   # Resources
docker compose down            # Stop
docker compose up -d           # Start
docker compose restart bot     # Restart bot
```

## Update Bot Code

```bash
# Upload new files
scp -r c:\advanced_crypto_bot\* root@<vps-ip>:/opt/crypto_bot/

# Rebuild + restart
cd /opt/crypto_bot
sudo docker compose up -d --build
```

## Files Created

| File | Purpose |
|------|---------|
| `Dockerfile` | Bot image |
| `Dockerfile.worker` | Worker image |
| `docker-compose.yml` | Stack config |
| `.dockerignore` | Build exclusions |
| `worker.py` | Background worker |
| `DOCKER_DEPLOYMENT_GUIDE.md` | Full guide |
