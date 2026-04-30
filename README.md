# 🤖 Advanced Crypto Trading Bot

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)
[![Indodax](https://img.shields.io/badge/Exchange-Indodax-orange.svg)](https://indodax.com/)
[![AI](https://img.shields.io/badge/AI-Claude%20API-purple.svg)](https://www.anthropic.com/)

Trading bot canggih untuk cryptocurrency exchange **Indodax** dengan integrasi **Machine Learning**, **AI enhancement (Claude API)**, dan **auto-trading**. Bot ini menggunakan analisis teknikal multi-timeframe, ML models V3/V4, dan AI reasoning untuk menghasilkan signal trading berkualitas tinggi.

---

## ✨ Fitur Utama

### 📊 **Signal Generation**
- **Technical Analysis**: RSI, MACD, Bollinger Bands, ATR, ADX, Volume analysis
- **Multi-Timeframe**: 1m, 5m, 15m, 1h untuk analisis komprehensif
- **ML Models**: 3 versi ML model (V2, V3 dengan backtesting, V4 trade outcome-based)
- **AI Enhancement**: Integrasi Claude API untuk reasoning & confidence adjustment
- **Signal Quality Engine**: Scoring 0-100 dengan risk/reward validation
- **Support/Resistance Detection**: Automatic S/R level detection

### 💹 **Auto-Trading**
- **Auto Buy/Sell**: Eksekusi otomatis berdasarkan signal berkualitas tinggi
- **Risk Management**: Portfolio exposure limit, position sizing, max concurrent positions
- **Market Regime Detection**: Trending/Ranging/Volatile/Choppy detection
- **Auto-Sell Monitoring**: Take profit, stop loss, trailing stop automation
- **Dry-Run Mode**: Simulasi trading tanpa risiko

### 🎯 **Specialized Modules**
- **Scalper Module**: High-frequency trading untuk profit 0.5-2%
- **Smart Hunter**: Momentum hunting untuk low-cap coins (target 3-5%)
- **Ultra Hunter**: Aggressive hunting untuk extreme opportunities (target 5-10%)

### 🤖 **Telegram Integration**
- **93 Commands**: Lengkap untuk monitoring, trading, dan management
- **Inline Keyboards**: Interactive UI untuk quick actions
- **Real-time Notifications**: Signal alerts, trade confirmations, portfolio updates
- **Notification Filters**: BUY-only, SELL-only, actionable, atau all signals

### 💾 **Infrastructure**
- **Redis Caching**: Price cache, state management, task queue
- **SQLite Database**: Signals, trades, positions, performance metrics
- **Background Workers**: Async workers, price polling, signal queue
- **WebSocket**: Real-time price updates dari Indodax

---

## 📚 Dokumentasi Canonical

Untuk navigasi codebase yang efisien, ikuti **layered read approach**:

### **Layer 1: System Overview**
📄 **[SYSTEM_MAP.md](SYSTEM_MAP.md)** - Module index, dependencies, entry points
- Baca ini **PERTAMA** untuk memahami arsitektur
- Indeks lengkap semua modul (core, analysis, autotrade, signals, dll)
- Dependencies tree & critical paths
- Quick navigation commands

### **Layer 2: Operations & Flow**
📄 **[OPERATIONS_FLOW_ALGORITHMA.md](OPERATIONS_FLOW_ALGORITHMA.md)** - Runtime flows & algorithms
- Startup sequence detail
- Signal generation pipeline (8 steps)
- Auto-trading flow dengan validation gates
- Market regime detection
- Test policy per modul

### **Layer 3: Command Reference**
📄 **[COMMAND_REFERENCE.md](COMMAND_REFERENCE.md)** - Telegram commands & callbacks
- Complete reference 93 commands
- Organized by category (signals, trading, portfolio, dll)
- Callback handlers & inline keyboards
- Error handling policies

### **Layer 4: Coding Standards**
📄 **[DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md)** - Code quality & best practices
- Mandatory file header format
- Docstring standards
- Naming conventions
- Error handling & logging
- Git commit message format
- Anti-patterns to avoid

### **Layer 5: Specific Code**
Setelah baca 4 layer di atas, baru baca kode spesifik yang dibutuhkan:
```bash
# Cari fungsi/class dengan grep
grep -rn "class SignalEnhancementEngine" advanced_crypto_bot/

# Read snippet ±20 baris di sekitar target
# Jangan read full file besar!
```

---

## 🚀 Quick Start

### 1. **Prerequisites**
```bash
# Python 3.9+
python3 --version

# Redis server
redis-server --version

# TA-Lib (for technical indicators)
# Install dari source atau package manager
```

### 2. **Installation**
```bash
# Clone repository
git clone https://github.com/akwsa/advanced_crypto_bot.git
cd advanced_crypto_bot

# Install dependencies
pip install -r requirements.txt

# Setup TA-Lib (jika belum)
# Ubuntu/Debian:
sudo apt-get install ta-lib
# macOS:
brew install ta-lib
```

### 3. **Configuration**
```bash
# Copy .env.example ke .env
cp .env.example .env

# Edit .env dengan API keys Anda:
# - TELEGRAM_BOT_TOKEN (dari @BotFather)
# - INDODAX_API_KEY & INDODAX_SECRET_KEY
# - ANTHROPIC_API_KEY (Claude API)
# - REDIS_HOST & REDIS_PORT
```

### 4. **Run Bot**
```bash
# Start Redis (terminal 1)
redis-server

# Start bot (terminal 2)
cd advanced_crypto_bot
python3 bot.py
```

### 5. **Telegram Setup**
```
1. Buka Telegram, cari bot Anda
2. /start - Mulai bot
3. /watch btcidr - Watch Bitcoin
4. /signal btcidr - Generate signal
5. /help - Lihat semua commands
```

---

## 📖 Usage Examples

### **Basic Signal Generation**
```
/watch btcidr ethidr dogebidr
/signals
→ Bot akan generate signals untuk semua watched pairs
```

### **Auto-Trading Setup**
```
/add_autotrade btcidr
/list_autotrade
/start_trading
→ Bot akan auto-trade untuk pairs yang ditambahkan
```

### **Notification Filters**
```
/notif_buy
→ Hanya notif BUY signals (filter SELL & HOLD)

/notif_status
→ Cek notification settings
```

### **Portfolio & Performance**
```
/balance
→ Cek saldo Indodax

/portfolio
→ Lihat holdings

/performance
→ P&L, win rate, total trades
```

### **Scalper Module**
```
/s_menu
→ Scalper main menu

/s_analisa btcidr
→ Analisa scalping opportunity

/s_posisi
→ Lihat scalp positions
```

---

## 🏗️ Architecture

```
advanced_crypto_bot/
├── 🔧 core/              # Config, Database, Logger, Utils
├── 📊 analysis/          # Technical Analysis, ML Models (V2/V3/V4)
├── 💹 autotrade/         # Trading Engine, Risk Manager, Portfolio
├── 🎯 autohunter/        # Smart & Ultra Profit Hunters
├── ⚡ scalper/           # Scalping Module
├── 📡 signals/           # Signal Pipeline, Quality Engine, Formatter
├── 🔌 api/               # Indodax API, WebSocket
├── 💾 cache/             # Redis Price Cache, State Manager
├── 👷 workers/           # Background Workers, Price Poller
├── 🤖 bot_parts/         # Telegram UI, Charts, Formatting
├── 🧪 tests/             # Unit & Integration Tests
└── 📈 monitoring/        # Runtime Observers
```

**Entry Point:** `bot.py` (AdvancedCryptoBot class)

**Key Flows:**
1. **Signal**: Price Update → Signal Pipeline → TA + ML + AI → Quality Check → Telegram
2. **Trading**: Signal → Risk Validation → Market Regime Check → Order Execution → Portfolio Update
3. **Auto-Sell**: Position Monitor → P&L Check → TP/SL Trigger → Sell Order → DB Update

---

## 🧪 Testing

```bash
# Test specific module
pytest tests/test_scalper_dryrun_positions.py -v

# Test signal pipeline
pytest tests/test_v4_integration.py -v

# Test safety
pytest tests/test_dryrun_safety.py -v

# Full test suite
pytest tests/ -v --cov=advanced_crypto_bot
```

**Test Policy:** Lihat [OPERATIONS_FLOW_ALGORITHMA.md](OPERATIONS_FLOW_ALGORITHMA.md) → Test Policy section

---

## ⚙️ Configuration

### **Environment Variables** (`.env`)
```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# Indodax API
INDODAX_API_KEY=your_api_key
INDODAX_SECRET_KEY=your_secret_key

# Claude API (AI Enhancement)
ANTHROPIC_API_KEY=your_anthropic_key

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Trading Parameters
MIN_CONFIDENCE=0.55
MIN_QUALITY_SCORE=60
MAX_POSITIONS=3
RISK_PER_TRADE=0.10
```

### **Trading Rules** (Phases)
- **Phase 1**: Baseline rules & reject filters → `PHASE1_BASELINE_AND_REJECT_RULES.md`
- **Phase 2**: Advanced rule implementation → `PHASE2_RULE_IMPLEMENTATION_SPEC.md`

---

## 🔒 Security

⚠️ **PENTING:**
- **JANGAN commit `.env`** ke Git (sudah ada di `.gitignore`)
- **JANGAN share API keys** di public
- **Gunakan dry-run mode** untuk testing sebelum live trading
- **Set position limits** sesuai risk tolerance
- **Monitor portfolio** secara berkala

---

## 📊 Performance

**Signal Quality:**
- Confidence threshold: 55%+
- Quality score: 60-100
- Risk/Reward ratio: >1.5
- AI enhancement: Claude API reasoning

**Auto-Trading:**
- Max exposure: 30% per trade
- Max concurrent positions: 3
- Default risk: 10% of capital
- Take profit: Dynamic based on volatility
- Stop loss: Based on S/R levels

**Scalper:**
- Target profit: 0.5-2%
- Stop loss: <0.5%
- Timeframe: <5 min
- High volume requirement

---

## 🛠️ Development

### **Code Navigation Workflow**
```bash
# 1. Baca SYSTEM_MAP.md
cat SYSTEM_MAP.md

# 2. Grep untuk lokasi kode
grep -rn "class TradingEngine" advanced_crypto_bot/

# 3. Read snippet (jangan full file!)
# Gunakan offset untuk read ±20 baris saja

# 4. Edit dengan patch kecil
# Gunakan edit tool, jangan rewrite full file

# 5. Test fokus (bukan full suite)
pytest tests/test_<module>.py

# 6. Update docs canonical jika perlu
```

### **Git Workflow**
```bash
# Format commit message (lihat DOCUMENTATION_RULES.md)
git commit -m "feat: add new feature

Description...

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 📈 Roadmap

- [x] Technical Analysis (TA-Lib)
- [x] ML Models V2/V3/V4
- [x] AI Enhancement (Claude API)
- [x] Auto-Trading Engine
- [x] Risk Management
- [x] Scalper Module
- [x] Hunter Modules (Smart & Ultra)
- [x] Telegram Bot (93 commands)
- [x] Redis Caching
- [x] Signal Quality Engine
- [ ] Web Dashboard (TMA)
- [ ] Backtesting UI
- [ ] Multi-exchange support
- [ ] Advanced ML models (V5 dengan deep learning)
- [ ] Portfolio rebalancing automation

---

## 🤝 Contributing

Contributions welcome! Please:
1. Read [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md) untuk coding standards
2. Buat branch: `git checkout -b feature/nama-fitur`
3. Commit dengan format yang benar
4. Update docs canonical jika perlu
5. Submit PR dengan deskripsi jelas

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file

---

## 🙏 Credits

- **TA-Lib**: Technical analysis library
- **Python Telegram Bot**: Telegram bot framework
- **Anthropic Claude**: AI enhancement
- **Indodax**: Indonesian crypto exchange
- **Redis**: Caching & state management

---

## ⚠️ Disclaimer

**TRADING CRYPTOCURRENCY MEMILIKI RISIKO TINGGI!**

Bot ini disediakan "as-is" tanpa warranty. Gunakan dengan risiko Anda sendiri:
- Hanya trade dengan uang yang sanggup Anda kehilangan
- Selalu gunakan **dry-run mode** untuk testing
- Set **position limits** yang konservatif
- Monitor portfolio secara aktif
- Pahami risiko market volatility

**Author tidak bertanggung jawab atas kerugian trading.**

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/akwsa/advanced_crypto_bot/issues)
- **Docs**: Baca canonical docs di repository
- **Email**: wkagung@gmail.com

---

**Happy Trading! 🚀📈**

Built with ❤️ using Python, ML, and AI
