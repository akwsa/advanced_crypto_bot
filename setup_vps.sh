#!/bin/bash
# =============================================================================
# Advanced Crypto Bot - VPS Setup Automation Script
# =============================================================================
# Usage: bash setup_vps.sh
# Run this script on your VPS after uploading the bot files
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Bot configuration
BOT_DIR="/opt/crypto-bot"
APP_DIR="$BOT_DIR/advanced_crypto_bot"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="crypto-bot"
LOG_DIR="/var/log"

# Functions
print_header() {
    echo -e "${BLUE}=================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=================================================${NC}"
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

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run as root (use sudo)"
        exit 1
    fi
}

# Main installation steps
print_header "Advanced Crypto Bot - VPS Setup"
echo ""

# 1. Check if running as root
print_info "Checking permissions..."
check_root
print_success "Running as root"
echo ""

# 2. Update system
print_header "Step 1: Update System"
apt update && apt upgrade -y
print_success "System updated"
echo ""

# 3. Install dependencies
print_header "Step 2: Install Dependencies"
apt install -y python3 python3-pip python3-venv \
    build-essential libssl-dev libffi-dev python3-dev \
    git wget curl nano htop \
    redis-server
print_success "Dependencies installed"
echo ""

# 4. Enable Redis
print_header "Step 3: Setup Redis"
systemctl enable redis-server
systemctl start redis-server
print_success "Redis enabled and started"
echo ""

# 5. Check if bot directory exists
print_header "Step 4: Setup Bot Directory"
if [ ! -d "$APP_DIR" ]; then
    print_error "Bot directory not found: $APP_DIR"
    print_info "Please upload bot files first"
    exit 1
fi
print_success "Bot directory found: $APP_DIR"
echo ""

# 6. Create virtual environment
print_header "Step 5: Setup Python Virtual Environment"
cd "$APP_DIR"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_warning "Virtual environment already exists"
fi
echo ""

# 7. Install Python dependencies
print_header "Step 6: Install Python Packages"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
print_success "Python packages installed"
echo ""

# 8. Setup .env file
print_header "Step 7: Configure Environment"
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        print_warning ".env created from .env.example"
        print_warning "⚠️  IMPORTANT: Edit .env with your configuration!"
        print_info "Run: nano $APP_DIR/.env"
    else
        print_error ".env.example not found"
        exit 1
    fi
else
    print_success ".env already exists"
fi
echo ""

# 9. Create systemd service
print_header "Step 8: Setup Systemd Service"
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Advanced Crypto Trading Bot
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=${VENV_DIR}/bin/python3 bot.py
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/${SERVICE_NAME}.log
StandardError=append:${LOG_DIR}/${SERVICE_NAME}-error.log

# Resource limits
MemoryMax=2G
MemoryHigh=1.5G

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
print_success "Systemd service created"
echo ""

# 10. Setup backup script
print_header "Step 9: Setup Backup Script"
mkdir -p "$BOT_DIR/backups"
cat > "$BOT_DIR/backup.sh" << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/crypto-bot/backups"
DB_FILE="/opt/crypto-bot/advanced_crypto_bot/data/trading.db"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
if [ -f "$DB_FILE" ]; then
    cp $DB_FILE $BACKUP_DIR/trading_${DATE}.db
    find $BACKUP_DIR -name "trading_*.db" -mtime +7 -delete
    echo "✅ Backup completed: trading_${DATE}.db"
else
    echo "⚠️  Database not found: $DB_FILE"
fi
EOF

chmod +x "$BOT_DIR/backup.sh"
print_success "Backup script created"
echo ""

# 11. Setup cron for auto-backup
print_header "Step 10: Setup Auto Backup (Daily 2AM)"
(crontab -l 2>/dev/null | grep -v "crypto-bot/backup.sh"; echo "0 2 * * * $BOT_DIR/backup.sh >> $LOG_DIR/crypto-backup.log 2>&1") | crontab -
print_success "Cron job added for daily backup"
echo ""

# 12. Create log rotation config
print_header "Step 11: Setup Log Rotation"
cat > /etc/logrotate.d/crypto-bot << EOF
${LOG_DIR}/${SERVICE_NAME}.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 root root
}

${LOG_DIR}/${SERVICE_NAME}-error.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 root root
}
EOF
print_success "Log rotation configured"
echo ""

# 13. Create helpful aliases
print_header "Step 12: Setup Helpful Aliases"
cat >> ~/.bashrc << 'EOF'

# Crypto Bot aliases
alias bot-start='systemctl start crypto-bot'
alias bot-stop='systemctl stop crypto-bot'
alias bot-restart='systemctl restart crypto-bot'
alias bot-status='systemctl status crypto-bot'
alias bot-logs='journalctl -u crypto-bot -f'
alias bot-logs-error='tail -f /var/log/crypto-bot-error.log'
alias bot-cd='cd /opt/crypto-bot/advanced_crypto_bot'
alias bot-backup='bash /opt/crypto-bot/backup.sh'
EOF
print_success "Shell aliases added (restart shell to use)"
echo ""

# Final summary
print_header "🎉 Installation Complete!"
echo ""
print_success "Bot setup completed successfully!"
echo ""
print_warning "⚠️  IMPORTANT NEXT STEPS:"
echo ""
echo "1️⃣  Configure .env file:"
echo "   nano $APP_DIR/.env"
echo ""
echo "   Required settings:"
echo "   - TELEGRAM_BOT_TOKEN=your_token"
echo "   - ADMIN_IDS=123456789,987654321"
echo "   - WATCH_PAIRS=btcidr,ethidr,bridr"
echo ""
echo "2️⃣  Enable auto-start on boot:"
echo "   systemctl enable crypto-bot"
echo ""
echo "3️⃣  Start the bot:"
echo "   systemctl start crypto-bot"
echo ""
echo "4️⃣  Check status:"
echo "   systemctl status crypto-bot"
echo ""
echo "5️⃣  View logs (real-time):"
echo "   journalctl -u crypto-bot -f"
echo ""
print_info "Useful commands (after restarting shell):"
echo "   bot-start    - Start bot"
echo "   bot-stop     - Stop bot"
echo "   bot-restart  - Restart bot"
echo "   bot-status   - Check status"
echo "   bot-logs     - View logs (real-time)"
echo "   bot-cd       - Go to bot directory"
echo "   bot-backup   - Manual backup"
echo ""
print_header "Setup Complete! 🚀"
