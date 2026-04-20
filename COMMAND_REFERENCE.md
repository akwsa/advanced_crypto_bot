# 📋 COMPLETE COMMAND REFERENCE
# Advanced Crypto Bot - Indodax Trading Bot
# ============================================================

## 🚀 QUICK START

```bash
/start          - Start bot
/help          - Show this help
/cmd           - List all command categories
/signal BTCIDR   - Get trading signal
```

---

## 📂 COMMAND CATEGORIES

### 1. WATCHLIST & MONITORING
```
/watch <PAIR>              - Add pair(s) to watchlist
/watch <P1>, <P2>        - Add multiple pairs
/unwatch <PAIR>            - Remove from watchlist
/list                    - View your watchlist
/price <PAIR>             - Quick price check
/monitor <PAIR>           - Set price monitoring
/clear_watchlist          - Clear all watchlist (admin)
```

### 2. TRADING SIGNALS
```
/signal <PAIR>           - Get complete trading analysis
/signals                 - Signals for all watchlist pairs
/scan                   - Market scanner
/topvolume              - Top volume pairs
/notifications          - Set notification preferences
```

### 3. AUTO-TRADING (Admin Only)
```
/autotrade               - Toggle auto-trading (keeps current mode)
/autotrade dryrun        - Enable SIMULATION mode (RECOMMENDED)
/autotrade real          - Enable REAL trading (real money)
/autotrade off           - Disable auto-trading
/autotrade_status        - Check status & history
/set_interval <min>       - Set check interval (1-10 minutes)
/scheduler_status        - Check scheduled tasks
```

### 4. SMART HUNTER (Auto Hunter)
```
/smarthunter on          - Start Smart Hunter
/smarthunter off         - Stop Smart Hunter
/smarthunter_status     - Check positions & status
```

### 5. ULTRA HUNTER (Conservative)
```
/ultrahunter on          - Start Ultra Hunter (strict criteria)
/ultrahunter off         - Stop Ultra Hunter
/ultrahunter          - Show Ultra Hunter commands
```

### 6. PORTFOLIO & TRADES
```
/balance                - Check balance & positions
/trades                 - View trade history
/performance            - Win rate, P&L, Sharpe ratio
/position <PAIR>        - Deep position analysis
/sync                   - Sync trades from Indodax
```

### 7. MANUAL TRADING
```
/trade BUY <PAIR> <PRICE> <IDR>     - Manual buy
/trade SELL <PAIR> <PRICE> <COIN>    - Manual sell
/cancel <ORDER_ID>                  - Cancel order
/set_sl <PAIR> <PRICE>             - Set stop loss
/set_tp <PAIR> <PRICE>             - Set take profit
/trade_auto_sell <PAIR>               - Auto-sell position
```

### 8. SUPPORT & RESISTANCE
```
/set_sr <PAIR>              - Set manual S/R levels
/view_sr <PAIR>             - View S/R levels
/delete_sr <PAIR>           - Delete S/R levels
```

### 9. ADMIN & SYSTEM
```
/status                  - Bot system status
/retrain                 - Retrain ML model (admin)
/metrics                 - Prometheus-like metrics
/emergency_stop           - Kill switch (STOP ALL)
/hunter_status            - Legacy profit hunter status
```

### 10. SCALPER MODULE

#### Pair Management
```
/s_pair list              - View active pairs
/s_pair add <PAIR>         - Add pair
/s_pair remove <PAIR>       - Remove pair
/s_pair reset            - Reset to default
```

#### Analysis
```
/s_analisa <PAIR>        - Full technical analysis
/s_info <PAIR>            - Position info
```

#### Trading
```
/s_buy <PAIR>            - Buy manual
/s_sell <PAIR>           - Sell manual
/s_sltp <PAIR> <TP> <SL> - Set TP/SL
/s_cancel <PAIR>          - Cancel TP/SL
/s_closeall             - Close all positions
```

#### Portfolio
```
/s_menu                  - Main scalper menu
/s_possi                 - Active positions
/s_portfolio              - View portfolio
/s_riwayat              - Trade history
/s_sync                 - Sync from Indodax
/s_reset                - Reset all positions
```

---

## 📊 CATEGORY COMMANDS

```bash
/cmd              - Show this guide
/cmd bot          - Main bot commands
/cmd scalp        - Scalper commands
/cmd pair         - Pair management
/cmd trade        - Trading commands
/cmd status       - Status commands
```

---

## 🎯 TRADING MODES

### DRY RUN (Simulation) - RECOMMENDED
```bash
/autotrade dryrun
/smarthunter on
```
All trades are SIMULATED - no real money used

### REAL TRADING
```bash
/autotrade real
/smarthunter on
```
Real orders placed on Indodax

---

## 📋 EXAMPLE USAGES

### Add multiple pairs
```
/watch btcidr, ethidr, solidr, dogeidr
```

### Get signal
```
/signal BTCIDR
/signal ethidr
```

### Enable auto-trading
```
/autotrade dryrun
/autotrade real
```

### Check status
```
/status
/autotrade_status
/smarthunter_status
/balance
```

### Scalper
```
/s_analisa BTCIDR
/s_buy BTCIDR
/s_sltp BTCIDR 5 2
```

---

## ⚙️ CONFIGURATION

### Risk Parameters
- Max position: 25% balance
- Stop loss: 2%
- Take profit: 5%
- Max trades/day: 10
- Daily loss limit: 5%
- Min risk-reward: 2:1

### Auto-Trade Intervals
```
/set_interval 1    - Fast (scalping)
/set_interval 3     - Balanced (recommended)
/set_interval 5     - Conservative (default)
```

---

## 👤 ADMIN COMMANDS (Admin Only)

- `/autotrade dryrun` - Enable simulation
- `/autotrade real` - Enable real trading
- `/autotrade off` - Disable
- `/retrain` - Retrain ML model
- `/status` - System status
- `/metrics` - Metrics
- `/emergency_stop` - Kill switch
- `/cleanup_signals` - Clean signals
- `/reset_skip` - Reset invalid pairs
- `/clear_watchlist` - Clear all watchlists
- `/add_autotrade` - Add auto-trade pair
- `/remove_autotrade` - Remove auto-trade pair
- `/list_autotrade` - List auto-trade pairs
- `/set_interval` - Set interval

---

## 📖 HELP PAGES

```bash
/help          - Complete user guide
/menu         - Quick menu
/cmd          - All commands by category
/cmd bot      - Bot commands
/cmd scalp    - Scalper commands
/cmd trade    - Trading commands
/cmd pair     - Pair management
/cmd status   - Status commands
```

---

## 🎓 QUICK REFERENCE

| Task | Command |
|------|---------|
| Get started | `/start` |
| Get help | `/help` |
| Add pairs | `/watch btcidr, ethidr` |
| Get signal | `/signal BTCIDR` |
| Test auto-trade | `/autotrade dryrun` |
| Start hunter | `/smarthunter on` |
| Check balance | `/balance` |
| Check status | `/status` |

---

## 📞 SUPPORT

Contact admin for issues or questions.

---

## ✅ VERSION
Bot Version: v2.0 (Updated: 2026-04-18)