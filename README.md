# Advanced Crypto Bot

Advanced crypto trading bot for Indodax with Telegram control, technical analysis, machine-learning-assisted signals, auto-trading workflows, and layered risk checks.

## Highlights

- Telegram bot interface for monitoring, signal lookup, watchlists, and trading commands
- Signal pipeline that combines technical analysis, ML prediction, quality filters, support/resistance validation, and enhancement checks
- Auto-trading flow with dry-run mode, risk manager, price monitoring, and partial take-profit handling
- Modular project structure with separate packages for `analysis`, `autotrade`, `signals`, `workers`, `cache`, and `core`
- Deployment assets for VPS, Docker, and service-based hosting

## Main Components

- `bot.py`: main application entry point and orchestration layer
- `analysis/`: technical analysis, ML models, support/resistance detection, signal analysis helpers
- `autotrade/`: trading engine, risk manager, portfolio logic, and price monitoring
- `signals/`: signal persistence, queueing, and quality engine
- `workers/`: background workers and price polling
- `api/`: Indodax API integration
- `core/`: config, database wrapper, utilities, logging, and signal enhancement engine
- `Documents/`: implementation notes, deployment guides, fix logs, and technical references

## Signal Flow

The core signal path lives in `bot.py` and follows this sequence:

1. Load or validate historical market data.
2. Fetch the freshest available price.
3. Calculate technical-analysis signals.
4. Run ML prediction with fallback to TA-only mode if needed.
5. Merge TA + ML through the trading engine.
6. Stabilize abrupt recommendation jumps.
7. Apply volatility, regime, and signal-quality filtering.
8. Detect and validate support/resistance context.
9. Run enhancement checks such as volume, VWAP, Ichimoku, divergence, and candlestick analysis.
10. Save the final signal and use it for notifications or auto-trading decisions.

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/akwsa/advanced_crypto_bot.git
cd advanced_crypto_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a local `.env` based on `.env.example` and fill in:

- Telegram bot token
- Admin user IDs
- Indodax API credentials for real trading
- Redis and optional runtime settings if used in your setup

### 3. Run the bot

```bash
python3 bot.py
```

### 4. Useful operational files

- `start_bot.bat` / `stop_bot.bat`: Windows helpers
- `deploy_vps.sh`: VPS deployment helper
- `docker-compose.yml`: container orchestration
- `crypto-bot.service`: systemd service template

## Documentation Map

- `PROJECT_STRUCTURE.md`: current package and folder layout
- `COMMAND_REFERENCE.md`: command-oriented reference
- `PANDUAN_SIGNAL.md`: signal usage guide
- `DEPLOY_BIZNET.md`: deployment notes
- `Documents/README.md`: index of deeper technical and historical docs

## Notes

- This repository includes both runtime logic and a large amount of project documentation for fixes, investigations, and deployment history.
- Local runtime artifacts such as databases, logs, and environment secrets are ignored from Git.
- Real trading is high risk. Dry-run mode should be used first before enabling live execution.

## Repository Status

- Default branch: `main`
- Initial tagged version: `v0.1.0`
