# COMMAND REFERENCE - Telegram Bot Commands

**Last Updated:** 2026-04-30  
**Purpose:** Reference lengkap semua command Telegram bot dan callback handlers.

---

## 📱 BASIC COMMANDS

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/start` | Mulai bot, tampilkan welcome message | `bot.start()` |
| `/help` | Tampilkan help message & command list | `bot.help()` |
| `/menu` | Tampilkan main menu dengan inline keyboard | `bot.menu()` |
| `/settings` | Konfigurasi bot settings | `bot.settings()` |
| `/cmd` | Helper untuk melihat commands | `bot.commands_helper()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 116-121

---

## 👀 WATCHLIST & MONITORING

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/watch <pair>` | Tambahkan pair ke watchlist (contoh: `/watch btcidr`) | `bot.watch()` |
| `/unwatch <pair>` | Hapus pair dari watchlist | `bot.unwatch()` |
| `/list` | Tampilkan watchlist aktif | `bot.list_watch()` |
| `/clear_watchlist` | Hapus semua pair dari watchlist | `bot.clear_watchlist()` |
| `/monitor` | Monitor strong signals | `bot.monitor()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 123-132

**Example:**
```
/watch btcidr
/watch ethidr
/list
```

---

## 📊 PRICE & SIGNALS

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/price <pair>` | Get current price (contoh: `/price btcidr`) | `bot.price()` |
| `/signal <pair>` | Generate signal untuk 1 pair | `bot.get_signal()` |
| `/signals` | Generate signals untuk semua watched pairs | `bot.signals()` |
| `/signal_buy` | Filter: hanya BUY signals | `bot.signal_buy_only()` |
| `/signal_sell` | Filter: hanya SELL signals | `bot.signal_sell_only()` |
| `/signal_hold` | Filter: hanya HOLD signals | `bot.signal_hold_only()` |
| `/signal_buysell` | Filter: BUY & SELL (actionable only) | `bot.signal_buysell()` |
| `/analyze <pair>` | Deep analysis untuk 1 pair | `bot.analyze_signal()` |
| `/scan` | Scan market untuk strong signals | `bot.market_scan()` |
| `/topvolume` | Tampilkan top volume pairs | `bot.top_volume()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 134-150

**Example:**
```
/signal btcidr
/signals
/signal_buy
/analyze ethidr
```

---

## 🔔 NOTIFICATION CONTROLS

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/notifications` | Manage notification settings | `bot.notifications()` |
| `/alerts` | Alias untuk `/notifications` | `bot.notifications()` |
| `/signal_notif` | Toggle auto signal notifications ON/OFF | `bot.signal_notif()` |
| `/notif_buy` | Notifikasi BUY signals saja | `bot.notif_buy()` |
| `/notif_sell` | Notifikasi SELL signals saja | `bot.notif_sell()` |
| `/notif_scalp` | Notifikasi scalp opportunities | `bot.notif_scalp()` |
| `/notif_all` | Notifikasi semua signals (BUY/SELL/HOLD) | `bot.notif_all()` |
| `/notif_status` | Cek notification status | `bot.notif_status()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 142-150

**Notification Filter Modes:**
- `all`: Semua signals (BUY, SELL, HOLD)
- `buy`: Hanya BUY & STRONG_BUY
- `sell`: Hanya SELL & STRONG_SELL
- `actionable`: BUY, STRONG_BUY, SELL, STRONG_SELL (exclude HOLD)

---

