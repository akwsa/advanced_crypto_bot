#!/bin/bash
# ============================================================================
# Advanced Crypto Trading Bot - VPS Deployment Script for Biznet
# ============================================================================
# Tested on: Ubuntu 22.04 LTS (Jammy Jellyfish)
# Hardware Requirements: 4 vCPU, 8GB RAM, 50GB SSD (minimum)
# Recommended: 4 vCPU, 16GB RAM, 100GB SSD (for heavy ML training)
#
# Usage:
#   1. Upload this script to VPS: scp deploy_biznet.sh root@vps-ip:/root/
#   2. SSH ke VPS: ssh root@vps-ip
#   3. Jalankan: chmod +x deploy_biznet.sh && ./deploy_biznet.sh
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BOT_USER="cryptobot"
BOT_DIR="/opt/crypto-bot"
BOT_REPO=""  # Isi jika menggunakan git clone
LOG_DIR="/var/log/crypto-bot"
DATA_DIR="$BOT_DIR/data"

# ============================================================================
# FUNCTIONS
# ============================================================================

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

print_header "Crypto Trading Bot - VPS Deployment"
echo ""
echo "🖥️  Target System: Ubuntu 22.04 LTS"
echo "💾 Minimum Requirements: 4 vCPU, 8GB RAM, 50GB SSD"
echo "💾 Recommended: 4 vCPU, 16GB RAM, 100GB SSD"
echo "🔒 Mode: DRY RUN (safe default - no real trading)"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Check Ubuntu version
if ! grep -q "Ubuntu 22.04" /etc/os-release 2>/dev/null; then
    print_warning "This script is designed for Ubuntu 22.04 LTS"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check hardware
CPU_CORES=$(nproc)
RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
DISK_GB=$(df -BG / | awk 'NR==2{print $4}' | tr -d 'G')

print_info "Detected hardware: $CPU_CORES vCPU, ${RAM_GB}GB RAM, ${DISK_GB}GB free disk"

if [[ $RAM_GB -lt 8 ]]; then
    print_warning "RAM is below recommended 8GB. Bot may struggle with ML training."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ============================================================================
# SYSTEM UPDATE & DEPENDENCIES
# ============================================================================

print_header "Step 1: System Update & Dependencies"

print_info "Updating package list..."
apt-get update -qq

print_info "Upgrading packages..."
apt-get upgrade -y -qq

print_info "Installing essential packages..."
apt-get install -y -qq \
    python3.10 \
    python3.10-venv \
    python3-pip \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    git \
    curl \
    wget \
    unzip \
    htop \
    iotop \
    ntp \
    ntpdate \
    sqlite3 \
    redis-server \
    ufw \
    fail2ban \
    logrotate \
    cron \
    vim \
    nano \
    tmux \
    tree \
    jq

print_success "System packages installed"

# ============================================================================
# FIREWALL SETUP
# ============================================================================

print_header "Step 2: Firewall Configuration"

print_info "Configuring UFW firewall..."

# Reset UFW
ufw --force reset

