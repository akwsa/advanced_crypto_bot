# 💬 Commands Reference — Advanced Crypto Trading Bot

Semua Telegram command yang tersedia. Format: `/command [arg]`.

**Legend:**
- 🟢 **Public** — semua user terdaftar bisa pakai
- 🔴 **Admin** — hanya admin di `Config.ADMIN_IDS`
- 🧪 **DRY RUN safe** — tidak pakai uang asli
- 💰 **Real money** — bisa execute order asli ke Indodax

---

## 🚀 Getting Started

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/start` | 🟢 | Welcome message + menu utama |
| `/register <invite_code>` | 🟢 | Daftar akses bot (butuh kode dari admin) |
| `/help` | 🟢 | Panduan lengkap |
| `/menu` | 🟢 | Menu cepat dengan tombol inline |
| `/cmd [kategori]` | 🟢 | Quick reference command |
| `/settings` | 🟢 | Settings panel |

---

## 👀 Watchlist & Monitoring

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/watch <PAIR>` | 🟢 | Tambah pair ke watchlist (boleh banyak: `/watch btcidr, ethidr`) |
| `/unwatch <PAIR>` | 🟢 | Hapus pair dari watchlist |
| `/list` | 🟢 | Lihat watchlist Anda |
| `/clear_watchlist [all]` | 🟢/🔴 | Kosongkan watchlist (admin + `all` = clear semua user) |
| `/price <PAIR>` | 🟢 | Cek harga real-time pair |
| `/topvolume` | 🟢 | Top 50 pair by volume 24h dari Indodax |
| `/scan` | 🟢 | Market opportunities (top gainers/losers/trending) |

**Format pair:** `btcidr`, `BTC/IDR`, `BTCIDR` — bot auto-normalize.

---

## 📡 Signal & Analisis

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/signal <PAIR>` | 🟢 | Generate signal lengkap untuk 1 pair (TA + ML + chart) |
| `/signals` | 🟢 | Semua signal dari watchlist (BUY + SELL + HOLD) |
| `/signal buy` | 🟢 | Filter signal BUY/STRONG_BUY dari watchlist (saved signals) |
| `/signal sell` | 🟢 | Filter signal SELL/STRONG_SELL dari watchlist |
| `/signal hold` | 🟢 | Filter signal HOLD |
| `/signal buysell` | 🟢 | BUY + SELL saja, skip HOLD |
| `/signal_buy` / `/signal_sell` | 🟢 | Alias untuk filter di atas |
| `/analyze <PAIR>` | 🟢 | Quick BUY/SELL analysis (lebih ringkas) |
| `/notifications` | 🟢 | Riwayat notifikasi signal yang dikirim |

### Signal Notification Control (admin)

| Command | Deskripsi |
|---------|-----------|
| `/signal on` / `/signal off` | Nyalakan / matikan push notification otomatis |
| `/signal_notif buy` | Filter notif: hanya BUY/STRONG_BUY |
| `/signal_notif sell` | Filter notif: hanya SELL/STRONG_SELL |
| `/signal_notif both` | Filter notif: BUY + SELL (skip HOLD) |
| `/signal_notif status` | Lihat filter aktif |
| `/notif_buy` / `/notif_sell` / `/notif_scalp` / `/notif_all` | Shortcut filter |
| `/notif_status` | Status filter saat ini |

### Signal Quality (admin)

| Command | Deskripsi |
|---------|-----------|
| `/signal_quality <PAIR> [TYPE]` | Analisis win rate historical signal per pair |
| `/signal_report [BUY|SELL] [limit]` | Top performing pair berdasarkan signal accuracy |

---

## 💼 Portfolio & Trading

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/balance [PAIR]` | 🟢 | Cek saldo IDR + crypto (filter per pair opsional) |
| `/portfolio` | 🟢 | Portfolio summary + risk metrics + open positions |
| `/trades` | 🟢 | Open trades + recent closed trades |
| `/position <PAIR>` | 🟢 | Detailed position analysis untuk 1 pair (PnL, S/R, ML) |
| `/performance` | 🟢 | Win rate, P&L, sharpe ratio, daily breakdown |
| `/sync` | 🟢 | Sync trade history dari Indodax API ke DB |
| `/pair_stats [min_trades]` | 🟢 | Ranking pair berdasarkan profit factor |

### Trade Reviews

| Command | Deskripsi |
|---------|-----------|
| `/trade_review <ID>` | Review detail satu trade dengan lesson learned |
| `/trade_reviews [PAIR] [limit]` | Recent trade reviews |

