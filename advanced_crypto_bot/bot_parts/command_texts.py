# Tujuan: Memusatkan teks bantuan/menu/command guide agar bot.py lebih ringkas.
# Caller: bot.AdvancedCryptoBot method wrappers untuk /help, /menu, dan /cmd.
# Dependensi: none.
# Main Functions: build_start_html, build_help_html, build_menu_markdown, build_commands_text.
# Side Effects: none (pure string builders).


TELEGRAM_BOT_COMMANDS = (
    ("start", "Buka ringkasan bot"),
    ("help", "Panduan singkat"),
    ("menu", "Menu cepat"),
    ("signal", "Sinyal pair / on-off notif"),
    ("signals", "Sinyal semua watchlist"),
    ("price", "Cek harga pair"),
    ("scan", "Scan peluang market"),
    ("balance", "Saldo dan posisi"),
    ("portfolio", "Ringkasan portfolio"),
    ("watch", "Tambah pair ke watchlist"),
    ("autotrade", "Mode auto-trade"),
    ("status", "Status sistem"),
    ("settings", "Mode dan pengaturan"),
    ("dashboard", "Buka dashboard web"),
    # Scalper module commands (handler di scalper/scalper_module.py)
    ("s_menu", "Scalper: menu utama"),
    ("s_pair", "Scalper: atur pair (list/add/remove/reset)"),
    ("s_pairs", "Scalper: daftar pair aktif"),
    ("s_analisa", "Scalper: analisa teknikal pair"),
    ("s_buy", "Scalper: buy manual pair"),
    ("s_sell", "Scalper: sell manual pair"),
    ("s_sltp", "Scalper: set TP/SL pair"),
    ("s_cancel", "Scalper: cancel TP/SL pair"),
    ("s_info", "Scalper: info posisi pair"),
    ("s_posisi", "Scalper: posisi aktif"),
    ("s_portfolio", "Scalper: portfolio ringkas"),
    ("s_riwayat", "Scalper: riwayat trade"),
    ("s_signal_summary", "Scalper: ringkasan sinyal"),
    ("s_sync", "Scalper: sync pair/posisi"),
    ("s_reset", "Scalper: reset semua posisi"),
    ("s_close_all", "Scalper: tutup semua posisi"),
    ("s_refresh", "Scalper: refresh portfolio"),
)


def _on_off(value):
    return "ON" if value else "OFF"


def build_start_html(
    first_name,
    is_admin,
    is_trading,
    is_dry_run,
    watch_count=0,
    autotrade_count=0,
    dashboard_ready=False,
):
    access_label = "Admin" if is_admin else "User"
    mode_label = "Simulasi aman" if is_dry_run else "Real money"
    trading_label = _on_off(is_trading)
    dashboard_label = "Siap" if dashboard_ready else "Belum diset"
    name = first_name or "Trader"

    return f"""
👋 <b>Halo, {name}</b>

Bot ini membantu baca peluang crypto, kirim sinyal, dan bisa menjalankan auto-trade bila kamu aktifkan.

<b>Status Sekarang</b>
• Trading otomatis: <b>{trading_label}</b>
• Mode uang: <b>{mode_label}</b>
• Watchlist: <b>{watch_count}</b> pair
• Auto-trade pair: <b>{autotrade_count}</b> pair
• Dashboard: <b>{dashboard_label}</b>
• Akses: <b>{access_label}</b>

<b>Mulai Paling Aman</b>
1. Tambah pair: <code>/watch btcidr, ethidr</code>
2. Cek sinyal: <code>/signal btcidr</code>
3. Simulasi dulu: <code>/autotrade dryrun</code>
4. Pantau hasil: <code>/balance</code>

Ketik <code>/menu</code> untuk tombol cepat atau <code>/help</code> untuk panduan singkat.
"""


