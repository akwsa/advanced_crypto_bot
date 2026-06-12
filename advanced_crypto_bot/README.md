# Advanced Crypto Trading Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-71%20passing-brightgreen)]()
[![Status](https://img.shields.io/badge/status-production%20%C2%B7%20dry--run-success)]()
[![License](https://img.shields.io/badge/license-private-lightgrey)]()

> A production-grade automated trading system for the [Indodax](https://indodax.com) exchange, with a layered ML pipeline, multi-timeframe analysis, and a real-time Telegram interface. Currently running on a Google Cloud VM in dry-run mode.

This repository is a working personal project — not a tutorial, not a course, not financial advice. The goal is to learn how to build and operate a real production ML pipeline end-to-end: data ingestion, feature engineering, model training, signal generation, risk management, and live deployment.

---

## Why this exists

Most "trading bot" repos on GitHub are notebook-quality demos that never run in production. This one does:

- Polls real prices from Indodax every 3-5 seconds across 60+ pairs
- Persists 180k+ price ticks in SQLite for ML training
- Runs four layered ML models (V1/V2/V3/V4) with a fallback strategy
- Sends real-time signals to a Telegram bot with full command interface
- Survives crashes, restarts, and full VM reboots via systemd
- Has a circuit breaker that halts trading when drawdown exceeds 10%

It is **NOT** a get-rich-quick tool. The real-trading path is locked behind a manual Scalper module. AutoTrade runs in DRY RUN by default and the safety policy is enforced in code (`Config.MAX_DRAWDOWN_PCT = 0.10`).

---

## System overview

```
   ┌─────────────────────────────────────────────────────────────┐
   │                     Indodax REST API                        │
   │  (60+ pairs · ticker, depth, trades · ~3-5s polling)        │
   └──────────────────────────┬──────────────────────────────────┘
                              │
              ┌───────────────▼───────────────┐
              │      Price Poller Worker      │
              │   (cascading volume parser)   │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   SQLite price_history table  │
              │       (~180k+ ticks)          │
              └───────────────┬───────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
   ┌────────▼─────┐  ┌────────▼─────┐  ┌────────▼─────┐
   │   ML V2      │  │  ML V1       │  │  Quant       │
   │ (primary)    │  │ (fallback)   │  │ (mean rev,   │
   │              │  │              │  │  Kelly,      │
   │  Random      │  │  Random      │  │  momentum,   │
   │  Forest      │  │  Forest      │  │  stat arb)   │
   └────────┬─────┘  └────────┬─────┘  └────────┬─────┘
            └─────────────────┼─────────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   Trading Engine (combines    │
              │   ML + TA + Quant verdicts)   │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  Signal Quality Engine V3     │
              │  - Mean Reversion check       │
              │  - HTF (1h) Trend Filter      │
              │  - Confluence Score (0-N)     │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   Support/Resistance Filter   │
              └───────────────┬───────────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
┌──────▼──────┐       ┌───────▼──────┐       ┌──────▼──────┐
│  Telegram   │       │  AutoTrade   │       │   Scalper   │
│  Notifier   │       │  (DRY RUN)   │       │  (REAL $)   │
└─────────────┘       └──────────────┘       └─────────────┘
```

---

## Highlights

| Module                 | What it does                                                             |
|------------------------|--------------------------------------------------------------------------|
| **Price Poller**       | Async REST polling, cascading volume normalization across pair currencies |
| **ML V2 (primary)**    | RandomForest multi-class, predicts BUY / SELL / HOLD                     |
| **ML V1 (fallback)**   | Older binary model used when V2 is uncertain or training data is sparse  |
| **ML V3**              | Backtesting + Bayesian Kelly position sizing (research only)             |
| **ML V4**              | Outcome-confidence boost, takes (signal_price, ml_confidence, recommendation, hour, dayofweek, symbol) and adjusts confidence |
| **Quality Engine V3**  | Multi-timeframe confluence scoring with HTF trend filter (1h resampled)  |
| **AutoTrade**          | Locked to DRY RUN; logs would-be entries without placing orders          |
| **Smart / Ultra Hunter** | Two distinct exit strategies (aggressive partial-sell vs conservative)  |
| **Scalper**            | Only path to real-money trades; manual confirm + position size guard     |
| **Risk Manager**       | Stop loss, take profit, trailing stop, drawdown circuit breaker          |
| **Telegram Interface** | 80+ commands (status, autotrade dryrun, stats, logs, halt, resume, ...)  |

---

## Tech stack

- **Language**: Python 3.10+
- **ML / Quant**: scikit-learn, pandas, numpy, ta-lib indicators
- **Data**: SQLite (price history, trades, model metadata), Redis (signal queue, optional)
- **Network**: requests, aiohttp, rss-parser
- **Bot framework**: python-telegram-bot
- **Web layer**: FastAPI dashboard (port 8091) + legacy TMA (8090)
- **Ops**: systemd, tmux, structured logging, GCP Compute Engine
- **Testing**: pytest (71 tests passing)

---

## ML pipeline — recent overhaul (June 2026)

A 3-week investigation found and fixed three foundational issues that were silently degrading model quality for months:

### 1. Volume = 0 in the entire feature set

The Indodax `get_ticker` endpoint returns volume per pair (`vol_btc`, `vol_eth`, `vol_idr`, `vol_doge`, ...) — **not** a generic `volume` field. The legacy code only checked three hard-coded names, so 180,903 rows in `price_history` had `volume = 0.0`. The model had been training on noise for that feature.

**Fix**: cascading fallback in `api/indodax_api.py`:
```
vol_idr → vol_<basecoin> → any vol_* → legacy fallback
```

### 2. "Multi-timeframe analysis" that wasn't multi-timeframe

The Quality Engine docstring claimed "15m primary + 4h trend filter". In reality, both timeframes were computed on the same 15m dataframe — no resampling, no actual higher-timeframe view.

**Fix**: real tick → 1h candle resampling via pandas, SMA fast=5 / slow=10, alignment score wired into the confluence scorer (`signals/signal_quality_engine.py::compute_higher_tf_trend`).

### 3. ML lookback was only 200 ticks

With 3-5 second polling, 200 ticks ≈ 10-16 hours of real history. Far too short for a 1h SMA filter to ever reach `htf_candles >= 11` (SMA slow + 1).

**Fix**: `Config.HISTORICAL_DATA_LIMIT = 500` (env-overridable), routed through `_load_historical_data` and `_update_historical_data`.

All three changes are live in commit [`4eb1388`](../../commit/4eb1388) with full regression tests.

---

## Quick start

> Requires Python 3.10+, a Telegram bot token, and (optionally) Indodax API keys.

```bash
git clone <repo_url>
cd advanced_crypto_bot/advanced_crypto_bot

pip install -r requirements.txt

cp .env.example .env
# Edit .env — see Configuration below

python bot.py
```

The bot connects to Telegram and starts polling. Send `/start` to your bot to register, then `/help` for the command list.

---

## Configuration (.env)

```env
# Telegram (REQUIRED)
TELEGRAM_BOT_TOKEN=...
ADMIN_IDS=123456789                  # comma-separated Telegram user IDs
TELEGRAM_INVITE_CODE=invite-secret   # for non-admin user registration

# Indodax (OPTIONAL — only for real trading via Scalper)
INDODAX_API_KEY=
INDODAX_SECRET_KEY=

# ML pipeline tuning
HISTORICAL_DATA_LIMIT=500            # ticks per pair held in memory + DB query
ML_CONFIDENCE_THRESHOLD=0.55
HTF_TREND_THRESHOLD_PCT=1.0

# Safety
MAX_DRAWDOWN_PCT=0.10                # 10% max drawdown circuit breaker
DAILY_LOSS_LIMIT_USD=...
```

Full schema in `core/config.py`.

---

## Telegram commands (selection)

| Command              | Effect                                              |
|----------------------|-----------------------------------------------------|
| `/start`             | Register / re-auth                                  |
| `/status`            | System health, position count, P&L                  |
| `/autotrade dryrun`  | Toggle dry-run autotrade on/off                     |
| `/scan <pair>`       | Run signal pipeline manually for one pair           |
| `/stats`             | ML model performance, signal distribution           |
| `/logs <n>`          | Tail last n log lines                               |
| `/halt`              | Emergency stop (cancels orders, blocks new entries) |
| `/resume`            | Re-enable trading after `/halt`                     |
| `/scalper <pair>`    | Open manual scalp UI for a pair (REAL money path)   |

80+ commands total. See `bot.py` and `commands/` for the full surface.

---

## Project layout

```
advanced_crypto_bot/
├── bot.py                     # Main Telegram event loop (~9.7k LOC, being extracted)
├── api/
│   └── indodax_api.py         # REST client + cascading volume normalization
├── core/
│   ├── config.py              # All Config.* constants
│   └── database.py            # SQLite layer (price_history, trades, models)
├── ml/
│   ├── ml_model.py            # V1 (binary RandomForest)
│   ├── ml_model_v2.py         # V2 (multi-class, primary)
│   ├── ml_model_v3.py         # Backtesting + Kelly
│   └── ml_model_v4.py         # Outcome confidence booster
├── quant/                     # Mean reversion, Kelly, momentum, stat arb
├── signals/
│   ├── signal_pipeline.py     # df → TA → ML → trading_engine → quality → SR → notify
│   ├── signal_quality_engine.py   # Multi-TF confluence, HTF trend filter
│   └── signal_formatter.py    # Telegram message formatting
├── scalper/                   # Manual / semi-auto real-trading module
├── workers/
│   ├── price_poller.py        # Async REST polling
│   └── ml_trainer.py          # Periodic retraining
├── tests/                     # pytest suite (71 tests)
├── data/                      # SQLite DB (gitignored)
└── logs/                      # Rotating logs (gitignored)
```

---

## Testing

```bash
pytest -q
# 71 passed in ~110s (split into 3 batches due to import overhead)
```

Highlights:
- Volume normalization edge cases (`tests/test_indodax_ticker_volume_normalization.py`)
- HTF trend filter logic (`tests/test_signal_quality_engine_htf_trend.py`)
- Risk manager boundary conditions (drawdown, daily loss, position size)
- Signal pipeline contract tests (input → expected recommendation)

---

## What this project taught me

- Operating a long-running stateful Python service in production (systemd + tmux + log rotation)
- Debugging ML feature degradation when input data is silently corrupt (the volume = 0 bug)
- Designing safety policies that cannot be bypassed accidentally (DRY RUN as default + drawdown circuit breaker)
- Telemetry and observability without buying a SaaS tool (structured logs + Telegram queries)
- Dealing with API quirks at scale (Indodax volume field naming, rate limits, 5xx storms)
- Coordinating multiple AI agents (Claude Code, Codex, Hermes Agent) to parallelize work on a 9.7k-LOC file

---

## Status & disclaimer

- **Status**: Active development. Service running on GCP, dry-run only.
- **Disclaimer**: Not financial advice. The bot is a learning project. Real trading is locked behind a manual Scalper module that requires explicit confirmation per trade. Use at your own risk if you fork it.
- **Roadmap**: V2 retraining with real volume features (after enough post-fix data accumulates), gradual extraction of `bot.py` into smaller modules, FastAPI dashboard hardening.

---

## Author

Built and operated solo by [@akwsa](https://github.com/akwsa).
Open to remote roles in **Backend Engineering · Machine Learning · AI Automation**.
Based in Indonesia (UTC+7), full-time available.

Get in touch via LinkedIn or email — see [profile](https://github.com/akwsa).