## 💰 PORTFOLIO & BALANCE

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/balance` | Cek saldo akun Indodax | `bot.balance()` |
| `/portfolio` | Tampilkan portfolio holdings | `bot.portfolio()` |
| `/trades` | Riwayat trades | `bot.trades()` |
| `/sync` | Sync trades dengan Indodax API | `bot.sync_trades()` |
| `/performance` | Performance metrics (P&L, win rate) | `bot.performance()` |
| `/pair_stats` | Statistics per trading pair | `bot.pair_stats_cmd()` |
| `/trade_review <trade_id>` | Review specific trade | `bot.trade_review_cmd()` |
| `/trade_reviews` | Recent trade reviews | `bot.trade_reviews_recent_cmd()` |
| `/position` | View open positions | `bot.position()` |
| `/trade <pair>` | Manual trade (akan prompt amount) | `bot.trade()` |
| `/trade_auto_sell` | Configure auto-sell settings | `bot.trade_auto_sell()` |
| `/cancel <trade_id>` | Cancel pending trade | `bot.cancel_trade()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 153-166

**Example:**
```
/balance
/portfolio
/performance
/trade_review 12345
```

---

## ⚙️ AUTO-TRADING & STATUS

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/status` | Bot status (trading enabled/disabled) | `bot.status()` |
| `/start_trading` | Enable auto-trading | `bot.start_trading()` |
| `/stop_trading` | Disable auto-trading | `bot.stop_trading()` |
| `/emergency_stop` | **EMERGENCY STOP** - stop all trading immediately | `bot.emergency_stop()` |
| `/autotrade` | Toggle auto-trade ON/OFF | `bot.autotrade()` |
| `/autotrade_status` | Check auto-trade status | `bot.autotrade_status()` |
| `/add_autotrade <pair>` | Tambah pair ke auto-trade list | `bot.add_autotrade()` |
| `/remove_autotrade <pair>` | Hapus pair dari auto-trade list | `bot.remove_autotrade()` |
| `/list_autotrade` | Tampilkan auto-trade pairs | `bot.list_autotrade()` |
| `/scheduler_status` | Status signal scheduler | `bot.scheduler_status()` |
| `/set_interval <seconds>` | Set signal generation interval | `bot.set_interval()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 168-188

**Example:**
```
/status
/add_autotrade btcidr
/list_autotrade
/start_trading
/emergency_stop
```

---

## 🤖 ML & ANALYSIS

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/retrain` | Retrain ML models | `bot.retrain_ml()` |
| `/backtest <pair>` | Backtest strategy | `bot.backtest_cmd()` |
| `/backtest_v3 <pair>` | Backtest dengan ML V3 | `bot.backtest_v3_cmd()` |
| `/dryrun` | Dry-run mode (simulate trading) | `bot.dryrun_cmd()` |
| `/regime` | Detect current market regime | `bot.regime_cmd()` |
| `/kelly <pair>` | Kelly criterion position sizing | `bot.kelly_cmd()` |
| `/compare` | Compare ML model versions | `bot.compare_cmd()` |
| `/signal_quality <pair>` | Cek signal quality score | `bot.signal_quality_cmd()` |
| `/signal_report` | Generate signal quality report | `bot.signal_report_cmd()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 181-187, 191-192

**Example:**
```
/regime
/backtest btcidr
/signal_quality ethidr
```

---

## 🎯 RISK MANAGEMENT

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/set_sl <pair> <price>` | Set stop loss | `bot.set_stoploss()` |
| `/set_tp <pair> <price>` | Set take profit | `bot.set_takeprofit()` |
| `/set_sr <pair> <support> <resistance>` | Set manual S/R levels | `bot.set_manual_sr()` |
| `/view_sr <pair>` | View S/R levels | `bot.view_manual_sr()` |
| `/delete_sr <pair>` | Delete manual S/R | `bot.delete_manual_sr()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 197-201

**Example:**
```
/set_sl btcidr 450000000
/set_tp btcidr 480000000
/view_sr btcidr
```

---

## 🏹 HUNTER MODULES

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/hunter_status` | Status semua hunter modules | `bot.hunter_status()` |
| `/smarthunter` | Control Smart Hunter module | `bot.smarthunter_cmd()` |
| `/smarthunter_status` | Status Smart Hunter | `bot.smarthunter_status()` |
| `/ultrahunter` | Control Ultra Hunter module | `bot.ultra_hunter_cmd()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 179-180, 202-203

