#!/usr/bin/env python3
"""
Setup Validation Script
=======================
Validates VPS deployment is complete and correct.

Usage:
    python scripts/validate_setup.py
    python scripts/validate_setup.py --verbose

Returns:
    0 = All checks passed
    1 = Some checks failed
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class SetupValidator:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.errors = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_total = 0

    def log(self, message, level='info'):
        """Log message with color."""
        colors = {
            'info': '\033[0;34mℹ️ ',
            'success': '\033[0;32m✅ ',
            'warning': '\033[1;33m⚠️  ',
            'error': '\033[0;31m❌ ',
            'header': '\033[1;36m'
        }
        reset = '\033[0m'

        prefix = colors.get(level, '')
        print(f"{prefix}{message}{reset}")

    def check(self, name):
        """Start a new check."""
        self.checks_total += 1
        if self.verbose:
            self.log(f"Checking: {name}", 'info')

    def pass_check(self, message):
        """Mark check as passed."""
        self.checks_passed += 1
        if self.verbose:
            self.log(message, 'success')

    def fail(self, message):
        """Mark check as failed."""
        self.errors.append(message)
        self.log(message, 'error')

    def warn(self, message):
        """Add warning."""
        self.warnings.append(message)
        self.log(message, 'warning')

    def run_command(self, cmd, shell=False):
        """Run shell command and return result."""
        try:
            if shell:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def validate(self):
        """Run all validation checks."""
        print("\n" + "="*60)
        print("Crypto Bot - Setup Validation")
        print("="*60 + "\n")

        # 1. System checks
        self.log("SYSTEM CHECKS", 'header')
        self.check("Ubuntu version")
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release') as f:
                content = f.read()
                if 'Ubuntu 22.04' in content or 'jammy' in content:
                    self.pass_check("Ubuntu 22.04 detected")
                else:
                    self.warn("Not Ubuntu 22.04, but may still work")
        else:
            self.fail("Cannot detect OS version")

        self.check("Python 3.10")
        success, stdout, _ = self.run_command(['python3.10', '--version'])
        if success and '3.10' in stdout:
            self.pass_check(f"Python {stdout.strip()}")
        else:
            self.fail("Python 3.10 not found")

        self.check("Hardware resources")
        try:
            import psutil
            cpu = psutil.cpu_count()
            ram = psutil.virtual_memory().total / (1024**3)
            disk = psutil.disk_usage('/').free / (1024**3)

            self.log(f"   CPU: {cpu} cores", 'info')
            self.log(f"   RAM: {ram:.1f} GB", 'info')
            self.log(f"   Disk Free: {disk:.1f} GB", 'info')

            if cpu < 2:
                self.fail("CPU < 2 cores (minimum 4 recommended)")
            elif cpu < 4:
                self.warn("CPU < 4 cores (4+ recommended)")

            if ram < 4:
                self.fail("RAM < 4 GB (minimum 8 recommended)")
            elif ram < 8:
                self.warn("RAM < 8 GB (8+ recommended)")

            self.pass_check("Hardware specs checked")
        except ImportError:
            self.warn("psutil not installed, skipping hardware check")

        # 2. User and permissions
        print("\n")
        self.log("USER & PERMISSIONS", 'header')

        self.check("Bot user exists")
        success, _, _ = self.run_command(['id', 'cryptobot'])
        if success:
            self.pass_check("User 'cryptobot' exists")
        else:
            self.fail("User 'cryptobot' not found - run deploy script")

        self.check("Bot directory")
        if os.path.exists('/opt/crypto-bot'):
            self.pass_check("Bot directory exists")
        else:
            self.fail("Bot directory /opt/crypto-bot not found")

        # 3. Dependencies
        print("\n")
        self.log("DEPENDENCIES", 'header')

        self.check("Redis service")
        success, _, _ = self.run_command(['systemctl', 'is-active', 'redis-server'])
        if success:
            self.pass_check("Redis is running")
        else:
            self.fail("Redis not running - start with: systemctl start redis-server")

        self.check("Python packages")
        packages = ['pandas', 'numpy', 'sklearn', 'telegram', 'redis', 'psutil']
        bot_dir = '/opt/crypto-bot'
        venv_python = f"{bot_dir}/venv/bin/python"

        if os.path.exists(venv_python):
            missing = []
            for pkg in packages:
                success, _, _ = self.run_command([venv_python, '-c', f'import {pkg}'], shell=False)
                if not success:
                    missing.append(pkg)

            if not missing:
                self.pass_check("All required packages installed")
            else:
                self.fail(f"Missing packages: {', '.join(missing)}")
        else:
            self.fail("Virtual environment not found")

        # 4. Configuration
        print("\n")
        self.log("CONFIGURATION", 'header')

        self.check("Environment file")
        env_file = '/opt/crypto-bot/.env'
        if os.path.exists(env_file):
            # Check permissions
            stat = os.stat(env_file)
            if stat.st_mode & 0o077:
                self.warn("⚠️  .env file has loose permissions (should be 600)")
            else:
                self.pass_check(".env file exists with correct permissions")

            # Check required vars
            with open(env_file) as f:
                content = f.read()
                if 'your_bot_token_here' in content or 'your_telegram_user_id' in content:
                    self.fail(".env file contains placeholder values - edit with real credentials!")
                else:
                    self.pass_check(".env file configured")
        else:
            self.fail(".env file not found - copy from .env.example")

        self.check("Trading mode")
        if os.path.exists(env_file):
            with open(env_file) as f:
                content = f.read()
                if 'DRY_RUN=True' in content:
                    self.pass_check("Trading mode: DRY RUN (safe)")
                elif 'DRY_RUN=False' in content:
                    self.warn("⚠️  Trading mode: REAL TRADING - ensure you're ready!")
                else:
                    self.warn("Cannot determine trading mode")

        # 5. Database
        print("\n")
        self.log("DATABASE", 'header')

        data_dir = '/opt/crypto-bot/data'
        self.check("Data directory")
        if os.path.exists(data_dir):
            self.pass_check("Data directory exists")

            # Check databases
            dbs = ['signals.db', 'trading.db', 'cache.db']
            for db in dbs:
                db_path = os.path.join(data_dir, db)
                if os.path.exists(db_path):
                    size = os.path.getsize(db_path) / (1024*1024)
                    self.log(f"   {db}: {size:.2f} MB", 'info')
        else:
            self.fail("Data directory not found")

        # 6. Services
        print("\n")
        self.log("SERVICES", 'header')

        self.check("Systemd service")
        if os.path.exists('/etc/systemd/system/crypto-bot.service'):
            self.pass_check("Service file exists")

            success, _, _ = self.run_command(['systemctl', 'is-enabled', 'crypto-bot'])
            if success:
                self.pass_check("Service enabled for auto-start")
            else:
                self.warn("Service not enabled")
        else:
            self.fail("Systemd service not found")

        self.check("Firewall (UFW)")
        success, stdout, _ = self.run_command(['ufw', 'status'], shell=False)
        if success and 'active' in stdout.lower():
            self.pass_check("UFW is active")
        else:
            self.warn("UFW not active - consider enabling for security")

        self.check("Fail2Ban")
        success, _, _ = self.run_command(['systemctl', 'is-active', 'fail2ban'])
        if success:
            self.pass_check("Fail2Ban is running")
        else:
            self.warn("Fail2Ban not running")

        # 7. Monitoring
        print("\n")
        self.log("MONITORING", 'header')

        self.check("Monitor script")
        if os.path.exists('/opt/crypto-bot/monitoring/monitor.py'):
            self.pass_check("Monitor script exists")
        else:
            self.fail("Monitor script not found")

        self.check("Cron jobs")
        success, stdout, _ = self.run_command(['crontab', '-u', 'cryptobot', '-l'])
        if success and 'monitor.py' in stdout:
            self.pass_check("Monitor cron job configured")
        else:
            self.warn("Monitor cron job not found")

        self.check("Log files")
        log_dir = '/var/log/crypto-bot'
        if os.path.exists(log_dir):
            self.pass_check("Log directory exists")
        else:
            self.warn("Log directory not found")

        # Summary
        print("\n" + "="*60)
        self.log("VALIDATION SUMMARY", 'header')
        print("="*60)

        print(f"\nChecks passed: {self.checks_passed}/{self.checks_total}")

        if self.warnings:
            print(f"\nWarnings ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"  ⚠️  {w}")

        if self.errors:
            print(f"\nErrors ({len(self.errors)}):")
            for e in self.errors:
                print(f"  ❌ {e}")

        if not self.errors and not self.warnings:
            print("\n🎉 All checks passed! Setup is ready.")
            return 0
        elif not self.errors:
            print("\n⚠️  Setup has warnings but should work.")
            return 0
        else:
            print(f"\n❌ Setup has {len(self.errors)} errors that need to be fixed.")
            print("\nFix commands:")
            print("  sudo ./deploy_biznet.sh  # Re-run deployment")
            print("  cryptobot status           # Check bot status")
            return 1

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate bot setup')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    args = parser.parse_args()

    validator = SetupValidator(verbose=args.verbose)
    return validator.validate()

if __name__ == '__main__':
    sys.exit(main())
