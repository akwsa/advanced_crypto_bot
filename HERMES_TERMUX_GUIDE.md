# 📱 Hermes Agent Setup for Termux - Bot Management Guide

## 🎯 Why Hermes Agent for Termux?

✅ **Lightweight** - Only ~50MB memory usage (vs 500MB for Pi Agent)
✅ **Battery Friendly** - Minimal CPU usage
✅ **Python-based** - No Node.js compilation needed
✅ **CLI-friendly** - Perfect for terminal/SSH management
✅ **Fast** - 10MB download vs 200MB for Pi Agent

## 📋 Prerequisites

### Android/Termux Requirements:
- Android 7.0+ (API 24+)
- Termux app (from F-Droid, NOT Play Store)
- Storage permission granted
- Minimum 1GB free space
- Internet connection

## 🔧 Installation Steps

### Step 1: Install Termux

```bash
# Download Termux from F-Droid:
# https://f-droid.org/en/packages/com.termux/

# Or use APK from:
# https://github.com/termux/termux-app/releases
```

### Step 2: Update Termux Packages

```bash
# Open Termux, then run:
pkg update && pkg upgrade -y
```

### Step 3: Install Python & Dependencies

```bash
# Install Python
pkg install python -y

# Install essential tools
pkg install git openssh rsync nano -y

# Verify Python installation
python --version
# Should show: Python 3.11.x or higher
```

### Step 4: Install Hermes Agent

**Method A: From PyPI (Recommended)**
```bash
pip install hermes-agent
```

**Method B: From Source (if PyPI unavailable)**
```bash
git clone https://github.com/yourusername/hermes-agent.git
cd hermes-agent
pip install -e .
```

### Step 5: Configure Hermes

```bash
# Create config directory
mkdir -p ~/.hermes

# Create config file
nano ~/.hermes/config.yaml
```

**Paste this configuration:**
```yaml
# Hermes Agent Configuration
agent:
  name: "bot-manager"
  workdir: "/data/data/com.termux/files/home/crypto-bot"
  
# VPS Connection (for remote bot management)
vps:
  host: "YOUR_VPS_IP"
  port: 22
  user: "root"
  key_path: "~/.ssh/id_rsa"
  
# Bot Configuration
bot:
  name: "crypto-bot"
  service: "crypto-bot.service"
  log_path: "/var/log/crypto-bot.log"
  
# Monitoring
monitoring:
  check_interval: 60  # seconds
  alert_threshold: 5   # consecutive failures before alert
  
# Notification (Telegram)
telegram:
  bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
  chat_id: "YOUR_TELEGRAM_CHAT_ID"
```

### Step 6: Setup SSH Keys (for VPS access)

```bash
# Generate SSH key
ssh-keygen -t rsa -b 4096 -C "termux@android"

# Press Enter for all prompts (default settings)

# Copy public key to VPS
ssh-copy-id root@YOUR_VPS_IP

# Test SSH connection
ssh root@YOUR_VPS_IP "echo Connection successful!"
```

## 🎮 Basic Usage

### Bot Management Commands

```bash
# Deploy bot to VPS
hermes deploy --target vps --source ./crypto-bot

# Start bot
hermes start crypto-bot

# Stop bot
hermes stop crypto-bot

# Restart bot
hermes restart crypto-bot

# Check status
hermes status crypto-bot

# View logs (real-time)
hermes logs crypto-bot --follow

# View last 100 lines
hermes logs crypto-bot --lines 100
```

### Monitoring Commands

```bash
# Start monitoring (checks every 60s)
hermes monitor crypto-bot

# Health check
hermes health crypto-bot

# Resource usage
hermes stats crypto-bot
```

### Maintenance Commands

```bash
# Update bot code
hermes update crypto-bot --git-pull

# Backup database
hermes backup crypto-bot

# Restore from backup
hermes restore crypto-bot --backup-id 20260518_120000

# Clean old logs
hermes clean crypto-bot --days 7
```

## 🔄 Automated Bot Management

### Create Management Script

