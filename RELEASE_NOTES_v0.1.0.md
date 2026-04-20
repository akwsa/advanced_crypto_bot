# Release Notes - v0.1.0

Initial public baseline for the Advanced Crypto Bot repository.

## Highlights

- Telegram-driven crypto bot for Indodax monitoring and trading workflows
- Signal pipeline that combines technical analysis, ML prediction, support/resistance validation, and enhancement filters
- Dry-run and auto-trading flows with risk management and price monitoring
- Root GitHub documentation added for easier onboarding and repository navigation

## Included In This Version

### Core bot capabilities

- Main orchestration in `bot.py`
- Technical-analysis and ML signal modules in `analysis/`
- Trading, risk, portfolio, and price monitor modules in `autotrade/`
- Signal quality engine, persistence, and queueing in `signals/`
- Polling and background worker support in `workers/`

### Signal-flow fixes

- Fixed signal history handling so quality checks use the actual previous signal state
- Fixed persisted signal confidence so saved records reflect the final confidence after enhancement
- Added `HOLD TRACE` logging to make final rejection reasons easier to audit
- Added quality-engine rejection counters and rejection reason logging

### Repository improvements

- Initialized Git repository on `main`
- Added a GitHub-friendly root `README.md`
- Refreshed `PROJECT_STRUCTURE.md` to match the current codebase layout
- Added GitHub issue templates and a lightweight Actions workflow

## Known Notes

- This repository contains a large historical `Documents/` folder with implementation notes, audits, and fix logs
- Runtime databases, logs, local secrets, and environment-specific state are intentionally excluded from Git
- Live trading remains high risk and should be tested in dry-run mode first

## Suggested Next Steps

- Add repository screenshots or diagrams for Telegram command flows
- Add targeted tests for the signal pipeline and risk-manager boundaries
- Split future changes into smaller thematic commits and release tags