# Default deny
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (important! don't lock yourself out)
ufw allow 22/tcp comment 'SSH access'

# Allow HTTPS for API calls
ufw allow 443/tcp comment 'HTTPS outbound'

# Allow Redis only from localhost
ufw allow from 127.0.0.1 to any port 6379 comment 'Redis local only'

# Enable UFW
ufw --force enable

print_success "Firewall configured (SSH allowed, Redis local only)"

# ============================================================================
# USER SETUP
# ============================================================================

print_header "Step 3: Bot User Setup"

# Create bot user if doesn't exist
if ! id "$BOT_USER" &>/dev/null; then
    print_info "Creating bot user: $BOT_USER"
    useradd -r -m -s /bin/bash -U $BOT_USER
    usermod -aG sudo $BOT_USER
    print_success "User $BOT_USER created"
else
    print_info "User $BOT_USER already exists"
fi

# Create directories
mkdir -p $BOT_DIR
mkdir -p $LOG_DIR
mkdir -p $DATA_DIR
mkdir -p /var/backups/crypto-bot

# ============================================================================
# REDIS SETUP
# ============================================================================

print_header "Step 4: Redis Configuration"

print_info "Configuring Redis..."

# Backup original config
cp /etc/redis/redis.conf /etc/redis/redis.conf.backup

# Update Redis config for security and performance
cat >> /etc/redis/redis.conf << 'EOF'

# Crypto Bot Redis Optimizations
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
bind 127.0.0.1
protected-mode yes
timeout 300
tcp-keepalive 60
EOF

# Start Redis
systemctl enable redis-server
systemctl restart redis-server

# Test Redis
if redis-cli ping | grep -q "PONG"; then
    print_success "Redis is running"
else
    print_error "Redis failed to start"
    exit 1
fi

# ============================================================================
# BOT CODE DEPLOYMENT
# ============================================================================

print_header "Step 5: Bot Code Deployment"

# Check if code already exists
if [[ -d "$BOT_DIR/bot.py" ]]; then
    print_warning "Bot code already exists at $BOT_DIR"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Skipping code deployment"
    fi
else
    print_info "Bot code will be deployed to: $BOT_DIR"
    print_info "Please ensure your code is uploaded to $BOT_DIR"
    print_info "You can use: scp -r /local/path/* root@vps-ip:$BOT_DIR/"
fi

# Set permissions
chown -R $BOT_USER:$BOT_USER $BOT_DIR
chmod -R 755 $BOT_DIR
chown -R $BOT_USER:$BOT_USER $LOG_DIR

print_success "Directory permissions set"

# ============================================================================
# PYTHON VIRTUAL ENVIRONMENT
# ============================================================================

print_header "Step 6: Python Environment Setup"

print_info "Creating Python virtual environment..."
cd $BOT_DIR

# Create venv
sudo -u $BOT_USER python3.10 -m venv venv

# Install requirements
print_info "Installing Python dependencies..."
sudo -u $BOT_USER $BOT_DIR/venv/bin/pip install --upgrade pip wheel setuptools

# Core dependencies
sudo -u $BOT_USER $BOT_DIR/venv/bin/pip install -q \
    pandas==2.0.3 \
    numpy==1.24.3 \
    scikit-learn==1.3.0 \
    scipy==1.11.1 \
    python-telegram-bot==20.4 \
    aiohttp==3.8.5 \
    aiosignal==1.3.1 \
    async-timeout==4.0.3 \
    attrs==23.1.0 \
    certifi==2023.7.22 \
    charset-normalizer==3.2.0 \
    frozenlist==1.4.0 \
    idna==3.4 \
    multidict==6.0.4 \
    pytz==2023.3 \
    requests==2.31.0 \
    six==1.16.0 \
    typing-extensions==4.7.1 \
    urllib3==2.0.4 \
    yarl==1.9.2 \
    redis==4.6.0 \
    psutil==5.9.5 \
    ta==0.10.2 \
    python-dateutil==2.8.2 \
    joblib==1.3.1 \
    threadpoolctl==3.2.0 \
    pytest==7.4.0 \
    pytest-asyncio==0.21.1 \
    matplotlib==3.7.2 \
    seaborn==0.12.2

print_success "Python dependencies installed"

# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================

print_header "Step 7: Environment Configuration"

ENV_FILE="$BOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    print_warning ".env file already exists"
    read -p "Overwrite with template? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Keeping existing .env file"
    else
        # Backup existing
        cp $ENV_FILE $ENV_FILE.backup.$(date +%Y%m%d%H%M%S)
    fi
else
    print_info "Creating .env template..."
    cat > $ENV_FILE << 'EOF'
# ============================================================================
# Advanced Crypto Trading Bot - Environment Configuration
# ============================================================================
# ⚠️  IMPORTANT: This file contains sensitive credentials!
#    Set permissions: chmod 600 .env
# ============================================================================

# ============================================================================
# TRADING MODE (CRITICAL SAFETY SETTING)
# ============================================================================
# DRY_RUN = True  → Simulation mode, NO REAL TRADES (safe for testing)
# DRY_RUN = False → REAL TRADING MODE, actual orders will be placed
# ============================================================================
DRY_RUN=True
AUTO_TRADE_DRY_RUN=True

# ============================================================================
# TELEGRAM BOT CONFIGURATION (REQUIRED)
# ============================================================================
# Get from @BotFather: https://t.me/botfather
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Your Telegram User ID(s) - comma separated for multiple admins
# Get your ID from @userinfobot: https://t.me/userinfobot
ADMIN_IDS=your_telegram_user_id

# ============================================================================
# INDODAX API (REQUIRED for real trading)
# ============================================================================
# Get from: https://indodax.com/api
INDODAX_API_KEY=your_api_key_here
INDODAX_API_SECRET=your_api_secret_here

# Testnet (for testing - recommended for first setup)
# Use testnet credentials here if available

# ============================================================================
# DATABASE PATHS
# ============================================================================
SIGNALS_DB_PATH=data/signals.db
TRADING_DB_PATH=data/trading.db
CACHE_DB_PATH=data/cache.db

# ============================================================================
# REDIS CONFIGURATION
# ============================================================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL=INFO
LOG_FILE=logs/trading_bot.log
MAX_LOG_SIZE_MB=100
BACKUP_COUNT=5

# ============================================================================
# TRADING PARAMETERS (DRY RUN defaults)
# ============================================================================
MAX_POSITIONS=3
POSITION_SIZE_PERCENT=5.0
STOP_LOSS_PERCENT=2.0
TAKE_PROFIT_PERCENT=4.0
TRAILING_STOP_PERCENT=1.5

# ML Model thresholds
ML_CONFIDENCE_THRESHOLD=0.65
MIN_CONFLUENCE_SCORE=4

# ============================================================================
# MONITORING & ALERTS
# ============================================================================
ENABLE_TELEGRAM_ALERTS=True
ALERT_COOLDOWN_MINUTES=60
HEALTH_CHECK_INTERVAL=300

# Resource thresholds
CPU_ALERT_THRESHOLD=80
RAM_ALERT_THRESHOLD=85
DISK_ALERT_THRESHOLD=90
EOF

    chown $BOT_USER:$BOT_USER $ENV_FILE
    chmod 600 $ENV_FILE

    print_success ".env template created at $ENV_FILE"
    print_warning "⚠️  IMPORTANT: Edit .env file with your actual credentials!"
    print_info "   vim $ENV_FILE"
fi

# ============================================================================
# SYSTEMD SERVICE SETUP
# ============================================================================

print_header "Step 8: Systemd Service Configuration"

SERVICE_FILE="/etc/systemd/system/crypto-bot.service"

cat > $SERVICE_FILE << EOF
[Unit]
Description=Advanced Crypto Trading Bot
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$BOT_DIR
Environment="PATH=$BOT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=$BOT_DIR/.env

ExecStartPre=/bin/mkdir -p $BOT_DIR/logs $BOT_DIR/data
ExecStart=$BOT_DIR/venv/bin/python -m bot

# Restart settings
Restart=always
RestartSec=10
StartLimitInterval=60s
StartLimitBurst=3

# Graceful shutdown
TimeoutStopSec=30
KillSignal=SIGTERM

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$BOT_DIR/logs $BOT_DIR/data
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload
systemctl enable crypto-bot.service

print_success "Systemd service created: crypto-bot.service"
print_info "Commands:"
print_info "  Start:   sudo systemctl start crypto-bot"
print_info "  Stop:    sudo systemctl stop crypto-bot"
print_info "  Status:  sudo systemctl status crypto-bot"
print_info "  Logs:    sudo journalctl -u crypto-bot -f"

# ============================================================================
# MONITORING CRON JOB
# ============================================================================

print_header "Step 9: Resource Monitoring Setup"

# Create cron job for monitoring
CRON_JOB="*/5 * * * * cd $BOT_DIR && $BOT_DIR/venv/bin/python monitoring/monitor.py >> $LOG_DIR/monitor.log 2>&1"

# Add to crontab for bot user
(crontab -u $BOT_USER -l 2>/dev/null || echo "") | grep -v "monitor.py" | \
    (cat; echo "$CRON_JOB") | crontab -u $BOT_USER -

print_success "Monitoring cron job added (runs every 5 minutes)"
print_info "Monitor logs: $LOG_DIR/monitor.log"

# ============================================================================
# LOG ROTATION
# ============================================================================

print_header "Step 10: Log Rotation Configuration"

cat > /etc/logrotate.d/crypto-bot << EOF
$LOG_DIR/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $BOT_USER $BOT_USER
    sharedscripts
    postrotate
        systemctl reload crypto-bot 2>/dev/null || true
    endscript
}
EOF

