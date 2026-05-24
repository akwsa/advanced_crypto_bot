# COMMAND REFERENCE - Telegram Bot Commands

**Last Updated:** 2026-05-22  
**Purpose:** Reference lengkap semua command Telegram bot dan callback handlers, diverifikasi dari `bot.py`, `core/handler_registry.py`, `bot_parts/command_texts.py`, dan `scalper/scalper_module.py`.

> Semua command yang terdaftar di `TELEGRAM_BOT_COMMANDS` (lihat `bot_parts/command_texts.py`) akan muncul di **native Telegram autocomplete menu** saat user mengetik `/`. Ketika user mengetik prefix seperti `/s`, Telegram memfilter daftar ini, sehingga semua command scalper ber-prefix `/s_` ikut muncul bersama `/start`, `/signal`, `/signals`, `/scan`, `/status`, `/settings`.

---

## 📱 BASIC COMMANDS

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/start` | Mulai bot, tampilkan welcome message | `bot.start()` |
| `/help` | Tampilkan help message & command list | `bot.help()` |
| `/menu` | Tampilkan main menu dengan inline keyboard | `bot.menu()` |
| `/settings` | Konfigurasi bot settings | `bot.settings()` |
| `/cmd` | Helper untuk melihat commands | `bot.commands_helper()` |
| `/register <kode>` | Registrasi akses bot dengan invite code. Bot menerapkan default-deny: hanya user terdaftar yang bisa pakai. Admin (ADMIN_IDS) otomatis lolos. | `bot.register_access()` |

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
| `/signal <pair>` | Generate signal untuk 1 pair. Jika BUY/SELL valid, pesan dapat menampilkan tombol Scalper-only. | `bot.get_signal()` |
| `/signal buy` | Filter latest saved watchlist signals: hanya BUY/STRONG_BUY. Tidak scan/generate ulang. Sama tujuan dengan `/signal_buy`. | `bot.get_signal()` |
| `/signal sell` | Filter latest saved watchlist signals: hanya SELL/STRONG_SELL. Tidak scan/generate ulang. Sama tujuan dengan `/signal_sell`. | `bot.get_signal()` |
| `/signal hold` | Filter latest saved watchlist signals: hanya HOLD. Tidak scan/generate ulang. Sama tujuan dengan `/signal_hold`. | `bot.signal_hold_only()` |
| `/signal buysell` | Shortcut filter watchlist: BUY + SELL tanpa HOLD. Sama tujuan dengan `/signal_buysell`. | `bot.signal_buysell()` |
| `/signal on` | Aktifkan notifikasi otomatis BUY/STRONG_BUY dan SELL/STRONG_SELL. HOLD otomatis difilter. | `bot.get_signal()` |
| `/signal off` | Matikan notifikasi signal otomatis. | `bot.get_signal()` |
| `/signals` | Generate signals untuk semua watched pairs. BUY/SELL valid dapat menampilkan tombol Scalper-only. | `bot.signals()` |
| `/signal_buy` | Filter latest saved watchlist signals: hanya BUY/STRONG_BUY, tanpa scan ulang | `bot.signal_buy_only()` |
| `/signal_sell` | Filter latest saved watchlist signals: hanya SELL/STRONG_SELL, tanpa scan ulang | `bot.signal_sell_only()` |
| `/signal_hold` | Filter latest saved watchlist signals: hanya HOLD, tanpa scan ulang | `bot.signal_hold_only()` |
| `/signal_buysell` | Filter: BUY & SELL/actionable only. HOLD di-skip. | `bot.signal_buysell()` |
| `/analyze <pair>` | Deep analysis untuk 1 pair | `bot.analyze_signal()` |
| `/scan` | Scan market untuk strong signals | `bot.market_scan()` |
| `/topvolume` | Tampilkan top volume pairs | `bot.top_volume()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 134-150

**Example:**
```
/signal btcidr
/signal buy
/signal sell
/signal on
/signal off
/signals
/signal_buy
/signal_sell
/signal_buysell
/analyze ethidr
```

