#!/bin/bash
# =============================================================================
# Deployment Script untuk VPS Biznet GIO (Ubuntu 22.04/24.04)
# Spesifikasi: 4 vCPU, 4GB RAM, 60GB SSD
# =============================================================================

set -e  # Exit on error

echo "🚀 Starting Crypto Bot Deployment..."

# =============================================================================
# 1. SYSTEM UPDATE & DEPENDENCIES
# =============================================================================
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "📦 Installing system dependencies..."
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    redis-server \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    git \
    curl \
    htop \
    wget

# =============================================================================
# 2. REDIS SETUP
# =============================================================================
echo "💾 Setting up Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Test Redis connection
redis-cli ping | grep -q "PONG" && echo "✅ Redis running" || echo "❌ Redis failed"

# =============================================================================
# 3. CREATE BOT USER & DIRECTORIES
# =============================================================================
echo "👤 Creating cryptobot user..."
sudo useradd -m -s /bin/bash cryptobot 2>/dev/null || echo "User already exists"

echo "📁 Creating directories..."
sudo mkdir -p /opt/crypto_bot/{data,logs,models,backups}
sudo chown -R cryptobot:cryptobot /opt/crypto_bot

# =============================================================================
# 4. DEPLOY BOT FILES
# =============================================================================
echo "📂 Deploying bot files..."
# Copy bot files to /opt/crypto_bot
sudo cp -r /path/to/your/bot/* /opt/crypto_bot/
sudo chown -R cryptobot:cryptobot /opt/crypto_bot

# =============================================================================
# 5. PYTHON VIRTUAL ENVIRONMENT
# =============================================================================
echo "🐍 Setting up Python virtual environment..."
cd /opt/crypto_bot
sudo -u cryptobot python3.11 -m venv /opt/crypto_bot/venv
sudo -u cryptobot /opt/crypto_bot/venv/bin/pip install --upgrade pip

echo "📦 Installing Python dependencies..."
sudo -u cryptobot /opt/crypto_bot/venv/bin/pip install -r requirements.txt

# Note: TA-Lib C library harus diinstall terpisah
# Jika ta-lib install gagal, jalankan manual:
# wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
# tar -xzf ta-lib-0.4.0-src.tar.gz
# cd ta-lib/
# ./configure --prefix=/usr
# make
# sudo make install
# cd ..
# rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# =============================================================================
# 6. ENVIRONMENT CONFIGURATION
# =============================================================================
echo "⚙️ Setting up environment..."
if [ ! -f /opt/crypto_bot/.env ]; then
    echo "⚠️  .env file not found! Please create it manually:"
    echo "   sudo nano /opt/crypto_bot/.env"
    echo "   # Gunakan template di .env.example"
else
    echo "✅ .env file found"
fi

# Set correct permissions
sudo chown cryptobot:cryptobot /opt/crypto_bot/.env
sudo chmod 600 /opt/crypto_bot/.env

# =============================================================================
# 7. SYSTEMD SERVICE
# =============================================================================
echo "🔧 Installing systemd service..."
sudo cp /opt/crypto_bot/crypto-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable crypto-bot.service

# =============================================================================
# 8. LOG ROTATION
# =============================================================================
echo "📝 Setting up log rotation..."
sudo tee /etc/logrotate.d/crypto-bot > /dev/null << 'EOF'
/opt/crypto_bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 cryptobot cryptobot
    sharedscripts
    postrotate
        systemctl reload crypto-bot > /dev/null 2>&1 || true
    endscript
}
EOF

# =============================================================================
# 9. START BOT
# =============================================================================
echo "🚀 Starting crypto bot..."
sudo systemctl start crypto-bot.service

# Wait for startup
sleep 5

# Check status
if sudo systemctl is-active --quiet crypto-bot; then
    echo "✅ Bot started successfully!"
else
    echo "❌ Bot failed to start. Check logs:"
    echo "   sudo journalctl -u crypto-bot -f"
fi

# =============================================================================
# 10. POST-DEPLOYMENT CHECKS
# =============================================================================
echo ""
echo "📊 POST-DEPLOYMENT CHECKLIST"
echo "═══════════════════════════════════════"
echo "✅ Redis: $(redis-cli ping)"
echo "✅ Bot status: $(sudo systemctl is-active crypto-bot)"
echo "✅ Memory usage: $(ps -o rss= -p $(pgrep -f 'python.*bot.py') 2>/dev/null | awk '{printf "%.0fMB", $1/1024}' || echo 'N/A')"
echo ""
echo "📝 USEFUL COMMANDS:"
echo "   sudo systemctl status crypto-bot    # Check status"
echo "   sudo journalctl -u crypto-bot -f    # View logs"
echo "   sudo systemctl restart crypto-bot   # Restart bot"
echo "   sudo systemctl stop crypto-bot      # Stop bot"
echo "   htop                                # Monitor resources"
echo ""
echo "🔒 SECURITY REMINDER:"
echo "   • Rotate API keys yang sudah terekspor di chat"
echo "   • Pastikan .env permissions: 600"
echo "   • Jangan commit .env ke Git"
echo ""
echo "🎉 Deployment complete!"