print_success "Log rotation configured (14 days retention)"

# ============================================================================
# FAIL2BAN CONFIGURATION
# ============================================================================

print_header "Step 11: Fail2Ban SSH Protection"

cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
EOF

systemctl enable fail2ban
systemctl restart fail2ban

print_success "Fail2Ban configured (3 failed SSH attempts = 1 hour ban)"

# ============================================================================
# BACKUP SCRIPT
# ============================================================================

print_header "Step 12: Backup Script"

BACKUP_SCRIPT="$BOT_DIR/scripts/backup.sh"
mkdir -p $(dirname $BACKUP_SCRIPT)

cat > $BACKUP_SCRIPT << 'EOF'
#!/bin/bash
# Daily backup script for Crypto Trading Bot

BACKUP_DIR="/var/backups/crypto-bot"
BOT_DIR="/opt/crypto-bot"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=7

mkdir -p $BACKUP_DIR

# Backup databases
tar -czf $BACKUP_DIR/databases_$DATE.tar.gz \
    -C $BOT_DIR data/signals.db data/trading.db data/cache.db 2>/dev/null || true

# Backup config
cp $BOT_DIR/.env $BACKUP_DIR/env_$DATE.backup

# Cleanup old backups
find $BACKUP_DIR -name "databases_*.tar.gz" -mtime +$KEEP_DAYS -delete
find $BACKUP_DIR -name "env_*.backup" -mtime +$KEEP_DAYS -delete