### Manual Trade (delegate ke Scalper)

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/trade BUY <PAIR> <PRICE> <IDR>` | 🔴💰 | Manual BUY — delegate ke `/s_buy` |
| `/trade SELL <PAIR> <PRICE> <COIN>` | 🔴💰 | Manual SELL — delegate ke `/s_sell` |
| `/trade_auto_sell <PAIR> <%>` | 🔴 | Set auto-sell target untuk semua posisi pair |
| `/cancel <ORDER_ID> | <PAIR>` | 🔴 | Cancel pending limit order |
| `/set_sl <%>` | 🔴 | Set custom stop loss percentage (untuk trade baru) |
| `/set_tp <%>` | 🔴 | Set custom take profit percentage |

---

## ⚡ Scalper (Real Trading Path)

**Penting:** Scalper adalah **satu-satunya jalur** untuk eksekusi uang asli ke Indodax.

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/s_menu` | 🟢 | Menu utama Scalper |
| `/s_buy <PAIR> <PRICE> <IDR> [TP] [SL]` | 🔴💰 | BUY via Scalper (dengan konfirmasi), opsional langsung set TP/SL |
| `/s_sell <PAIR> [PRICE] [AMOUNT]` | 🔴💰 | SELL via Scalper |
| `/s_sltp <PAIR> <TP> <SL>` | 🔴💰 | Set/update Take Profit & Stop Loss posisi Scalper; gunakan `-` untuk hapus salah satu level |
| `/s_cancel <PAIR> [tp|sl|all]` | 🔴💰 | Hapus TP, SL, atau keduanya dari posisi Scalper |
| `/s_posisi` | 🟢 | Posisi Scalper aktif + ringkasan TP/SL/RR |
| `/s_analisa <PAIR>` | 🟢 | Analisa cepat pair untuk scalping |

Contoh SL/TP:
```text
/s_buy btcidr 1500000000 100000 1545000000 1470000000
/s_sltp btcidr 1545000000 1470000000
/s_cancel btcidr all
```

Tampilan Telegram Scalper menampilkan persentase TP/SL dari entry, estimasi Risk/Reward, dan R/R. Tombol cepat posisi menyediakan preset `TP +1% / SL -0.5%`, `TP +2% / SL -1%`, `TP +3% / SL -2%`, serta `SL BE`.

⚠️ **Catatan safety:** SL/TP Scalper adalah **bot-side polling**, bukan native OCO Indodax. Jika bot mati/offline, trigger TP/SL tidak berjalan. Tombol "🟢 BUY via Scalper" / "🔴 SELL via Scalper" yang muncul di pesan signal otomatis route ke command Scalper di atas (bukan execute langsung — masih ada konfirmasi).

---

## 🤖 Auto-Trade (Admin, DRY RUN only)

**Safety Policy:** AutoTrade dikunci ke **DRY RUN** — `/autotrade real` di-block.

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/autotrade` | 🔴🧪 | Toggle ON/OFF (default DRY RUN) |
| `/autotrade dryrun` | 🔴🧪 | Enable DRY RUN simulation |
| `/autotrade off` | 🔴 | Disable auto-trade |
| `/autotrade real` | 🔴 | ❌ **DI-BLOCK** oleh safety policy |
| `/autotrade_status` | 🔴 | Status detail + history hari ini |
| `/start_trading` | 🔴🧪 | Start auto-trade (DRY RUN locked) |
| `/stop_trading` | 🔴 | Pause auto-trade (posisi yang ada tetap aktif) |
| `/emergency_stop` | 🔴💰 | Kill switch — flatten semua posisi + halt trading |
| `/set_interval <minutes>` | 🔴 | Ubah interval scan (1-30 menit) |

### Auto-Trade Pairs (terpisah dari watchlist!)

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/add_autotrade <PAIR>` | 🔴 | Tambah pair ke auto-trade list |
| `/remove_autotrade <PAIR>` | 🔴 | Hapus dari auto-trade list |
| `/list_autotrade` | 🔴 | Lihat auto-trade list |

**Penting:** auto-trade list ≠ watchlist. Watchlist untuk monitoring + scalper, auto-trade list untuk eksekusi otomatis.

---

## 🎯 Profit Hunters (Admin, DRY RUN locked)

### Smart Hunter

| Command | Deskripsi |
|---------|-----------|
| `/smarthunter on` / `/smarthunter off` | Start/stop (locked DRY RUN) |
| `/smarthunter_status` | Status detail Smart Hunter |

**Strategi:** Partial sell di +3% (50%), +5% (30%), +8% (20%), trailing stop 1.5%, hard SL -2%, max 5 trades/hari.

### Ultra Hunter

| Command | Deskripsi |
|---------|-----------|
| `/ultrahunter start` / `/ultrahunter stop` | Start/stop (locked DRY RUN) |
| `/ultrahunter status` | Status Ultra Hunter |

**Strategi:** Conservative — max 100k IDR/posisi, 2 trades/hari, TP +4%, SL -2%, cooldown 1h setelah loss.