**Modules:**
- **Smart Hunter**: Moderate risk, profit target 3-5%
- **Ultra Hunter**: Aggressive, profit target 5-10%

---

## ⚡ SCALPER COMMANDS (Prefix: `s_`)

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/s_menu` | Scalper main menu | `scalper.cmd_menu()` |
| `/s_pairs` | Daftar scalping pairs | `scalper.cmd_pairs()` |
| `/s_posisi` | Posisi scalper aktif | `scalper.cmd_posisi()` |
| `/s_portfolio` | Scalper portfolio | `scalper.cmd_portfolio()` |
| `/s_analisa <pair>` | Analisa scalping opportunity | `scalper.cmd_analisa()` |
| `/s_buy <pair> <amount>` | Manual scalp buy | `scalper.cmd_buy()` |
| `/s_sell <pair> <amount>` | Manual scalp sell | `scalper.cmd_sell()` |
| `/s_sltp <pair> <sl> <tp>` | Set SL/TP untuk scalp position | `scalper.cmd_sltp()` |
| `/s_cancel <order_id>` | Cancel scalp order | `scalper.cmd_cancel()` |
| `/s_info` | Scalper info & stats | `scalper.cmd_info()` |
| `/s_pair <pair>` | Set active scalping pair | `scalper.cmd_pair()` |
| `/s_reset` | Reset scalper state | `scalper.cmd_reset()` |
| `/s_rest` | Alias untuk `/s_reset` | `scalper.cmd_reset()` |
| `/s_closeall` | Close semua scalp positions | `scalper.cmd_close_all()` |
| `/s_riwayat` | Riwayat scalp trades | `scalper.cmd_riwayat()` |
| `/s_sync` | Sync scalper dengan exchange | `scalper.cmd_sync()` |
| `/s_signal_summary` | Summary scalper signals | `scalper.cmd_signal_summary()` |

**File:** `scalper/scalper_module.py`  
**Registry:** `core/handler_registry.py` lines 209-229

**Example:**
```
/s_menu
/s_analisa btcidr
/s_buy btcidr 0.001
/s_posisi
/s_closeall
```

---

## 📈 METRICS & PERFORMANCE

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/metrics` | Bot performance metrics | `bot.metrics_cmd()` |
| `/metric` | Alias untuk `/metrics` | `bot.metrics_cmd()` |
| `/dashboard` | TMA Dashboard (advanced analytics) | `bot.cmd_dashboard()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 173-174, 232

---

## 🛠️ MAINTENANCE & CLEANUP

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/cleanup_signals` | Cleanup old signals from DB | `bot.cleanup_signals()` |
| `/backfill_performance` | Backfill performance metrics | `bot.backfill_performance()` |
| `/reset_skip` | Reset skip counters | `bot.reset_skip()` |
| `/reset_drawdown` | Reset drawdown state | `bot.cmd_reset_drawdown()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 128-131

---

## 🔘 CALLBACK HANDLERS (Inline Buttons)

### Main Callback Handler: `bot.callback_handler()`

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` line 236

**Callback Patterns:**
```python
CallbackQueryHandler(bot.callback_handler)
```

**Callback Data Formats:**
- `watch_<pair>`: Watch pair
- `unwatch_<pair>`: Unwatch pair
- `signal_<pair>`: Generate signal
- `buy_<pair>`: Execute buy
- `sell_<pair>`: Execute sell
- `autotrade_on`: Enable auto-trade
- `autotrade_off`: Disable auto-trade
- `notif_on`: Enable notifications
- `notif_off`: Disable notifications
- `filter_<mode>`: Set notification filter (buy/sell/all/actionable)

**Example Inline Keyboard:**
```python
[
    [InlineKeyboardButton("📊 Signal", callback_data="signal_btcidr")],
    [InlineKeyboardButton("💰 Buy", callback_data="buy_btcidr")],
    [InlineKeyboardButton("📉 Sell", callback_data="sell_btcidr")],
]
```

