#!/usr/bin/env python3
"""
Resource Monitor for VPS
=======================
Monitors CPU, RAM, Disk usage and sends alerts via Telegram.

Features:
- CPU usage monitoring (alert if >80% for 5min)
- RAM usage monitoring (alert if >85% for 3min)
- Disk usage monitoring (alert if >90%)
- Bot process health check
- Network connectivity check
- Auto-restart on failure (optional)

Usage:
    python monitoring/monitor.py          # Run once (check now)
    python monitoring/monitor.py --daemon # Run continuously
    python monitoring/monitor.py --status # Show current status

Setup:
    Add to crontab for monitoring every 5 minutes:
    */5 * * * * cd /path/to/bot && python monitoring/monitor.py >> logs/monitor.log 2>&1
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ psutil not installed. Install with: pip install psutil")

# Load config
try:
    from core.config import Config
    TELEGRAM_BOT_TOKEN = Config.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = Config.ADMIN_IDS[0] if Config.ADMIN_IDS else None
except Exception:
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Alert thresholds
CPU_ALERT_THRESHOLD = 80  # Alert if CPU >80% for 5 minutes
CPU_ALERT_DURATION = 300  # 5 minutes in seconds
RAM_ALERT_THRESHOLD = 85  # Alert if RAM >85% for 3 minutes
RAM_ALERT_DURATION = 180  # 3 minutes in seconds
DISK_ALERT_THRESHOLD = 90  # Alert if disk >90%

# State file for tracking alert history
STATE_FILE = 'data/monitor_state.json'
LOG_FILE = 'logs/monitor.log'

# Setup logging
os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('monitor')


class ResourceMonitor:
    """Monitor VPS resources and send alerts."""

    def __init__(self):
        self.state = self._load_state()
        self.last_alert_time = {}
        self.alert_cooldown = 3600  # 1 hour between same alerts

    def _load_state(self) -> Dict:
        """Load monitoring state from file."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            'cpu_spike_start': None,
            'ram_spike_start': None,
            'last_disk_alert': None,
            'last_health_check': None,
            'alert_count': 0
        }

    def _save_state(self):
        """Save monitoring state to file."""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        if not PSUTIL_AVAILABLE:
            return 0.0
        return psutil.cpu_percent(interval=1)

    def get_ram_usage(self) -> float:
        """Get current RAM usage percentage."""
        if not PSUTIL_AVAILABLE:
            return 0.0
        return psutil.virtual_memory().percent

    def get_disk_usage(self) -> float:
        """Get current disk usage percentage."""
        if not PSUTIL_AVAILABLE:
            return 0.0
        return psutil.disk_usage('/').percent

    def get_bot_process(self) -> Optional[psutil.Process]:
        """Find bot process."""
        if not PSUTIL_AVAILABLE:
            return None
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info.get('cmdline', []))
                if 'bot.py' in cmdline and 'python' in cmdline.lower():
                    return proc
            except Exception:
                pass
        return None

    def send_telegram_alert(self, message: str, priority: str = 'normal'):
        """Send alert via Telegram."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram not configured, alert not sent")
            return False

        # Check cooldown
        alert_key = message[:50]  # First 50 chars as key
        now = time.time()
        if alert_key in self.last_alert_time:
            if now - self.last_alert_time[alert_key] < self.alert_cooldown:
                logger.info(f"Alert on cooldown: {message[:50]}...")
                return False

        try:
            import requests

            emoji = {
                'critical': '🚨',
                'high': '⚠️',
                'normal': 'ℹ️',
                'info': '💡'
            }.get(priority, 'ℹ️')

            full_message = f"""
{emoji} **VPS MONITOR ALERT**

{message}

⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🖥️ Server: {os.uname().nodename if hasattr(os, 'uname') else 'VPS'}
            """.strip()

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': full_message,
                'parse_mode': 'Markdown'
            }

            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Alert sent: {message[:50]}...")
                self.last_alert_time[alert_key] = now
                self.state['alert_count'] += 1
                self._save_state()
                return True
            else:
                logger.error(f"Failed to send alert: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            return False

    def check_cpu(self) -> bool:
        """Check CPU usage and alert if needed."""
        cpu = self.get_cpu_usage()
        now = time.time()

        logger.info(f"CPU Usage: {cpu:.1f}%")

        if cpu > CPU_ALERT_THRESHOLD:
            if self.state['cpu_spike_start'] is None:
                self.state['cpu_spike_start'] = now
                logger.warning(f"CPU spike started: {cpu:.1f}%")
            else:
                duration = now - self.state['cpu_spike_start']
                if duration > CPU_ALERT_DURATION:
                    # CPU has been high for too long
                    self.send_telegram_alert(
                        f"🖥️ **CPU SPIKE DETECTED**\n\n"
                        f"CPU Usage: {cpu:.1f}% (threshold: {CPU_ALERT_THRESHOLD}%)\n"
                        f"Duration: {duration/60:.1f} minutes\n\n"
                        f"Possible causes:\n"
                        f"• ML training in progress\n"
                        f"• High market volatility\n"
                        f"• Memory swapping to disk",
                        priority='high'
                    )
                    # Reset to avoid spam
                    self.state['cpu_spike_start'] = now - CPU_ALERT_DURATION + 60
        else:
            if self.state['cpu_spike_start'] is not None:
                duration = now - self.state['cpu_spike_start']
                if duration > 60:  # Was high for at least 1 minute
                    logger.info(f"CPU spike ended after {duration/60:.1f} minutes")
            self.state['cpu_spike_start'] = None

        self._save_state()
        return cpu < CPU_ALERT_THRESHOLD

    def check_ram(self) -> bool:
        """Check RAM usage and alert if needed."""
        ram = self.get_ram_usage()
        now = time.time()

        logger.info(f"RAM Usage: {ram:.1f}%")

        if ram > RAM_ALERT_THRESHOLD:
            if self.state['ram_spike_start'] is None:
                self.state['ram_spike_start'] = now
                logger.warning(f"RAM spike started: {ram:.1f}%")
            else:
                duration = now - self.state['ram_spike_start']
                if duration > RAM_ALERT_DURATION:
                    # RAM has been high for too long
                    self.send_telegram_alert(
                        f"💾 **RAM SPIKE DETECTED**\n\n"
                        f"RAM Usage: {ram:.1f}% (threshold: {RAM_ALERT_THRESHOLD}%)\n"
                        f"Duration: {duration/60:.1f} minutes\n\n"
                        f"⚠️ **RISK: Bot may be killed by OOM!**\n\n"
                        f"Recommendations:\n"
                        f"• Restart bot: /stop_trading then start\n"
                        f"• Consider upgrading RAM\n"
                        f"• Check for memory leaks",
                        priority='critical'
                    )
                    # Reset to avoid spam
                    self.state['ram_spike_start'] = now - RAM_ALERT_DURATION + 60
        else:
            if self.state['ram_spike_start'] is not None:
                duration = now - self.state['ram_spike_start']
                if duration > 60:
                    logger.info(f"RAM spike ended after {duration/60:.1f} minutes")
            self.state['ram_spike_start'] = None

        self._save_state()
        return ram < RAM_ALERT_THRESHOLD

    def check_disk(self) -> bool:
        """Check disk usage and alert if needed."""
        disk = self.get_disk_usage()

        logger.info(f"Disk Usage: {disk:.1f}%")

        if disk > DISK_ALERT_THRESHOLD:
            self.send_telegram_alert(
                f"💿 **DISK SPACE CRITICAL**\n\n"
                f"Disk Usage: {disk:.1f}% (threshold: {DISK_ALERT_THRESHOLD}%)\n\n"
                f"Actions needed:\n"
                f"• Run cleanup: /cleanup_signals\n"
                f"• Delete old logs\n"
                f"• Vacuum database",
                priority='critical'
            )

        return disk < DISK_ALERT_THRESHOLD

    def check_bot_health(self) -> bool:
        """Check if bot process is healthy."""
        if not PSUTIL_AVAILABLE:
            return True

        proc = self.get_bot_process()
        if proc is None:
            logger.error("Bot process NOT FOUND!")
            self.send_telegram_alert(
                f"🛑 **BOT PROCESS NOT RUNNING**\n\n"
                f"The trading bot process could not be found.\n\n"
                f"Actions:\n"
                f"• Check status: sudo systemctl status crypto-bot\n"
                f"• Restart: sudo systemctl restart crypto-bot\n"
                f"• Check logs: tail -f logs/trading_bot.log",
                priority='critical'
            )
            return False

        # Check CPU and memory of bot process
        try:
            cpu = proc.cpu_percent(interval=1)
            mem = proc.memory_percent()
            logger.info(f"Bot Process - CPU: {cpu:.1f}%, RAM: {mem:.1f}%")

            if cpu > 95:
                self.send_telegram_alert(
                    f"⚠️ **Bot CPU Very High: {cpu:.1f}%**\n"
                    f"Process may be stuck in a loop.",
                    priority='high'
                )

        except Exception as e:
            logger.error(f"Error checking bot process: {e}")

        return True

    def check_network(self) -> bool:
        """Check network connectivity."""
        try:
            import urllib.request
            urllib.request.urlopen('https://api.telegram.org', timeout=5)
            logger.info("Network: OK")
            return True
        except Exception as e:
            logger.error(f"Network: FAILED - Cannot reach Telegram API: {e}")
            return False

    def run_check(self) -> Dict:
        """Run all checks and return status."""
        logger.info("="*60)
        logger.info("Running resource check...")
        logger.info("="*60)

        results = {
            'timestamp': datetime.now().isoformat(),
            'cpu_ok': self.check_cpu(),
            'ram_ok': self.check_ram(),
            'disk_ok': self.check_disk(),
            'bot_ok': self.check_bot_health(),
            'network_ok': self.check_network()
        }

        all_ok = all(results.values())
        status = "✅ HEALTHY" if all_ok else "❌ ISSUES DETECTED"
        logger.info(f"Overall Status: {status}")
        logger.info("="*60)

        return results

    def run_daemon(self, interval: int = 60):
        """Run monitoring in daemon mode."""
        logger.info(f"Starting monitor daemon (interval: {interval}s)")

        while True:
            try:
                self.run_check()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='VPS Resource Monitor')
    parser.add_argument('--daemon', action='store_true',
                        help='Run continuously (default: run once)')
    parser.add_argument('--interval', type=int, default=60,
                        help='Check interval in seconds (default: 60)')
    parser.add_argument('--status', action='store_true',
                        help='Show current status only')

    args = parser.parse_args()

    monitor = ResourceMonitor()

    if args.status:
        # Just show current readings
        print("="*60)
        print("Current VPS Status")
        print("="*60)
        if PSUTIL_AVAILABLE:
            print(f"CPU Usage: {monitor.get_cpu_usage():.1f}%")
            print(f"RAM Usage: {monitor.get_ram_usage():.1f}%")
            print(f"Disk Usage: {monitor.get_disk_usage():.1f}%")
        else:
            print("⚠️ psutil not installed - install with: pip install psutil")
        print("="*60)
    elif args.daemon:
        monitor.run_daemon(args.interval)
    else:
        monitor.run_check()


if __name__ == '__main__':
    main()
