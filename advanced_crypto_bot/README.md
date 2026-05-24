# 🤖 Advanced Crypto Trading Bot

AI-powered crypto trading bot untuk **Indodax** dengan Telegram interface, Machine Learning, dan Quantitative Trading.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Production-brightgreen.svg)](.)

---

## 🎯 Apa Itu Bot Ini?

Bot otomatis yang:
- Pantau harga real-time crypto di Indodax (REST polling)
- Generate signal **BUY / SELL / HOLD** pakai Technical Analysis + ML (4 versi model)
- Eksekusi trade otomatis (dengan safety policy: AutoTrade dikunci **DRY RUN**, real trading hanya via Scalper)
- Kirim notifikasi & terima command via Telegram
- Risk management: stop loss, take profit, trailing stop, max drawdown circuit breaker

---

## ✨ Fitur Utama

| Modul | Fungsi |
|-------|--------|
| **AutoTrade** | Auto-trading dengan ML signals (DRY RUN only — safety policy) |
| **Smart Hunter** | Profit hunter agresif: partial sell di +3%/+5%/+8%, trailing stop |
| **Ultra Hunter** | Conservative hunter: max 2 trades/hari, TP +4%, SL -2% |
| **Scalper** | Manual & semi-auto scalping (satu-satunya jalur untuk **uang asli**) |
| **ML Models** | V1 (basic), V2 (multi-class), V3 (backtesting + Kelly), V4 (trade outcome) |
| **Quant Modules** | Mean Reversion, Bayesian Kelly, Momentum Factor, Stat Arb |
| **Risk Manager** | Stop loss, take profit, drawdown circuit breaker, daily loss limit |

---

## 🚀 Quick Start

### Prasyarat

- Python 3.10+
- Telegram Bot Token (dari [@BotFather](https://t.me/BotFather))
- Indodax account (opsional, hanya untuk real trading via Scalper)
- Redis (opsional, untuk cache & queue persistence)

### Install

```bash
# 1. Clone repo
git clone <repo_url>
cd advanced_crypto_bot/advanced_crypto_bot

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Copy template config
cp .env.example .env

# 4. Edit .env (lihat section Konfigurasi di bawah)
nano .env

# 5. Run
python3 bot.py
```

Bot jalan dengan polling Telegram. Tekan `Ctrl+C` untuk graceful shutdown.

---

## ⚙️ Konfigurasi (.env)

Variabel paling penting:

```env
# Telegram (WAJIB)
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789                  # Telegram user ID admin (boleh banyak, comma)
TELEGRAM_INVITE_CODE=invite-secret   # Kode registrasi user non-admin

# Indodax API (opsional, hanya untuk real trading)
INDODAX_API_KEY=
INDODAX_SECRET_KEY=

# Trading mode
AUTO_TRADE_DRY_RUN=true              # SELALU true di startup (di-enforce di kode)
MANUAL_TRADING_ENABLED=true
DRY_RUN=true

# Risk
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=5.0
MAX_DAILY_LOSS_PCT=5.0
MAX_DRAWDOWN_PCT=0.20

# Webhook (opsional, default polling)
WEBHOOK_ENABLED=false
WEBHOOK_URL=
WEBHOOK_PORT=8443

# Dashboard (opsional)
DASHBOARD_URL=http://your-vps:8080
```

---

## 🔒 Safety Policy

**Penting:** Bot ini dikunci dengan policy berikut:

1. **AutoTrade selalu DRY RUN.** Setiap startup memanggil `_enable_startup_dryrun_autotrade()` yang memaksa `AUTO_TRADE_DRY_RUN=true`. Command `/autotrade real` di-block.
2. **Smart Hunter & Ultra Hunter juga DRY RUN.** Command start mereka memanggil `_lock_no_money_automation()`.
3. **Real trading uang asli HANYA lewat Scalper** (`/s_buy`, `/s_sell`) dengan konfirmasi eksplisit.
4. **Default-deny access control.** User non-admin harus register via `/register <invite_code>` dulu.

Filosofinya: bot otomatis simulasi semua, manusia tetap pegang trigger eksekusi uang asli.

---

## 📚 Dokumentasi

Cuma 4 file inti (dipindah dari kondisi lama yang punya 38 file):

| File | Isi |
|------|-----|
| **README.md** (file ini) | Overview, install, config, safety |
| **[GOALS.md](GOALS.md)** | Roadmap, target metrics, timeline menuju real trading |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Struktur modul, data flow, signal pipeline, trading flow |
| **[COMMANDS.md](COMMANDS.md)** | Semua Telegram command (watchlist, signal, trade, admin) |
| **[CHANGELOG.md](CHANGELOG.md)** | History perubahan per tanggal |

Dokumen lama (analysis, catatan harian, phase reports, dll) ada di `docs/archive/`.

---

## 🧪 Testing

```bash
# Run semua test
python3 -m pytest tests/

# Atau pakai script wrapper
./scripts/test.sh

# Test spesifik
python3 -m pytest tests/test_signal_dispatch_buttons.py -v
```

Sekitar **300+ test** sudah ada (signal pipeline, dryrun safety, telegram UI, scalper, dll).

---

## 🛠️ Troubleshooting Cepat

| Masalah | Solusi |
|---------|--------|
| Bot tidak respond di Telegram | Cek `TELEGRAM_BOT_TOKEN`, cek log `data/logs/crypto_bot.log` |
| Signal tidak muncul | Pair belum di-`/watch`, atau candle < 60 (butuh ~15 menit polling awal) |
| ML model not trained | Run `/retrain` (admin), butuh 200+ candles |
| Redis warning | Redis opsional; tanpa Redis bot fallback ke dict in-memory |
| Indodax API error 403 | API tidak ekspose historical OHLC ke public; bot pakai REST polling + CoinGecko fallback |
| Memory > 2GB | Health monitor auto-restart bot (lihat `_start_health_monitor`) |

---

## 📞 Command Cepat

```
/start          - Mulai bot
/help           - Panduan lengkap
/watch btcidr   - Pantau pair
/signals        - Lihat semua signal di watchlist
/balance        - Cek saldo
/s_menu         - Menu Scalper (untuk real trading)
/status         - Status bot (admin)
```

Lihat **[COMMANDS.md](COMMANDS.md)** untuk daftar lengkap.
