# Project Knowledge for AI Agents

This file is the short context pack for agents working on Advanced Crypto Bot.

## Project

- Path: `/home/officer/advanced_crypto_bot/advanced_crypto_bot`
- Runtime: Python Telegram bot for Indodax crypto signals/trading.
- Current safe mode: DRY RUN.
- Main entry: `bot.py` (`AdvancedCryptoBot`).

## Architecture

- `core/config.py`: env/config/risk constants. `MAX_DRAWDOWN_PCT=0.10` is correct fraction.
- `core/database.py`: SQLite state; WAL enabled in live DBs.
- `signals/signal_pipeline.py`: end-to-end signal generation; currently the biggest signal hotspot.
- `signals/signal_quality_engine.py` + `signals/signal_rules.py`: quality gates and final actionability.
- `autotrade/trading_engine.py`: signal combination, trade eligibility, position sizing, SL/TP.
- `analysis/ml_model*.py`: ML V1-V4.
- `quant/*.py`: mean reversion, Kelly, momentum, correlation, stat arb, VaR/CVaR, GARCH, ARIMA, frontier.
- `autohunter/*` and `scalper/scalper_module.py`: additional strategies.

## Verified Baseline

- Compile check passed for core modules and tests.
- Full pytest with `/home/officer/.hermes/bin/python -m pytest -q`: `238 passed, 25 warnings`.
- Project venv `venv/bin/python` currently lacks pytest; use Hermes interpreter or install dev deps.

## Current Main Risks

1. Large files/functions: `bot.py`, `signals/signal_pipeline.py`, `scalper/scalper_module.py`.
2. ML signal imbalance history: SELL/STRONG_SELL too dominant vs BUY/STRONG_BUY; retraining and monitoring needed.
3. Thread/background task complexity; duplicate notification/race risks must be tested.
4. Telegram/Indodax rate limiting and secret handling need security hardening.
5. Static correlation groups should be replaced/augmented with dynamic correlation portfolio heat.
6. WebSocket is not the main reliable data path; REST polling fallback creates latency.

## Agent Workflow

1. Read `BMAD_AI_TEAM_PLAYBOOK.md` first.
2. Make a focused plan.
3. Change the smallest safe surface.
4. Add behavior tests.
5. Run focused tests, then full suite if possible.
6. Report risks and rollback.
