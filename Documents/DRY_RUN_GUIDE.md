# 🧪 Dry Run Trading Mode - User Guide

## Overview
The **Dry Run Mode** allows you to test the bot's auto-trading strategy **without using real money**. It simulates all trades while tracking virtual P&L, making it perfect for learning and strategy validation.

## Quick Start

### 1. Enable Dry Run Mode
```
/autotrade dryrun
```

This will:
- ✅ Enable auto-trading in **simulation mode**
- ✅ Generate real trading signals
- ✅ Simulate BUY/SELL orders (no real execution)
- ✅ Track virtual P&L in the database
- ❌ NOT send any orders to Indodax
- ❌ NOT use any real money

### 2. Monitor Status
```
/autotrade_status
```

This shows:
- Current mode (🧪 Dry Run or 🔴 Real)
- Today's simulated trades
- Virtual P&L performance
- Open simulated positions

### 3. Switch Modes

**To Real Trading:**
```
/autotrade real
```
⚠️ WARNING: This uses REAL money!

**To Disable:**
```
/autotrade off
```

**Toggle (keeps current mode):**
```
/autotrade
```

## How It Works

### Real Trade Flow:
```
Signal Generated → API Order → Real Execution → Real P&L
```

### Dry Run Trade Flow:
```
Signal Generated → Simulated Order → Virtual P&L (No API call)
```

### What Gets Simulated:
- ✅ Signal generation (TA + ML analysis)
- ✅ Entry price tracking
- ✅ Position size calculation
- ✅ Stop Loss & Take Profit levels
- ✅ Trade recording in database
- ✅ P&L tracking (virtual)
- ✅ Telegram notifications

### What Does NOT Happen:
- ❌ No API calls to Indodax
- ❌ No real orders placed
- ❌ No real money used
- ❌ No actual balance changes

## Configuration

### In `.env` file:
```env
# Default to dry run mode for safety
AUTO_TRADE_DRY_RUN=true

# Set to false when ready for real trading
# AUTO_TRADE_DRY_RUN=false
```

### In `config.py`:
```python
AUTO_TRADE_DRY_RUN = os.getenv('AUTO_TRADE_DRY_RUN', 'true').lower() == 'true'
```

## Use Cases

### 1. **Learning** 📚
- Understand how the bot makes decisions
- See signal generation in action
- Learn about risk management (SL/TP)

### 2. **Strategy Testing** 🧪
- Validate ML model accuracy
- Test risk parameters (SL%, TP%)
- Analyze win rate before real trading

### 3. **Risk-Free Monitoring** 👀
- Watch what trades WOULD happen
- Track potential profits/losses
- Build confidence in the system

### 4. **Debug & Optimize** 🔧
- Identify false signals
- Fine-tune confidence thresholds
- Adjust position sizing

## Telegram Notifications

### Dry Run Trade Notification:
```
🧪 DRY RUN: SIMULULATED TRADE 🧪

📊 Pair: `BTC/IDR`
💡 Action: BUY (SIMULATED)
💰 Price: `1,650,000,000` IDR
📦 Amount: `0.0015`
💵 Total: `2,475,000` IDR

🛡️ Stop Loss: `1,617,000,000` IDR (-2%)
🎯 Take Profit: `1,732,500,000` IDR (+5%)

🤖 Confidence: 78%
🆔 Trade ID: `123`
📋 Order ID: `DRY-456789`

⚠️ This is a SIMULATION
• No real money used
• No actual order placed
• For testing only
```

### Real Trade Notification:
```
🚨 AUTO-TRADE EXECUTED 🟢

📊 Pair: `BTC/IDR`
💡 Action: BUY
💰 Price: `1,650,000,000` IDR
📦 Amount: `0.0015`
💵 Total: `2,475,000` IDR

🛡️ Stop Loss: `1,617,000,000` IDR (-2%)
🎯 Take Profit: `1,732,500,000` IDR (+5%)

🤖 Confidence: 78%
🆔 Trade ID: `124`
📋 Order ID: `987654`
```