### Hunter Dashboard

| Command | Deskripsi |
|---------|-----------|
| `/hunter_status` | Dashboard gabungan Smart Hunter + Ultra Hunter |

---

## 📊 Support / Resistance

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/set_sr <PAIR> <S1> <S2> <R1> <R2> [notes]` | 🔴 | Set manual S/R levels (override auto-detection) |
| `/view_sr [PAIR]` | 🔴 | Lihat manual S/R levels |
| `/delete_sr <PAIR>` | 🔴 | Hapus manual S/R, kembali ke auto-detect |

---

## 🤖 Machine Learning

| Command | Akses | Deskripsi |
|---------|-------|-----------|
| `/retrain` | 🔴 | Manual retrain ML model V1/V2 + V4 (background, dengan notifikasi hasil) |
| `/backtest <PAIR> <DAYS>` | 🔴 | Backtest standard (V1/V2) |
| `/backtest_v3 <PAIR> <DAYS>` | 🔴 | PRO Backtest (V3 dengan fees, Kelly sizing, comprehensive metrics) |
| `/dryrun <PAIR> [BALANCE]` | 🔴 | Simulasi trading via V3 (no real orders) |
| `/regime <PAIR>` | 🟢 | Deteksi market regime (volatility, trend, volume) |
| `/kelly [WIN_RATE] [AVG_WIN] [AVG_LOSS]` | 🟢 | Kelly Criterion position sizing calculator |
| `/compare [DAYS]` | 🔴 | Multi-pair backtest comparison |

---

## 🔧 Admin & Status

| Command | Deskripsi |
|---------|-----------|
| `/status` | Bot status: uptime, CPU, memory, watchlist, mode trading |
| `/metrics` | Detailed metrics dashboard (system, trading, signals, ML, cache) |
| `/scheduler_status` | Scheduler tasks + Signal Queue status |
| `/cleanup_signals` | Hapus signal records yang incomplete |
| `/backfill_performance` | Rebuild profit feedback tables dari trade history |
| `/reset_skip` | Reset skipped/invalid pairs blacklist (price poller) |
| `/reset_drawdown` | Reset equity peak + re-enable auto-trade setelah circuit breaker |
| `/dashboard` | Buka link Crypto Dashboard di browser |

### Monitoring SL/TP

| Command | Deskripsi |
|---------|-----------|
| `/monitor` | Lihat posisi yang sedang dipantau dengan SL/TP levels |

---

## 🎨 Telegram Inline Buttons

Selain command, banyak fitur tersedia via inline keyboard:

| Tombol | Aksi |
|--------|------|
| 📊 Market | Trigger `/scan` |
| 💼 Portfolio | Trigger `/portfolio` |
| 🔔 Alerts | Trigger `/notifications` |
| ⚙️ Settings | Buka settings panel |
| 📈 Signal | Trigger `/signals` |
| 💰 Price | Prompt input pair untuk `/price` |
| 🟢 BUY/SELL via Scalper | Route ke `/s_buy` / `/s_sell` (bukan execute langsung) |

Tombol BUY/SELL hanya muncul kalau:
- Pair valid di Indodax (cek `/api/summaries`)
- Untuk BUY: ada saldo IDR
- Untuk SELL: ada saldo coin atau scalper local position > 0

---

## 📋 Pair Format

Bot menerima format apapun dan otomatis normalize:

| Input | Hasil |
|-------|-------|
| `btcidr` | ✅ |
| `BTC/IDR` | ✅ |
| `BTCIDR` | ✅ |
| `btc` | ✅ (auto append `idr`) |
| `BTC` | ✅ |

Untuk Indodax API internal: `btc_idr`, `pippin_idr` — bot handle conversion otomatis.

---

## ⚠️ Catatan Penting

1. **DRY RUN default.** Setiap startup bot otomatis set `AUTO_TRADE_DRY_RUN=true`. Untuk real trading, **WAJIB** lewat Scalper (`/s_buy`, `/s_sell`).

2. **Akses control default-deny.** User non-admin harus `/register <invite_code>` dulu sebelum bisa pakai bot.

3. **Notifikasi otomatis bisa di-mute** dengan `/signal off` tapi command manual (`/signal`, `/signals`) tetap aktif.

4. **Watchlist ≠ Auto-trade pairs.** Dua list berbeda:
   - Watchlist: untuk monitoring + scalping (`/watch`)
   - Auto-trade: untuk eksekusi otomatis (`/add_autotrade`)

5. **Cooldown:** Signal punya cooldown 5 menit per pair+type untuk prevent spam.

6. **Circuit breaker:** Kalau drawdown > `MAX_DRAWDOWN_PCT` (default 20%), auto-trade auto-stop. Reset dengan `/reset_drawdown`.