def build_help_html():
    return """
📘 <b>Panduan Singkat</b>

<b>Tujuan utama</b>
Bot ini membantu kamu memilih: <b>beli</b>, <b>tunggu</b>, atau <b>jual</b>. Untuk uang asli, tetap mulai kecil dan pakai simulasi dulu.

<b>3 command paling penting</b>
• <code>/signal btcidr</code> — tanya peluang 1 coin
• <code>/signal buy</code> — tampilkan hanya pair BUY/STRONG_BUY
• <code>/signal sell</code> — tampilkan hanya pair SELL/STRONG_SELL
• <code>/signal hold</code> — tampilkan hanya pair HOLD
• <code>/signal buysell</code> — tampilkan pair BUY + SELL tanpa HOLD
• <code>/signal on|off</code> — kontrol notifikasi otomatis
• <code>/scan</code> — cari peluang dari market
• <code>/balance</code> — lihat saldo dan posisi

<b>Auto-trade aman dulu</b>
• <code>/add_autotrade btcidr, ethidr</code> — pilih pair
• <code>/autotrade dryrun</code> — simulasi tanpa uang asli
• <code>/autotrade_status</code> — pantau hasil

<b>Hunter dan scalping</b>
• <code>/smarthunter on</code> — cari peluang otomatis
• <code>/hunter_status</code> — ringkasan semua hunter
• <code>/s_menu</code> — menu scalper

<b>Butuh daftar lengkap?</b>
• <code>/menu</code> — menu ringkas
• <code>/cmd bot</code>, <code>/cmd trade</code>, <code>/cmd status</code>, <code>/cmd scalp</code>

<b>Aturan aman</b>
• Jangan langsung real trading sebelum dry-run stabil.
• Kalau sinyal <b>HOLD</b>, artinya tunggu.
• Kalau bingung, cek <code>/dashboard</code> atau <code>/status</code>.
    """


def build_main_menu_html(
    is_admin=False,
    is_trading=False,
    is_dry_run=True,
    watch_count=0,
    autotrade_count=0,
    dashboard_ready=False,
):
    trading_label = _on_off(is_trading)
    mode_label = "DRY RUN" if is_dry_run else "REAL"
    dashboard_label = "Siap" if dashboard_ready else "Belum diset"
    role_label = "Admin" if is_admin else "User"

    return f"""
📱 <b>Menu Utama</b>

<b>Ringkasan</b>
• Auto-trade: <b>{trading_label}</b>
• Mode: <b>{mode_label}</b>
• Watchlist: <code>{watch_count}</code> pair
• Auto-trade pair: <code>{autotrade_count}</code> pair
• Dashboard: <b>{dashboard_label}</b>
• Akses: <b>{role_label}</b>

Pilih tombol di bawah untuk buka bagian yang kamu butuhkan.
"""


def build_menu_section_html(section, is_admin=False, dashboard_ready=False):
    section = (section or "home").lower()

    if section == "market":
        return """
📊 <b>Market</b>

• <code>/signal btcidr</code> cek 1 pair
• <code>/signal buy</code> tampilkan hanya pair BUY/STRONG_BUY
• <code>/signal sell</code> tampilkan hanya pair SELL/STRONG_SELL
• <code>/signal hold</code> tampilkan hanya pair HOLD
• <code>/signal buysell</code> tampilkan BUY + SELL tanpa HOLD
• <code>/signal on|off</code> kontrol notif otomatis
• <code>/scan</code> cari peluang market
• <code>/topvolume</code> lihat volume ramai

Status warna:
🟢 BUY = peluang beli
🔴 SELL = tekanan jual
🟡 HOLD = tunggu
"""

    if section == "portfolio":
        return """
💼 <b>Portfolio</b>

• <code>/balance</code> saldo dan posisi
• <code>/portfolio</code> ringkasan risiko
• <code>/trades</code> riwayat trade
• <code>/pair_stats</code> performa pair

Gunakan bagian ini untuk cek hasil, bukan untuk entry buru-buru.
"""

    if section == "alerts":
        return """
🔔 <b>Alerts</b>

• <code>/notifications</code> riwayat notifikasi
• <code>/watch btcidr</code> aktifkan pantauan pair
• <code>/monitor btcidr</code> pantau level harga

Notifikasi paling berguna setelah watchlist punya pair aktif.
"""

    if section == "settings":
        dryrun_tip = "Tetap gunakan <code>/autotrade dryrun</code> sampai performa stabil."
        admin_tip = (
            "Admin bisa ubah mode lewat <code>/autotrade dryrun</code>, "
            "<code>/autotrade real</code>, atau <code>/autotrade off</code>."
            if is_admin
            else "Mode trading hanya bisa diubah admin."
        )
        dashboard_tip = (
            "Dashboard web sudah siap lewat tombol Dashboard."
            if dashboard_ready
            else "Dashboard butuh <code>DASHBOARD_URL</code> di <code>.env</code>."
        )
        return f"""
⚙️ <b>Settings</b>

• <code>/status</code> status sistem
• <code>/autotrade_status</code> status auto-trade
• <code>/cmd trade</code> detail command trading

{admin_tip}
{dashboard_tip}
{dryrun_tip}
"""

    return build_main_menu_html(is_admin=is_admin, dashboard_ready=dashboard_ready)