## Status Dashboard

### Dry Run Mode Active:
```
🤖 AUTO-TRADING STATUS

📊 Status: 🟢 ACTIVE

🧪 Mode: DRY RUN (Simulation)
• ⚠️ NO real money being used
• ✅ All trades are simulated for testing

📈 Today's Activity (2026-04-04):
• Total Auto Trades: 5
  - 🧪 Dry Run: 5
• Wins: 3 | Losses: 2
• P&L: `+125,000` IDR

📋 Recent Auto-Trades:
🧪 ✅ BUY BTC/IDR
   P&L: +75,000 IDR
🧪 ❌ BUY ETH/IDR
   P&L: -30,000 IDR

💡 Commands:
• /autotrade dryrun - Enable simulation mode
• /autotrade real - Enable real trading
• /autotrade off - Disable auto-trading
```

## Safety Tips

### ✅ Recommended Workflow:
1. **Start with Dry Run** (minimum 1-2 weeks)
2. **Analyze Results** (check win rate, P&L)
3. **Adjust Parameters** if needed
4. **Switch to Real** only when confident
5. **Start Small** even in real mode

### ⚠️ Important Notes:
- Dry Run uses **simulated order IDs** (format: `DRY-XXXXXX`)
- Database trades are marked with `[DRY RUN]` in notes
- Switching to Real mode does NOT affect dry run history
- You can have both dry run and real trades in database

## Trading Parameters

### Current Settings (from `.env`):
```env
STOP_LOSS_PCT=2.0           # Cut loss at -2%
TAKE_PROFIT_PCT=4.0         # Take profit at +4%
MIN_TRADE_AMOUNT=100000     # Minimum: 100k IDR
MAX_TRADE_AMOUNT=5000000    # Maximum: 5M IDR
AUTO_TRADE_DRY_RUN=true     # Simulation mode
```

### Scan Interval Configuration

You can adjust how frequently the bot scans for trading signals using `/set_interval`:

```bash
/set_interval 1      → Fast (scalping, check every 1 minute)
/set_interval 2      → Medium-fast
/set_interval 3      → Balanced (recommended)
/set_interval 5      → Conservative (default)
```

**Important:**
- Lower interval = more checks, but may generate false signals
- Higher interval = more accurate signals, but may miss entries
- Minimum: 1 minute | Maximum: 30 minutes
- Can be changed anytime via `/set_interval` without restarting bot

### Risk Management:
- Max position size: 25% of balance
- Max daily trades: 10
- Daily loss limit: 5%
- Min risk-reward ratio: 2:1
- ML confidence threshold: 65%

## Troubleshooting

### Bot not generating dry run trades?
1. Check `/autotrade_status` - ensure mode is DRY RUN
2. Make sure you have pairs in watchlist (`/watch`)
3. Wait for data collection (need 60+ candles)
4. Check logs for errors

### Want to see more frequent scans?
- Bot scans every 5 minutes per pair (default)
- Use `/set_interval <minutes>` to change scan frequency:
  - `/set_interval 1` → Check every minute (fast)
  - `/set_interval 3` → Balanced (recommended)
- Add more pairs to watchlist for more opportunities
- Use `/signal <PAIR>` for manual analysis

### Switched to Real but still see DRY RUN?
- Restart bot after changing `AUTO_TRADE_DRY_RUN` in `.env`
- Or use `/autotrade real` command to override

## Next Steps

1. **Enable Dry Run**: `/autotrade dryrun`
2. **Add Pairs**: `/watch BTC/IDR`
3. **Wait & Observe**: Bot will scan every 5 min
4. **Check Results**: `/autotrade_status`
5. **Analyze**: Review virtual P&L after 1-2 weeks
6. **Decide**: Switch to real or keep simulating

---

**Remember**: Dry Run is your safety net. Use it wisely before risking real capital! 🛡️