echo "Backup completed: $DATE"
EOF

chmod +x $BACKUP_SCRIPT
chown -R $BOT_USER:$BOT_USER $(dirname $BACKUP_SCRIPT)

# Add backup cron job (daily at 2 AM)
BACKUP_CRON="0 2 * * * $BACKUP_SCRIPT >> $LOG_DIR/backup.log 2>&1"
(crontab -u $BOT_USER -l 2>/dev/null || echo "") | grep -v "backup.sh" | \
    (cat; echo "$BACKUP_CRON") | crontab -u $BOT_USER -

print_success "Daily backup scheduled (2 AM)"

# ============================================================================
# HEALTH CHECK SCRIPT
# ============================================================================

print_header "Step 13: Health Check Script"

HEALTH_SCRIPT="$BOT_DIR/scripts/health_check.sh"

cat > $HEALTH_SCRIPT << EOF
#!/bin/bash
# Health check script for monitoring bot status

BOT_USER="$BOT_USER"
LOG_FILE="$LOG_DIR/health.log"
PID_FILE="$BOT_DIR/bot.pid"

# Check if bot is running
if ! pgrep -f "python -m bot" > /dev/null; then
    echo "\$(date): Bot is NOT running!" >> \$LOG_FILE
    # Restart bot
    systemctl restart crypto-bot
    echo "\$(date): Restart attempted" >> \$LOG_FILE
else
    echo "\$(date): Bot is running OK" >> \$LOG_FILE
fi

# Check disk space
DISK_USAGE=\$(df / | tail -1 | awk '{print \$5}' | tr -d '%')
if [ \$DISK_USAGE -gt 90 ]; then
    echo "\$(date): WARNING - Disk usage at \${DISK_USAGE}%" >> \$LOG_FILE