```bash
# Create script directory
mkdir -p ~/scripts

# Create bot manager script
nano ~/scripts/bot-manager.sh
```

**Paste this script:**
```bash
#!/data/data/com.termux/files/usr/bin/bash
# Bot Management Script for Hermes

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Functions
check_status() {
    echo -e "${YELLOW}Checking bot status...${NC}"
    hermes status crypto-bot
}

view_logs() {
    echo -e "${YELLOW}Viewing logs...${NC}"
    hermes logs crypto-bot --lines 50
}

restart_bot() {
    echo -e "${YELLOW}Restarting bot...${NC}"
    hermes restart crypto-bot
    sleep 3
    check_status
}

update_bot() {
    echo -e "${YELLOW}Updating bot...${NC}"
    hermes stop crypto-bot
    hermes update crypto-bot --git-pull
    hermes start crypto-bot
    echo -e "${GREEN}Update complete!${NC}"
}

backup_db() {
    echo -e "${YELLOW}Backing up database...${NC}"
    hermes backup crypto-bot
    echo -e "${GREEN}Backup complete!${NC}"
}

# Menu
echo "╔══════════════════════════════════════╗"
echo "║     Crypto Bot Manager (Hermes)     ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "1) Check Status"
echo "2) View Logs"
echo "3) Restart Bot"
echo "4) Update Bot"
echo "5) Backup Database"
echo "6) Exit"
echo ""
read -p "Choose option [1-6]: " option

case $option in
    1) check_status ;;
    2) view_logs ;;
    3) restart_bot ;;
    4) update_bot ;;
    5) backup_db ;;
    6) echo "Goodbye!"; exit 0 ;;
    *) echo "Invalid option"; exit 1 ;;
esac
```

```bash
# Make executable
chmod +x ~/scripts/bot-manager.sh

# Create alias
echo "alias bot-mgr='bash ~/scripts/bot-manager.sh'" >> ~/.bashrc
source ~/.bashrc

# Run with:
bot-mgr
```

## 📊 Monitoring Dashboard (Terminal UI)

### Create Simple Dashboard

```bash
# Install dependencies
pip install rich psutil

# Create dashboard script
nano ~/scripts/bot-dashboard.py
```

**Paste this Python script:**
```python
#!/data/data/com.termux/files/usr/bin/python3
"""Simple Bot Monitoring Dashboard for Termux"""

import subprocess
import time
from rich.console import Console
from rich.table import Table
from rich.live import Live
from datetime import datetime

console = Console()

def get_bot_status():
    """Check bot status via Hermes"""
    try:
        result = subprocess.run(
            ['hermes', 'status', 'crypto-bot'],
            capture_output=True, text=True, timeout=5
        )
        return "Running" if result.returncode == 0 else "Stopped"
    except:
        return "Unknown"

def get_vps_stats():
    """Get VPS resource stats"""
    try:
        result = subprocess.run(
            ['ssh', 'root@YOUR_VPS_IP', 'free -h && df -h / | tail -1'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except:
        return "Unable to fetch"

def create_dashboard():
    """Create dashboard table"""
    table = Table(title="🤖 Crypto Bot Dashboard", show_header=True)
    
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    
    # Bot status
    status = get_bot_status()
    status_emoji = "✅" if status == "Running" else "❌"
    table.add_row("Bot Status", f"{status_emoji} {status}")
    
    # Uptime
    table.add_row("Last Check", datetime.now().strftime("%H:%M:%S"))
    
    # VPS Stats (if available)
    # table.add_row("VPS Stats", get_vps_stats())
    
    return table

def main():
    """Main dashboard loop"""
    console.print("[bold cyan]Starting Bot Dashboard...[/bold cyan]")
    console.print("[yellow]Press Ctrl+C to exit[/yellow]\n")
    
    with Live(create_dashboard(), refresh_per_second=1) as live:
        try:
            while True:
                time.sleep(5)  # Update every 5 seconds
                live.update(create_dashboard())
        except KeyboardInterrupt:
            console.print("\n[yellow]Dashboard stopped.[/yellow]")

if __name__ == "__main__":
    main()
```