**Signal Action Button Safety:**
- Tombol BUY/SELL pada pesan signal hanya memakai callback Scalper: `s_buy:<pair>` dan `s_sell:<pair>`.
- Pair harus resmi Indodax IDR.
- Tombol BUY tampil hanya jika ada saldo IDR atau balance API sedang tidak bisa dicek secara aman.
- Tombol SELL tampil hanya jika ada balance coin/hold di Indodax atau posisi lokal Scalper.
- HOLD tidak menampilkan tombol BUY/SELL.

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
- Automatic/background Telegram signal alerts are currently locked to actionable signals: BUY/STRONG_BUY and SELL/STRONG_SELL.
- `/signal on` enables actionable automatic push; HOLD/neutral signals remain blocked.
- Legacy mode labels may still exist in commands/settings, but automatic HOLD signal pushes are blocked.
- Use manual `/signal hold` if HOLD snapshots are needed explicitly.

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
| `/trade <BUY/SELL> <pair> <price> <amount>` | Manual trade | `bot.trade()` |
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
| `/autotrade` | Panel/mode auto-trade. Policy sekarang: no-money automation, gunakan DRY RUN/OFF. | `bot.autotrade()` |
| `/autotrade dryrun` | Aktifkan mode simulasi tanpa uang asli. Selama policy DRY RUN aktif, mode ini juga diterapkan otomatis setiap `bot.py` start. | `bot.autotrade()` |
| `/autotrade real` | DIBLOKIR oleh safety policy; dipaksa tetap DRY RUN / NO MONEY. | `bot.autotrade()` |
| `/autotrade off` | Matikan auto-trade. | `bot.autotrade()` |
| `/autotrade_status` | Check auto-trade status | `bot.autotrade_status()` |
| `/add_autotrade <pair>` | Tambah pair ke auto-trade list | `bot.add_autotrade()` |
| `/remove_autotrade <pair>` | Hapus pair dari auto-trade list | `bot.remove_autotrade()` |
| `/list_autotrade` | Tampilkan auto-trade pairs | `bot.list_autotrade()` |
| `/scheduler_status` | Status signal scheduler | `bot.scheduler_status()` |
| `/set_interval <minutes>` | Set signal generation interval (dalam menit) | `bot.set_interval()` |

**File:** `bot.py`  
**Registry:** `core/handler_registry.py` lines 168-188

**Example:**
```
/status
/add_autotrade btcidr
/list_autotrade
/autotrade dryrun
/autotrade real      # akan ditolak/dikunci DRY RUN
/start_trading       # hanya DRY RUN / NO MONEY
/emergency_stop
```

**Safety Policy:** AutoTrade, `/start_trading`, Smart Hunter, dan Ultra Hunter dikunci untuk DRY RUN / NO MONEY. Setiap startup `bot.py` otomatis menerapkan efek `/autotrade dryrun` agar AutoTrade naik dalam mode simulasi. Eksekusi uang asli hanya boleh lewat Scalper (`/s_buy`, `/s_sell`) dan tetap melewati flow konfirmasi Scalper.

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

