# 🚀 QUICK START GUIDE - Advanced Crypto Trading Bot

**Last Updated:** 2026-05-17  
**Mode:** DRY RUN (Safe Mode)  
**Difficulty:** Beginner-Friendly

---

## 📋 TABLE OF CONTENTS

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [First Run](#first-run)
5. [Basic Commands](#basic-commands)
6. [Testing AutoTrade](#testing-autotrade)
7. [Testing Hunters](#testing-hunters)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Next Steps](#next-steps)

---

## ✅ PREREQUISITES

### System Requirements
- **OS:** Ubuntu 20.04+ / WSL2 / Linux
- **Python:** 3.10 or higher
- **RAM:** 2 GB minimum, 4 GB recommended
- **Disk:** 1 GB free space
- **Network:** Stable internet connection

### Required Accounts
1. **Telegram Account** - For bot control
2. **Indodax Account** (Optional) - Only needed for real trading

### Knowledge Requirements
- ✅ Basic Linux command line
- ✅ Basic understanding of cryptocurrency trading
- ⚠️ NO programming knowledge required

---

## 📦 INSTALLATION

### Step 1: Navigate to Bot Directory
```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
```

### Step 2: Check Python Version
```bash
python3 --version
# Should show: Python 3.10.x or higher
```

If Python is not installed:
```bash
sudo apt update
sudo apt install python3 python3-pip -y
```

### Step 3: Install Dependencies
```bash
pip3 install -r requirements.txt
```

**Expected output:**
```
Successfully installed python-telegram-bot-20.x pandas-2.x numpy-1.x ...
```

### Step 4: Verify Installation
```bash
python3 -c "import telegram; print('✅ Telegram bot library OK')"
python3 -c "import pandas; print('✅ Pandas OK')"
python3 -c "import sklearn; print('✅ Scikit-learn OK')"
```

---

## ⚙️ CONFIGURATION

### Step 1: Copy Environment File
```bash
cp .env.example .env
```

### Step 2: Get Telegram Bot Token

1. Open Telegram
2. Search for `@BotFather`
3. Send: `/newbot`
4. Follow instructions to create bot
5. Copy the token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 3: Get Your Telegram User ID

1. Open Telegram
2. Search for `@userinfobot`
3. Send: `/start`
4. Copy your user ID (looks like: `123456789`)

### Step 4: Edit .env File
```bash
nano .env
```

**Minimal configuration (DRY RUN mode):**
```bash
# Telegram (REQUIRED)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_IDS=123456789

# Trading Mode (SAFE - DRY RUN)
AUTO_TRADE_DRY_RUN=true
AUTO_TRADING_ENABLED=false

# Initial Balance (Simulation)
INITIAL_BALANCE=10000000

# Trading Pairs (Start with 3-5 pairs)
WATCH_PAIRS=btcidr,ethidr,dogeidr

# Stop Loss & Take Profit
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=4.0
```

**Save and exit:** Press `Ctrl+X`, then `Y`, then `Enter`

### Step 5: Verify Configuration
```bash
python3 -c "
from core.config import Config
print(f'✅ Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...')
print(f'✅ Admin IDs: {Config.ADMIN_IDS}')
print(f'✅ DRY RUN: {Config.AUTO_TRADE_DRY_RUN}')
print(f'✅ Initial Balance: {Config.INITIAL_BALANCE:,.0f} IDR')
"
```

**Expected output:**
```
✅ Bot Token: 123456789:...
✅ Admin IDs: [123456789]
✅ DRY RUN: True
✅ Initial Balance: 10,000,000 IDR
```

---

## 🎬 FIRST RUN

### Step 1: Start Bot
```bash
python3 bot.py
```

**Expected output:**
```
🚀 Initializing Advanced Crypto Trading Bot...
✅ Database initialized
✅ ML Model V2 loaded
✅ Trading Engine initialized
✅ Signal Quality Engine initialized
✅ Redis State Manager initialized
✅ Bot initialized successfully!
📱 Starting Telegram bot with POLLING...
💡 Press Ctrl+C to stop bot
```

### Step 2: Test Bot in Telegram

1. Open Telegram
2. Search for your bot (name you gave to BotFather)
3. Send: `/start`

**Expected response:**
```
🤖 Advanced Crypto Trading Bot

Welcome! I'm your AI-powered trading assistant.

🧪 Mode: DRY RUN (Safe Mode)
💰 Balance: 10,000,000 IDR

Quick Actions:
• /help - Show all commands
• /menu - Main menu
• /watch btcidr - Add pair to watchlist
• /signal btcidr - Generate signal
```

### Step 3: Verify Bot is Working
```bash
# In Telegram, send:
/status

# Expected response:
✅ Bot Status

🤖 Status: ONLINE
🧪 Mode: DRY RUN
💰 Balance: 10,000,000 IDR
📊 Watchlist: 0 pairs
🔄 Auto-Trading: DISABLED
⏱️ Uptime: 2 minutes
```

---

## 📱 BASIC COMMANDS

### 1. Watchlist Management
```bash
# Add pairs to watchlist
/watch btcidr
/watch ethidr
/watch dogeidr

# View watchlist
/list

# Remove pair
/unwatch dogeidr

# Clear all
/clear_watchlist
```

### 2. Signal Generation
```bash
# Generate signal for single pair
/signal btcidr

# Generate signals for all watched pairs
/signals

# Filter signals
/signal_buy      # Only BUY signals
/signal_sell     # Only SELL signals
/signal_buysell  # Only actionable (BUY/SELL)
```

**Example Signal Output:**
```
📊 Signal for BTCIDR

🎯 Recommendation: BUY
💪 Confidence: 72%
⭐ Quality Score: 78/100

💰 Price: 450,000,000 IDR
📈 Support: 440,000,000 IDR
📉 Resistance: 470,000,000 IDR

📊 Technical Indicators:
• RSI: 45 (Neutral)
• MACD: Bullish crossover
• Bollinger: Near lower band

🤖 ML Prediction: BUY (72%)
🧠 AI Reasoning: Strong bullish momentum with volume confirmation

⚠️ Risk/Reward: 1:2.5 (Good)
```

### 3. Price Checking
```bash
# Get current price
/price btcidr

# Top volume pairs
/topvolume
```

### 4. Portfolio & Balance
```bash
# Check balance
/balance

# View portfolio
/portfolio

# View open positions
/position

# View trade history
/trades
```

---

## 🤖 TESTING AUTOTRADE (DRY RUN)

### Step 1: Add Pairs to Auto-Trade
```bash
# In Telegram:
/add_autotrade btcidr
/add_autotrade ethidr

# Verify
/list_autotrade

# Expected response:
📋 Auto-Trade Pairs:
• btcidr
• ethidr
```

### Step 2: Enable Auto-Trading
```bash
/start_trading

# Expected response:
✅ Auto-trading ENABLED

🧪 Mode: DRY RUN (Safe Mode)
💰 Balance: 10,000,000 IDR
📊 Auto-trade pairs: 2

⚠️ Note: All trades are simulated.
No real money will be used.
```

### Step 3: Monitor Auto-Trading
```bash
# Check status
/autotrade_status

# Expected response:
🤖 Auto-Trade Status

Status: 🟢 ENABLED
Mode: 🧪 DRY RUN

📊 Pairs: 2
• btcidr
• ethidr

💰 Balance: 10,000,000 IDR
📈 Open Positions: 0
📊 Today's Trades: 0
```

### Step 4: Wait for Signals

Bot will automatically:
1. Monitor prices every 15 seconds
2. Generate signals when conditions met
3. Execute trades (simulated)
4. Send notifications

**Example Auto-Trade Notification:**
```
🤖 AUTO-TRADE EXECUTED

🎯 Action: BUY
💎 Pair: BTCIDR
💰 Amount: 0.00222 BTC
💵 Price: 450,000,000 IDR
💸 Total: 1,000,000 IDR

📊 Signal:
• Confidence: 75%
• Quality: 82/100

🛡️ Risk Management:
• Stop Loss: 441,000,000 (-2.0%)
• Take Profit: 468,000,000 (+4.0%)

🧪 DRY RUN: This is a simulated trade
```

### Step 5: Monitor Positions
```bash
/position

# Expected response:
📊 Open Positions

💎 BTCIDR
Entry: 450,000,000 IDR
Current: 452,000,000 IDR
Amount: 0.00222 BTC
P&L: +0.44% (+20,000 IDR)

🛡️ Risk Management:
• SL: 441,000,000 (-2.0%)
• TP: 468,000,000 (+4.0%)
• Trailing: Active

⏱️ Holding: 15 minutes
```

### Step 6: Stop Auto-Trading
```bash
/stop_trading

# Expected response:
🛑 Auto-trading DISABLED

📊 Final Stats:
• Trades today: 3
• Win rate: 66.7% (2/3)
• P&L: +150,000 IDR (+1.5%)
```

---

## 🎯 TESTING HUNTERS

### Smart Hunter (Moderate Risk)

**Step 1: Start Smart Hunter**
```bash
/smarthunter on

# Expected response:
✅ Smart Hunter started

🧪 Mode: DRY RUN
🎯 Target: 3-5% profit
🛡️ Risk: Moderate
💰 Balance: 10,000,000 IDR
```

**Step 2: Monitor Smart Hunter**
```bash
/smarthunter_status

# Expected response:
🤖 Smart Hunter

Status: 🟢 JALAN
Mode: DRY RUN
Saldo kerja: 10,000,000 IDR
Posisi aktif: 1
Trade hari ini: 2
🟢 P&L hari ini: +320,000 IDR

Posisi terbuka:
• pippinidr entry 1,250 IDR, sisa 8,000 coins
```

**Step 3: Stop Smart Hunter**
```bash
/smarthunter off
```

---

### Ultra Hunter (Aggressive)

**Step 1: Start Ultra Hunter**
```bash
/ultrahunter on

# Expected response:
✅ Ultra Hunter started

⚠️ WARNING: Aggressive mode
🎯 Target: 5-10% profit
🛡️ Stop Loss: -3%
💰 Balance: 10,000,000 IDR
```

**Step 2: Monitor Ultra Hunter**
```bash
/ultrahunter

# Expected response:
🔥 Ultra Hunter

Status: 🟢 JALAN
Mode: DRY RUN
Risk Level: AGGRESSIVE
Posisi aktif: 1
Trade hari ini: 1
🟢 P&L hari ini: +850,000 IDR
```

---

## 📊 MONITORING

### Daily Monitoring Commands

```bash
# Morning routine (08:00)
/status          # Check bot status
/balance         # Check balance
/position        # Check open positions
/signals         # Generate fresh signals

# Midday check (12:00)
/autotrade_status  # Check auto-trade
/smarthunter_status  # Check Smart Hunter
/performance     # Check performance

# Evening review (20:00)
/trades          # Review today's trades
/performance     # Final performance
/metrics         # System metrics
```

### Performance Metrics

```bash
/performance

# Expected response:
📊 Trading Performance (Last 7 Days)

💰 P&L: +1,250,000 IDR (+12.5%)
📈 Win Rate: 75% (15/20 trades)
💵 Avg Profit: +83,333 IDR per trade
📉 Max Drawdown: -3.2%

🎯 Best Pair: pippinidr (+450,000 IDR)
📉 Worst Pair: dogeidr (-120,000 IDR)

⏱️ Avg Hold Time: 4.2 hours
🔄 Trade Frequency: 2.9 trades/day
```

### System Metrics

```bash
/metrics

# Expected response:
🖥️ System Metrics

💾 Memory: 450 MB / 2 GB (22%)
🔄 CPU: 15%
💿 Database: 65 MB
📊 Cache Hit Rate: 85%

🔔 Notifications: 45 sent today
⚡ Avg Response Time: 1.2s
🐛 Errors: 2 (non-critical)
```

---

## 🔧 TROUBLESHOOTING

### Problem 1: Bot Not Starting

**Symptom:** Error when running `python3 bot.py`

**Solution:**
```bash
# Check Python version
python3 --version  # Should be 3.10+

# Reinstall dependencies
pip3 install -r requirements.txt --force-reinstall

# Check .env file
cat .env | grep TELEGRAM_BOT_TOKEN
```

---

### Problem 2: No Signals Generated

**Symptom:** `/signal btcidr` returns "No data available"

**Solution:**
```bash
# Wait 5-10 minutes for data collection
# Bot needs to collect price history first

# Check if pair is valid
/price btcidr

# Try different pair
/signal ethidr
```

---

### Problem 3: Telegram Bot Not Responding

**Symptom:** Bot doesn't reply to commands

**Solution:**
```bash
# Check bot is running
ps aux | grep bot.py

# Check logs
tail -f bot.log

# Restart bot
# Press Ctrl+C to stop
python3 bot.py
```

---

### Problem 4: "Rate Limit" Error

**Symptom:** "⏳ Rate Limit" message in Telegram

**Solution:**
```bash
# Wait 60 seconds before trying again
# Rate limit: 5 commands per minute

# If you're admin, rate limit is bypassed
# Check your user ID is in ADMIN_IDS
```

---

### Problem 5: Database Locked

**Symptom:** "Database is locked" error

**Solution:**
```bash
# Stop bot
# Press Ctrl+C

# Remove lock files
rm -f data/trading.db-shm data/trading.db-wal

# Restart bot
python3 bot.py
```

---

## 🎓 NEXT STEPS

### Week 1: Learning Phase
- ✅ Use DRY RUN mode
- ✅ Test all basic commands
- ✅ Monitor signal quality
- ✅ Learn risk management features

### Week 2: Testing Phase
- ✅ Enable AutoTrade (DRY RUN)
- ✅ Test Smart Hunter
- ✅ Test Ultra Hunter
- ✅ Monitor performance metrics

### Week 3: Optimization Phase
- ✅ Adjust stop loss / take profit
- ✅ Fine-tune auto-trade pairs
- ✅ Test different strategies
- ✅ Review trade history

### Week 4: Decision Phase
- ✅ Review 3 weeks of data
- ✅ Calculate win rate & profitability
- ✅ Decide: Continue DRY RUN or go REAL
- ⚠️ If going REAL: Start with small capital (1-5 juta IDR)

---

## 📚 ADDITIONAL RESOURCES

### Documentation Files
1. `EXECUTIVE_SUMMARY.md` - Quick overview
2. `ANALISIS_KOMPREHENSIF_BOT.md` - Complete analysis
3. `TESTING_PLAN_AUTOTRADE_HUNTER.md` - Testing guide
4. `OPTIMIZATION_FIXES.md` - Fix recommendations
5. `COMMAND_REFERENCE.md` - All commands
6. `OPERATIONS_FLOW_ALGORITHMA.md` - How it works
7. `SYSTEM_MAP.md` - Architecture

### Telegram Commands Reference
```bash
# Quick reference
/help           # Show all commands
/menu           # Main menu
/cmd            # Command helper

# Full list
/help           # Complete command list
```

### Support & Community
- 📖 Read documentation files
- 🐛 Report bugs via GitHub issues
- 💬 Ask questions in Telegram group
- 📧 Contact developer

---

## ⚠️ IMPORTANT REMINDERS

### Safety First
- ✅ **ALWAYS use DRY RUN mode first**
- ✅ **Test for at least 2-4 weeks**
- ✅ **Start with small capital**
- ✅ **Never invest more than you can afford to lose**

### Risk Management
- ✅ **Set stop loss** (default: 2%)
- ✅ **Set take profit** (default: 4%)
- ✅ **Limit daily trades** (default: 10)
- ✅ **Monitor positions daily**

### Best Practices
- ✅ **Review trades daily**
- ✅ **Adjust strategy based on results**
- ✅ **Keep learning**
- ✅ **Stay disciplined**

---

## 🎯 SUCCESS CHECKLIST

### Before Real Trading
- [ ] Used DRY RUN for 2-4 weeks
- [ ] Win rate >= 60%
- [ ] Understand all features
- [ ] Read all documentation
- [ ] Fixed critical issues (if applicable)
- [ ] Tested with small capital
- [ ] Have emergency stop plan
- [ ] Comfortable with risk

### Daily Checklist
- [ ] Check bot status
- [ ] Review open positions
- [ ] Monitor performance
- [ ] Adjust if needed
- [ ] Review trade history

---

## 🚀 YOU'RE READY!

Congratulations! You now have everything you need to start using the Advanced Crypto Trading Bot safely.

**Remember:**
- 🧪 Start with DRY RUN mode
- 📊 Monitor signal quality
- 📈 Learn from results
- ⚠️ Manage risk carefully

**Good luck with your trading journey! 🎉**

---

**Last Updated:** 2026-05-17  
**Version:** 1.0  
**Status:** ✅ READY TO USE

---

*This guide is designed for beginners. Follow each step carefully and don't rush into real trading. Safety first!*