def build_menu_markdown():
    return """
📋 **Menu Cepat**

**Cek market**
• `/signal btcidr` - keputusan beli/tunggu/jual
• `/scan` - cari peluang dari market
• `/topvolume` - coin ramai volume

**Pantau uang**
• `/balance` - saldo dan posisi
• `/portfolio` - ringkasan risiko
• `/trades` - riwayat trade

**Auto-trade**
• `/add_autotrade btcidr, ethidr` - pilih pair
• `/autotrade dryrun` - simulasi aman
• `/autotrade_status` - status auto-trade
• `/autotrade off` - matikan

**Hunter & scalper**
• `/smarthunter on` - nyalakan Smart Hunter
• `/hunter_status` - ringkasan hunter
• `/s_menu` - menu scalper

**Bantuan lengkap**
• `/help` - panduan singkat
• `/cmd trade` - detail trading
• `/cmd status` - detail monitoring
"""


def build_commands_text(category=None):
    if not category:
        return """
📋 **PANDUAN LENGKAP COMMAND BOT**

🔹 **CARA PAKAI:**
`/cmd` - Lihat panduan ini
`/cmd bot` - Command Bot Utama
`/cmd scalp` - Command Scalper Module
`/cmd pair` - Manajemen Pair
`/cmd trade` - Trading
`/cmd status` - Status & Monitoring

_Ketik `/cmd <kategori>` untuk detail_
"""

    category = category.lower()

    if category == "bot":
        return """
🤖 **COMMAND BOT UTAMA**

👀 **Watchlist & Monitoring**
• `/watch <pair>` atau `/watch <p1>, <p2>, ...` - Add pairs to watchlist + scalper
• `/unwatch <pair>` atau `/unwatch <p1>, <p2>, ...` - Remove from watchlist
• `/list` - Lihat watchlist Anda
• `/clear_watchlist` - Hapus watchlist sendiri
• `/price <pair>` - Cek harga cepat
• `/monitor <pair>` - Set price monitoring

📊 **Analisa & Sinyal**
• `/analyze <pair>` - Analisa cepat BUY/SELL (Recomendation!)
• `/signals` - Analisa semua pair di watchlist
• `/signal <pair>` - Signal lengkap 1 pair
• `/signal buy` - Tampilkan hanya pair BUY/STRONG_BUY
• `/signal sell` - Tampilkan hanya pair SELL/STRONG_SELL
• `/signal hold` - Tampilkan hanya pair HOLD
• `/signal buysell` - Tampilkan pair BUY + SELL tanpa HOLD
• `/signal on|off` - Kontrol notifikasi otomatis
• `/scan` - Scan market untuk peluang
• `/topvolume` - Top volume pairs
• `/signal_quality <pair> [TYPE]` - Audit kualitas sinyal
• `/signal_report [BUY|SELL] [LIMIT]` - Report sinyal
• `/regime <pair>` - Market regime pair
• `/compare <days>` - Bandingkan performa periode
• `/kelly <win_rate> <avg_win> <avg_loss>` - Kelly sizing

💼 **Portfolio & Trading**
• `/balance` - Saldo & posisi
• `/trades` - Riwayat trade
• `/performance` - Statistik win rate & P&L
• `/position <pair>` - Analisa mendalam
• `/trade BUY/SELL <pair> <price> <amount>` - Trade manual
• `/trade_auto_sell <pair> <percentage>` - Set auto sell target
• `/cancel <order_id|pair>` - Cancel order
• `/sync` - Sync trade dari Indodax

⚙️ **Auto Trading**
• `/autotrade` - Toggle auto-trade mode
• `/autotrade dryrun` - Mode simulasi (RECOMMENDED)
• `/autotrade real` - Trading sungguhan
• `/autotrade off` - Matikan auto-trade
• `/autotrade_status` - Cek status
• `/set_interval <menit>` - Set interval auto-trade
• `/scheduler_status` - Check scheduled tasks

🤖 **Smart Hunter**
• `/smarthunter on` - Start Smart Hunter
• `/smarthunter off` - Stop Smart Hunter
• `/smarthunter_status` - Check positions
• `/hunter_status` - Summary hunter
• `/ultrahunter on|off|status` - Ultra Hunter control

🔧 **Admin & ML**
• `/status` - Status bot
• `/retrain` - Retrain model ML
• `/metrics` - Prometheus-like metrics
• `/cleanup_signals` - Cleanup signal DB
• `/backfill_performance` - Backfill performance
• `/reset_skip` - Reset skipped pairs
• `/emergency_stop` - Kill switch (STOP ALL)
"""

    if category == "scalp":
        return """
⚡ **COMMAND SCALPER MODULE**

📊 **Pair Management**
• `/s_pair list` - Lihat pair aktif
• `/s_pair add <pair>` - Tambah pair
• `/s_pair remove <pair>` - Hapus pair
• `/s_pair reset` - Reset ke default

🔍 **Analisa**
• `/s_analisa <pair>` - Analisa teknikal lengkap
  Contoh: `/s_analisa bridr`
  Menampilkan: RSI, MACD, MA, Bollinger, Volume

💰 **Trading Manual**
• `/s_buy <pair>` - Buy manual
• `/s_sell <pair>` - Sell manual
• `/s_sltp <pair> <tp> <sl>` - Set TP/SL
• `/s_cancel <pair>` - Cancel TP/SL
• `/s_info <pair>` - Info posisi

📋 **Monitoring**
• `/s_menu` - Menu utama scalper
• `/s_posisi` - Lihat posisi aktif
• `/s_reset` / `/s_rest` - Reset semua posisi

💡 **Tips Scalper:**
• Gunakan `/s_analisa` sebelum entry
• Set TP/SL untuk manage risk
• `/s_posisi` untuk pantau profit/loss
"""

    if category == "pair":
        return """
📈 **MANAJEMEN PAIR**

**Bot Utama - Watchlist**
• `/watch <pair>` atau `/watch <p1>, <p2>, ...` - Tambah ke watchlist
• `/unwatch <pair>` atau `/unwatch <p1>, <p2>, ...` - Hapus dari watchlist
• `/list` - Lihat semua pair Anda
• `/clear_watchlist` - Hapus semua watchlist sendiri
• `/price <pair>` - Cek harga pair
• `/signal <pair>` - Lihat signal pair
• `/monitor <pair>` - Monitor pair/posisi

**Bot Utama - Scan Pair**
• `/scan` - Scan market untuk peluang
• `/topvolume` - Pair volume tertinggi
• `/regime <pair>` - Lihat market regime pair
• `/signal_quality <pair> [TYPE]` - Audit kualitas sinyal pair

**Scalper Module:**
• `/s_pair list` - Lihat pair scalper
• `/s_pair add <pair>` - Tambah pair
• `/s_pair remove <pair>` - Hapus pair
• `/s_pair reset` - Reset ke default
• `/s_analisa <pair>` - Analisa pair scalper
• `/s_info <pair>` - Info pair/posisi scalper

**Contoh:**
```
/watch btcidr, ethidr, solidr
/signal btcidr
/regime ethidr
/s_pair add btcidr
/s_analisa btcidr
```
"""

    if category == "trade":
        return """
💰 **COMMAND TRADING**

**Bot Utama - Manual:**
• `/trade BUY <pair> <price> <idr_amount>`
• `/trade SELL <pair> <price> <coin_amount>`
• `/trade_auto_sell <pair> <percentage>` - Auto sell target
• `/cancel <order_id|pair>` - Cancel order
• `/position <pair>` - Analisa posisi mendalam
• `/sync` - Sync trade history dari Indodax
• `/balance` - Saldo & posisi
• `/trades` - Riwayat trade
• `/performance` - Statistik performa

**Bot Utama - Auto:**
• `/autotrade dryrun` - Simulasi (aman!)
• `/autotrade` - Toggle mode berjalan
• `/autotrade real` - Trading sungguhan
• `/autotrade off` - Matikan
• `/autotrade_status` - Status auto-trade
• `/scheduler_status` - Status scheduler
• `/backfill_performance` - Rebuild performance dari closed trades

**Hunter / Assisted Trading:**
• `/smarthunter on|off` - Smart Hunter
• `/smarthunter_status` - Status Smart Hunter
• `/hunter_status` - Ringkasan hunter
• `/ultrahunter on|off|status` - Ultra Hunter

**Scalper Module:**
• `/s_buy <pair>` - Buy
• `/s_sell <pair>` - Sell
• `/s_sltp <pair> <tp> <sl>` - Set TP/SL
• `/s_cancel <pair>` - Cancel TP/SL
• `/s_posisi` - Posisi aktif scalper
• `/s_portfolio` - Portfolio scalper

**Risk Management:**
• Max 25% balance per trade
• Stop loss: 2%
• Take profit: 5%
• Max 10 trades/hari
• Daily loss limit: 5%

**Contoh:**
```
/autotrade dryrun
/signal btcidr
/trade_auto_sell BTC/IDR 3
/backfill_performance
```
"""

    if category == "status":
        return """
📊 **STATUS & MONITORING**

**Bot Status:**
• `/status` - Status keseluruhan bot
• `/metrics` - Runtime metrics
• `/autotrade_status` - Status auto-trade
• `/smarthunter_status` - Smart Hunter status
• `/hunter_status` - Ringkasan hunter
• `/scheduler_status` - Scheduled tasks

**Portfolio:**
• `/balance` - Saldo & posisi terbuka
• `/trades` - Riwayat trade
• `/performance` - Win rate, P&L, Sharpe ratio

**Market & Signal:**
• `/price <pair>` - Harga saat ini
• `/signal <pair>` - Sinyal trading 1 pair
• `/signal buy` - Tampilkan hanya pair BUY/STRONG_BUY
• `/signal sell` - Tampilkan hanya pair SELL/STRONG_SELL
• `/signal hold` - Tampilkan hanya pair HOLD
• `/signal buysell` - Tampilkan pair BUY + SELL tanpa HOLD
• `/signal on|off` - Kontrol notifikasi otomatis
• `/signals` - Semua sinyal watchlist
• `/scan` - Market scanner
• `/topvolume` - Top volume pairs
• `/signal_quality <pair> [TYPE]` - Audit kualitas sinyal
• `/signal_report [BUY|SELL] [LIMIT]` - Report sinyal
• `/regime <pair>` - Market regime pair

**Maintenance:**
• `/cleanup_signals` - Cleanup signal DB
• `/backfill_performance` - Rebuild performance
• `/reset_skip` - Reset skipped pairs

**Scalper:**
• `/s_menu` - Menu scalper
• `/s_posisi` - Posisi aktif
• `/s_analisa <pair>` - Analisa pair

**Contoh Penggunaan:**
```
/status
/autotrade_status
/smarthunter_status
/backfill_performance
/balance
```
"""

    return f"""
❌ Kategori tidak dikenal: `{category}`

**Kategori tersedia:**
• `/cmd bot` - Command Bot Utama
• `/cmd scalp` - Command Scalper
• `/cmd pair` - Manajemen Pair
• `/cmd trade` - Trading
• `/cmd status` - Status & Monitoring
"""