## 📈 QUANT TRADING (NEW)

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/quant` | Menu utama quant trading modules | `bot.quant_menu_cmd()` |
| `/quant_mr <pair>` | Z-Score Mean Reversion analysis | `bot.quant_mr_cmd()` |
| `/quant_kelly <pair>` | Bayesian Kelly position sizing | `bot.quant_kelly_cmd()` |
| `/quant_momentum <pair>` | Momentum factor scoring | `bot.quant_momentum_cmd()` |
| `/quant_perf` | Performance analytics (Sharpe, Sortino, Calmar) | `bot.quant_perf_cmd()` |
| `/quant_corr` | Dynamic correlation matrix & portfolio heat | `bot.quant_corr_cmd()` |
| `/quant_arb` | Statistical arbitrage scanner | `bot.quant_arb_cmd()` |

**File:** `bot.py` (quant command handlers)  
**Module:** `quant/` (engine implementations)  
**Registry:** `core/handler_registry.py`

**Example:**
```
/quant
/quant_mr btcidr
/quant_kelly btcidr
/quant_momentum ethidr
/quant_perf
/quant_corr
/quant_arb
```

### Quant Module Details:

**1. Mean Reversion (`/quant_mr`)**
- Multi-timeframe z-score (period 20/50/100)
- Bollinger %B confirmation
- VWAP deviation scoring
- Market regime alignment check
- Output: z-score, signal direction, confluence bonus

**2. Bayesian Kelly (`/quant_kelly`)**
- Per-pair adaptive win rate (exponential decay)
- Bayesian prior (conservative start)
- Confidence-adjusted sizing
- Volatility-adjusted sizing
- Drawdown-aware reduction
- Output: optimal position size, Kelly fraction

**3. Momentum Factor (`/quant_momentum`)**
- ROC multi-period (5/10/20/50 candles)
- Volume-weighted momentum
- Momentum acceleration (ROC of ROC)
- Relative strength vs BTC
- Output: momentum score (-100 to +100), edge bonus

**4. Performance Analytics (`/quant_perf`)**
- Sharpe Ratio (annualized)
- Sortino Ratio (downside risk)
- Calmar Ratio (return/drawdown)
- Profit Factor, Expectancy
- Max Drawdown & Recovery Factor
- Rolling 7d/30d metrics
- Output: comprehensive performance report

**5. Dynamic Correlation (`/quant_corr`)**
- Rolling correlation matrix (20-period)
- Auto-detect correlation groups
- Portfolio heat score (0-1)
- Diversification score
- Correlation limit check before new trades
- Output: matrix, heat level, risk assessment

**6. Statistical Arbitrage (`/quant_arb`)**
- Cointegration test (Engle-Granger)
- Spread z-score calculation
- Half-life estimation
- Entry/exit signals for pair trades
- Output: cointegrated pairs, spread signals

---

## 🎯 RISK MANAGEMENT

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/set_sl <persen>` | Set stop loss (persentase, contoh: `2.5`) | `bot.set_stoploss()` |
| `/set_tp <persen>` | Set take profit (persentase, contoh: `5.0`) | `bot.set_takeprofit()` |
| `/set_sr <pair> <S1> <S2> <R1> <R2> [notes]` | Set manual S/R levels | `bot.set_manual_sr()` |
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
- **Smart Hunter**: start/on diblokir untuk eksekusi uang asli; status tetap bisa dicek.
- **Ultra Hunter**: start/on diblokir untuk eksekusi uang asli; status tetap bisa dicek.
- Trading uang asli hanya lewat Scalper (`/s_buy`, `/s_sell`).

---

## ⚡ SCALPER COMMANDS (Prefix: `s_`)

| Command | Description | Handler Function |
|---------|-------------|------------------|
| `/s_menu` | Scalper main menu | `scalper.cmd_menu()` |
| `/s_pairs` | Daftar scalping pairs | `scalper.cmd_pairs()` |
| `/s_posisi` | Posisi scalper aktif | `scalper.cmd_posisi()` |
| `/s_portfolio` | Scalper portfolio | `scalper.cmd_portfolio()` |
| `/s_analisa <pair>` | Analisa scalping opportunity | `scalper.cmd_analisa()` |
| `/s_buy <pair> [price] [idr_amount]` | Manual Scalper BUY. Ini jalur utama untuk real-money buy; tetap ikuti konfirmasi/validasi Scalper. | `scalper.cmd_buy()` |
| `/s_sell <pair> [price] [amount]` | Manual Scalper SELL. Ini jalur utama untuk real-money sell; tetap ikuti konfirmasi/validasi Scalper. | `scalper.cmd_sell()` |
| `/s_sltp <pair> <tp> <sl>` | Set TP/SL untuk scalp position | `scalper.cmd_sltp()` |
| `/s_cancel <pair> [tp|sl|all]` | Cancel TP/SL Scalper untuk pair | `scalper.cmd_cancel()` |
| `/s_info` | Scalper info & stats | `scalper.cmd_info()` |
| `/s_pair <pair>` | Set active scalping pair | `scalper.cmd_pair()` |
| `/s_reset` | Reset scalper state | `scalper.cmd_reset()` |
| `/s_rest` | Alias untuk `/s_reset` | `scalper.cmd_reset()` |
| `/s_close_all` | Close semua scalp positions | `scalper.cmd_close_all()` |
| `/s_refresh` | Refresh portfolio scalper | `scalper.cmd_refresh_portfolio()` |
| `/s_riwayat` | Riwayat scalp trades | `scalper.cmd_riwayat()` |
| `/s_sync` | Sync scalper dengan exchange | `scalper.cmd_sync()` |
| `/s_signal_summary` | Summary scalper signals | `scalper.cmd_signal_summary()` |