---

## 📝 MESSAGE HANDLERS

### Text Input Handler: `bot.handle_text_input()`
**Registry:** `core/handler_registry.py` line 234

Handles non-command text messages (untuk input pair, amount, dll).

### Unknown Command Handler: `bot.handle_unknown_command()`
**Registry:** `core/handler_registry.py` line 235

Catches undefined commands dan suggest `/help`.

---

## 🚨 ERROR HANDLER

### Global Error Handler: `_build_error_handler(bot)`
**File:** `core/handler_registry.py` lines 40-101  
**Registry:** line 114

**Error Types Handled:**
1. **Transient Errors** (throttled logging):
   - `Conflict`: Duplicate bot instance
   - `NetworkError`: Network issues
   - `TimedOut`: Request timeout
   - `RetryAfter`: Rate limit

2. **User Errors** (warning only):
   - `Forbidden`: User blocked bot
   - `BadRequest`: Invalid request

3. **Serious Errors** (full stacktrace + admin notification):
   - Unknown exceptions
   - Handler crashes

**Throttle:** 60 seconds untuk transient errors (avoid log spam)

---

## 📊 COMMAND CATEGORIES

### By Module

| Category | Commands Count | Prefix |
|----------|----------------|--------|
| Basic | 5 | None |
| Watchlist | 5 | None |
| Signals | 10 | None |
| Notifications | 8 | `notif_` |
| Portfolio | 12 | None |
| Auto-Trading | 11 | `autotrade_` |
| ML & Analysis | 9 | None |
| Risk Management | 5 | `set_`, `view_`, `delete_` |
| Hunter Modules | 4 | None |
| Scalper | 17 | `s_` |
| Metrics | 3 | None |
| Maintenance | 4 | None |

**Total Commands:** ~93 commands

---

## 🔧 COMMAND REGISTRATION FLOW

```
bot.py startup
    │
    ├─ Create Application (Telegram)
    │
    ├─ Call: register_bot_handlers(bot)
    │   │
    │   ├─ Register error handler
    │   │
    │   ├─ Register command groups:
    │   │   ├─ Basic (start, help, menu, settings)
    │   │   ├─ Watchlist (watch, unwatch, list)
    │   │   ├─ Signals (price, signal, signals, analyze)
    │   │   ├─ Portfolio (balance, portfolio, trades)
    │   │   ├─ Auto-Trading (status, start_trading, autotrade)
    │   │   ├─ ML & Analysis (retrain, backtest, regime)
    │   │   ├─ Risk (set_sl, set_tp, set_sr)
    │   │   ├─ Hunters (smarthunter, ultrahunter)
    │   │   └─ Scalper (s_* commands) - conditional
    │   │
    │   ├─ Register message handlers (text input, unknown commands)
    │   │
    │   └─ Register callback query handler
    │
    └─ Start polling
```

---

## 🎯 QUICK REFERENCE - Most Used Commands

```bash
# Setup
/start
/watch btcidr
/watch ethidr

# Signals
/signal btcidr
/signals
/notif_buy

# Trading
/balance
/portfolio
/add_autotrade btcidr
/start_trading

# Monitoring
/status
/performance
/metrics

# Emergency
/emergency_stop
```

---

## 📚 Documentation Update Rules

**When to Update This File:**
1. Menambah/menghapus command di `bot.py`
2. Menambah/menghapus handler di `core/handler_registry.py`
3. Menambah/menghapus callback pattern
4. Mengubah command behavior significantly

**Update Steps:**
1. Edit command table di section yang sesuai
2. Update command count jika perlu
3. Update example jika command signature berubah
4. Git commit dengan message: "docs: update COMMAND_REFERENCE for <command>"

---

**Navigation:**
- Prev: `OPERATIONS_FLOW_ALGORITHMA.md` (flow & algoritma)
- Next: `DOCUMENTATION_RULES.md` (coding standards)