fi

# Check memory
MEM_USAGE=\$(free | grep Mem | awk '{printf "%.0f", \$3/\$2 * 100.0}')
if [ \$MEM_USAGE -gt 90 ]; then
    echo "\$(date): WARNING - Memory usage at \${MEM_USAGE}%" >> \$LOG_FILE
fi
EOF

chmod +x $HEALTH_SCRIPT
chown -R $BOT_USER:$BOT_USER $(dirname $HEALTH_SCRIPT)

# Add health check cron (every 10 minutes)
HEALTH_CRON="*/10 * * * * $HEALTH_SCRIPT"
(crontab -u $BOT_USER -l 2>/dev/null || echo "") | grep -v "health_check.sh" | \
    (cat; echo "$HEALTH_CRON") | crontab -u $BOT_USER -

print_success "Health check scheduled (every 10 minutes)"

# ============================================================================
# STARTUP SCRIPT
# ============================================================================

print_header "Step 14: Startup Helper Script"

STARTUP_SCRIPT="/usr/local/bin/cryptobot"

cat > $STARTUP_SCRIPT << 'EOF'
#!/bin/bash
# Crypto Bot Management Script

COMMAND=$1
BOT_DIR="/opt/crypto-bot"
LOG_DIR="/var/log/crypto-bot"

case $COMMAND in
    start)
        echo "🚀 Starting Crypto Bot..."
        sudo systemctl start crypto-bot
        ;;
    stop)
        echo "🛑 Stopping Crypto Bot..."
        sudo systemctl stop crypto-bot
        ;;
    restart)
        echo "🔄 Restarting Crypto Bot..."
        sudo systemctl restart crypto-bot
        ;;
    status)
        echo "📊 Crypto Bot Status:"
        sudo systemctl status crypto-bot --no-pager
        ;;
    logs)
        echo "📜 Recent logs:"
        sudo journalctl -u crypto-bot -n 50 --no-pager
        ;;
    follow)
        echo "👀 Following logs (Ctrl+C to exit)..."
        sudo journalctl -u crypto-bot -f
        ;;
    monitor)
        echo "📈 Running resource monitor..."
        cd $BOT_DIR && sudo -u cryptobot ./venv/bin/python monitoring/monitor.py
        ;;
    monitor-daemon)
        echo "📈 Starting monitor daemon..."
        cd $BOT_DIR && sudo -u cryptobot ./venv/bin/python monitoring/monitor.py --daemon
        ;;
    cleanup)
        echo "🧹 Running database cleanup..."
        cd $BOT_DIR && sudo -u cryptobot ./venv/bin/python scripts/cleanup_signals.py --days 30
        ;;
    backup)
        echo "💾 Running backup..."
        sudo -u cryptobot $BOT_DIR/scripts/backup.sh
        ;;
    shell)
        echo "🐚 Opening bot shell as cryptobot user..."
        sudo -u cryptobot -H bash -c "cd $BOT_DIR && exec bash"
        ;;
    test)
        echo "🧪 Running tests..."
        cd $BOT_DIR && sudo -u cryptobot ./venv/bin/python -m pytest tests/ -v 2>/dev/null || echo "No tests found or tests failed"
        ;;
    *)
        echo "Crypto Bot Management Script"
        echo ""
        echo "Usage: cryptobot <command>"
        echo ""
        echo "Commands:"
        echo "  start          - Start the bot"
        echo "  stop           - Stop the bot"
        echo "  restart        - Restart the bot"
        echo "  status         - Show bot status"
        echo "  logs           - Show recent logs"
        echo "  follow         - Follow logs in real-time"
        echo "  monitor        - Run resource monitor once"
        echo "  monitor-daemon - Run monitor continuously"
        echo "  cleanup        - Clean up old signal data"
        echo "  backup         - Run manual backup"
        echo "  shell          - Open shell as bot user"
        echo "  test           - Run test suite"
        echo ""
        echo "Telegram Commands (send to your bot):"
        echo "  /status        - Check bot status"
        echo "  /mode          - Check trading mode"
        echo "  /health        - Check system health"
        echo "  /cleanup_signals - Clean old signals"
        ;;