> Semua command scalper di tabel ini terdaftar di `TELEGRAM_BOT_COMMANDS` sehingga muncul di native Telegram menu saat user mengetik `/s_`. Handler registration: `scalper/scalper_module.py::_register_handlers`.

**File:** `scalper/scalper_module.py`  
**Registry:** `core/handler_registry.py` lines 209-229

**Example:**
```
/s_menu
/s_analisa btcidr
/s_buy btcidr 650000000 50000
/s_sell btcidr
/s_sltp btcidr 680000000 630000000
/s_cancel btcidr all
/s_posisi
/s_close_all
```

**Aliases:** `buy`, `sell`, `sltp`, `posisi`, dan `analisa` juga diregister langsung oleh `scalper/scalper_module.py`, tetapi prefix `/s_` lebih direkomendasikan agar tidak membingungkan dengan command utama.

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
- `s_buy:<pair>`: Buka flow BUY Scalper dari tombol signal.
- `s_sell:<pair>`: Buka flow SELL Scalper dari tombol signal.
- `s_refresh_posisi`: Refresh posisi Scalper.
- `watch_<pair>`: Watch pair.
- `signal_<pair>`: Generate signal.
- `price_<pair>`: Cek harga pair.
- `menu_home`, `nav_<section>`: Navigasi menu.
- `autotrade_*`: Panel/status AutoTrade; money mode tetap dikunci DRY RUN / NO MONEY.
- `notif_*` / `filter_<mode>`: Set notification filter (`buy`, `sell`, `all`, `actionable`).

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
| Quant Trading | 7 | `quant_` |
| Risk Management | 5 | `set_`, `view_`, `delete_` |
| Hunter Modules | 4 | None |
| Scalper | 17 | `s_` |
| Metrics | 3 | None |
| Maintenance | 4 | None |

**Total Commands:** ~100 commands

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
    │   │   ├─ Quant Trading (quant, quant_mr, quant_kelly, quant_momentum, quant_perf, quant_corr, quant_arb)
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
/signal buy
/signal sell
/signal_buysell
/signals
/notif_buy
/notif_sell

# Trading aman
/balance
/portfolio
/add_autotrade btcidr
/autotrade dryrun
/start_trading     # DRY RUN / NO MONEY
/s_menu
/s_buy btcidr 650000000 50000
/s_sell btcidr

# Monitoring
/status
/performance
/metrics

# Emergency
/emergency_stop
```

---

## 🔒 ACCESS CONTROL (SECURITY)

**Effective:** 2026-05-22

Bot menerapkan **default-deny**: semua user ditolak kecuali terdaftar.

### Tiga cara menjadi user terdaftar:

| Metode | Syarat |
|--------|--------|
| **Admin** | user_id ada di `ADMIN_IDS` (.env / environment) |
| **Whitelist** | user_id ada di `ALLOWED_USER_IDS` (.env / environment) |
| **Invite self-registration** | kirim `/register <kode>` — kode harus cocok `TELEGRAM_INVITE_CODE` (.env) |

### Batasan tambahan:
- Bot **hanya bisa dipakai di private chat**. Grup / channel ditolak.
- Admin commands tetap dicek 2× (gate + handler internal).

### File:
- `core/config.py` — `ADMIN_IDS`, `ALLOWED_USER_IDS`, `TELEGRAM_INVITE_CODE`
- `core/database.py` — tabel `telegram_users` + CRUD
- `core/handler_registry.py` — wrapper `_guard_callback()` untuk semua handler
- `bot.py` — helper `_is_authorized()`, `_require_authorized()`, `register_access()`

### Dokumentasi lengkap:
- 📄 `docs/telegram-access-control.md`
- 🧪 `tests/test_telegram_access_control.py` — 12 test

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
