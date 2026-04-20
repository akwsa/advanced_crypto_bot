# Advanced Crypto Bot Project Structure

This document maps the repository as it exists today and is intended to be a quick orientation guide for contributors and operators.

## Repository Layout

```text
advanced_crypto_bot/
├── README.md                     # GitHub-facing overview
├── bot.py                        # Main application entry point
├── PROJECT_STRUCTURE.md          # This file
├── COMMAND_REFERENCE.md          # Command-oriented quick reference
├── PANDUAN_SIGNAL.md             # Signal usage guide
├── docker-compose.yml            # Container orchestration
├── Dockerfile                    # Primary image build
├── deploy_vps.sh                 # VPS deployment helper
├── crypto-bot.service            # systemd service example
│
├── core/                         # Shared configuration, DB, utils, logging, enhancement engine
├── api/                          # Exchange API integrations
├── analysis/                     # Technical analysis and ML models
├── autotrade/                    # Trading engine, risk, portfolio, monitoring
├── autohunter/                   # Smart hunter integration and hunting logic
├── scalper/                      # Scalper module and command handling
├── signals/                      # Signal quality engine, queueing, persistence
├── cache/                        # In-memory and Redis-backed cache/state
├── workers/                      # Background workers and polling loop
├── monitoring/                   # Monitoring-related assets
│
├── Documents/                    # Historical docs, guides, audits, and fix notes
├── deprecated.archived/          # Preserved legacy scripts and archived tooling
├── data/                         # Runtime SQLite and generated data (gitignored)
├── logs/                         # Runtime logs (gitignored)
├── models/                       # Trained model artifacts (mostly gitignored)
└── venv/                         # Local virtual environment (gitignored)
```

## Package Roles

### `core/`

- `config.py`: central runtime configuration and environment-driven settings
- `database.py`: SQLite database access
- `logger.py`: application logging setup
- `utils.py`: shared formatting and helper functions
- `signal_enhancement_engine.py`: late-stage signal enhancement logic

### `api/`

- `indodax_api.py`: primary Indodax REST wrapper

### `analysis/`

- `technical_analysis.py`: indicator calculations
- `ml_model.py`, `ml_model_v2.py`, `ml_model_v3.py`: signal prediction models
- `support_resistance.py`: S/R detection
- `signal_analyzer.py`, `analyze_signals.py`: analysis helpers for command responses

### `autotrade/`

- `trading_engine.py`: TA + ML merge into base signal decisions
- `risk_manager.py`: position and loss-limit controls
- `portfolio.py`: portfolio exposure tracking
- `price_monitor.py`: SL/TP and price alert monitoring

### `autohunter/`

- smart-hunter focused logic and integration used by the main bot

### `scalper/`

- dedicated scalper commands and fast manual workflow helpers

### `signals/`

- `signal_quality_engine.py`: confluence scoring and quality rejection layer
- `signal_filter_v2.py`: additional signal filtering logic
- `signal_queue.py`: scheduling and queue support
- `signal_db.py`: signal persistence

### `cache/`

- local cache and Redis-backed cache/state managers

### `workers/`

- asynchronous background worker support
- market polling loop used by the bot runtime

## Runtime Flow

At a high level:

1. `bot.py` boots shared services and Telegram handlers.
2. `workers/price_poller.py` and runtime callbacks keep market data fresh.
3. `analysis/` and `autotrade/trading_engine.py` build the base recommendation.
4. `signals/signal_quality_engine.py`, support/resistance validation, and enhancement filters refine the output.
5. `autotrade/price_monitor.py` and `autotrade/risk_manager.py` govern alerts and execution safety.

## Documentation Notes

- `Documents/` contains the deeper project history, fix logs, audits, and implementation notes.
- The root docs should stay concise and GitHub-friendly.
- Operational output such as databases, logs, and local secrets are intentionally excluded from Git.

## Recommended Starting Points

- Start with `README.md` for setup and overview.
- Read `bot.py` if you need the full orchestration path.
- Use `PROJECT_STRUCTURE.md` when mapping modules.
- Use `Documents/README.md` when you need historical context or detailed guides.

Last updated: April 2026