```bash
# Make executable
chmod +x ~/scripts/bot-dashboard.py

# Run dashboard
python ~/scripts/bot-dashboard.py
```

## 🔔 Telegram Notifications

### Setup Telegram Alerts

```bash
# Create notification script
nano ~/scripts/bot-alert.sh
```

**Paste this:**
```bash
#!/data/data/com.termux/files/usr/bin/bash
# Telegram Alert Script

BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID="YOUR_TELEGRAM_CHAT_ID"

send_telegram() {
    MESSAGE=$1
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${CHAT_ID}" \
        -d text="${MESSAGE}" \
        -d parse_mode="HTML"
}

# Check bot status
if ! hermes status crypto-bot > /dev/null 2>&1; then
    send_telegram "⚠️ <b>Bot Alert</b>: Crypto bot is DOWN!"
    
    # Auto-restart
    hermes start crypto-bot
    sleep 3
    
    if hermes status crypto-bot > /dev/null 2>&1; then
        send_telegram "✅ <b>Bot Alert</b>: Crypto bot restarted successfully!"
    else
        send_telegram "❌ <b>Bot Alert</b>: Failed to restart bot! Manual intervention needed."
    fi
fi
```

```bash
# Make executable
chmod +x ~/scripts/bot-alert.sh

# Add to cron (check every 5 minutes)
crontab -e
```

Add this line:
```
*/5 * * * * /data/data/com.termux/files/home/scripts/bot-alert.sh
```

## 🔧 Advanced Usage

### Multi-Bot Management

```bash
# Deploy multiple bots
hermes deploy bot1 --target vps1
hermes deploy bot2 --target vps2

# Check all bots
hermes status --all

# Restart all
hermes restart --all
```

### Scheduled Tasks

```bash
# Daily backup at 2 AM
crontab -e
```

Add:
```
0 2 * * * hermes backup crypto-bot
0 3 * * * hermes clean crypto-bot --days 7
```

### Remote Execution

```bash
# Execute command on VPS
hermes exec crypto-bot "systemctl status crypto-bot"

# Get bot logs
hermes exec crypto-bot "tail -f /var/log/crypto-bot.log"

# Database backup
hermes exec crypto-bot "bash /opt/crypto-bot/backup.sh"
```

## 🐛 Troubleshooting

### Hermes not found
```bash
# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### SSH Connection Failed
```bash
# Test SSH
ssh -v root@YOUR_VPS_IP

# Check SSH key
ls -la ~/.ssh/id_rsa
```

### Bot Status Unknown
```bash
# Check Hermes config
cat ~/.hermes/config.yaml

# Test connection
hermes health crypto-bot --verbose
```

## 📱 Termux Widget Integration (Optional)

### Create Home Screen Widget

```bash
# Install Termux:Widget from F-Droid

# Create widget script
mkdir -p ~/.shortcuts

# Create bot status widget
nano ~/.shortcuts/bot-status.sh
```

```bash
#!/data/data/com.termux/files/usr/bin/bash
hermes status crypto-bot && \
echo "✅ Bot Running" || \
echo "❌ Bot Stopped"
```

```bash
chmod +x ~/.shortcuts/bot-status.sh

# Long-press on home screen → Widgets → Termux:Widget → bot-status
```

## 🎉 Summary

**Hermes Agent di Termux memberikan:**
- ✅ Lightweight bot management (50MB memory)
- ✅ Remote VPS control via SSH
- ✅ Automated monitoring & alerts
- ✅ Simple CLI commands
- ✅ Battery-efficient
- ✅ Perfect untuk mobile management

**Quick Commands:**
```bash
hermes status crypto-bot    # Check status
hermes logs crypto-bot -f   # View logs
hermes restart crypto-bot   # Restart bot
bot-mgr                     # Interactive menu
```

**Next Steps:**
1. Configure ~/.hermes/config.yaml
2. Setup SSH keys for VPS access
3. Test basic commands
4. Setup monitoring & alerts
5. Add shortcuts/widgets

---

Made with ❤️ for Termux Users