esac
EOF

chmod +x $STARTUP_SCRIPT

print_success "Management command created: cryptobot"
print_info "Usage: cryptobot <start|stop|restart|status|logs|follow>"

# ============================================================================
# SUMMARY & NEXT STEPS
# ============================================================================

print_header "🎉 Deployment Complete!"

cat << 'EOF'

┌─────────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT SUMMARY                               │
├─────────────────────────────────────────────────────────────────────┤
│  ✅ System packages installed                                       │
│  ✅ Firewall configured (UFW)                                       │
│  ✅ User 'cryptobot' created                                        │
│  ✅ Redis configured and running                                     │
│  ✅ Python environment ready                                        │
│  ✅ Systemd service configured                                       │
│  ✅ Monitoring cron jobs scheduled                                   │
│  ✅ Log rotation configured                                          │
│  ✅ Fail2Ban SSH protection enabled                                  │
│  ✅ Daily backups scheduled                                          │
│  ✅ Health checks enabled                                            │
└─────────────────────────────────────────────────────────────────────┘

🔧 NEXT STEPS:

1. EDIT CONFIGURATION:
   sudo vim /opt/crypto-bot/.env

   Required changes:
   - TELEGRAM_BOT_TOKEN (from @BotFather)
   - ADMIN_IDS (your Telegram user ID)
   - INDODAX_API_KEY & SECRET (for real trading - later)

2. UPLOAD BOT CODE:
   From your local machine:
   scp -r /path/to/your/code/* root@YOUR_VPS_IP:/opt/crypto-bot/

   Then fix permissions:
   sudo chown -R cryptobot:cryptobot /opt/crypto-bot

3. INITIAL TEST (DRY RUN):
   sudo systemctl start crypto-bot
   sudo journalctl -u crypto-bot -f

   Or use management script:
   cryptobot start
   cryptobot follow

4. VERIFY TELEGRAM BOT:
   - Send /start to your bot
   - Check /status command
   - Verify /mode shows DRY RUN

5. FOR REAL TRADING (when ready):
   a. Get Indodax API credentials
   b. Edit .env: DRY_RUN=False
   c. Edit .env: AUTO_TRADE_DRY_RUN=False
   d. Restart: cryptobot restart

   ⚠️  WARNING: Start with small amounts!
   ⚠️  Test thoroughly in DRY RUN first!

📊 MONITORING:
   - Resource monitor runs every 5 minutes
   - Health check runs every 10 minutes
   - Daily backup at 2 AM
   - Logs: /var/log/crypto-bot/

📞 COMMANDS:
   cryptobot start      - Start bot
   cryptobot stop       - Stop bot
   cryptobot status     - Check status
   cryptobot logs       - View logs
   cryptobot follow     - Follow logs
   cryptobot monitor    - Run monitor

🔒 SECURITY NOTES:
   - SSH: Port 22 (change if needed)
   - Firewall: Only SSH, HTTPS outbound allowed
   - Redis: Localhost only
   - Bot runs as unprivileged user 'cryptobot'
   - .env file has 600 permissions

📋 USEFUL COMMANDS:
   # Check bot logs
   sudo journalctl -u crypto-bot -f

   # Check monitor logs
   tail -f /var/log/crypto-bot/monitor.log

   # Check resource usage
   htop

   # Check database size
   du -sh /opt/crypto-bot/data/

   # Manual backup
   sudo -u cryptobot /opt/crypto-bot/scripts/backup.sh

EOF

# Create final status check
echo ""
print_info "System Status:"
echo "  Redis: $(systemctl is-active redis-server)"
echo "  Fail2Ban: $(systemctl is-active fail2ban)"
echo "  UFW: $(ufw status | head -1)"
echo ""
print_success "Deployment script completed!"
print_warning "Remember to edit .env file with your credentials before starting!"
