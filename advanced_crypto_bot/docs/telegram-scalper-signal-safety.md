# Telegram Signal Scalper Safety Policy

> ⚠️ **Related:** [Telegram Access Control](telegram-access-control.md) — default-deny whitelist untuk bot security.

Date: 2026-05-22

## Goal

Signal messages in Telegram may show action buttons only when the action is safe and aligned with the official Indodax state.

## Rules Implemented

1. Signal pair must be an official Indodax IDR market from `/api/summaries`.
2. BUY/STRONG_BUY signals may show `BUY <PAIR> via Scalper` when IDR balance is available, or when balance API is temporarily unavailable.
3. SELL/STRONG_SELL signals may show `SELL <PAIR> via Scalper` only when one of these is true:
   - Indodax balance has a non-zero coin amount for that pair.
   - Scalper local position has a non-zero amount for that pair.
4. Signal buttons route only to existing Scalper callbacks:
   - `s_buy:<pair>`
   - `s_sell:<pair>`
5. Buttons do not execute orders directly. Scalper confirmation flow remains the execution gate.
6. AutoTrade real mode is blocked and forced back to DRY RUN / NO MONEY.
7. On every `bot.py` startup, the bot automatically applies `/autotrade dryrun` semantics: AutoTrade is enabled for simulation and the persisted money mode is set to DRY RUN.
8. Smart Hunter and Ultra Hunter start commands are blocked for money execution. Trading with money is allowed only through Scalper.

## Automatic Telegram Signal Alerts

- Automatic/background signal alerts pushed to Telegram are locked to actionable signals: `BUY`, `STRONG_BUY`, `SELL`, and `STRONG_SELL`.
- `/signal on` enables actionable automatic pushes. The confirmation message explicitly says `BUY` / `STRONG_BUY` and `SELL` / `STRONG_SELL` will be sent automatically.
- `HOLD` may still be processed internally, saved, or used by trading logic, but it is not pushed as an automatic Telegram signal alert.
- Legacy notification modes such as `all`, `buy`, `sell`, or `actionable` no longer change automatic alert direction; automatic alerts are actionable-only.
- HOLD output is available only when the user explicitly calls manual commands such as `/signal hold`.
- Blocked HOLD background alerts do not consume notification cooldown, so a later BUY/SELL for the same pair can still be pushed.

## Manual Signal Filter Commands

- `/signal buy` and `/signal_buy` now read the latest saved watchlist signals from `data/signals.db`, then send only `BUY` / `STRONG_BUY` entries.
- `/signal sell` and `/signal_sell` read the same saved snapshot, then send only `SELL` / `STRONG_SELL` entries.
- `/signal hold` and `/signal_hold` read the same saved snapshot, then send only `HOLD` entries.
- These three filter commands do not scan pairs, do not generate fresh signals, and do not send a "Scanning ..." pre-message.
- If no matching signal exists, Telegram output is suppressed instead of sending diagnostic summaries, candidate lists, or opposite-direction signals.

## Safety Notes

- Signal chart now tries a normalized DB-backed history lookup when in-memory candles are flat or stale.
- Flat/synthetic history no longer produces a misleading straight-line chart; the chart is skipped instead.
- Indodax balance is cached briefly for Telegram button eligibility.
- If official pair list cannot be fetched, no action buttons are rendered.
- If Indodax balance is unavailable, SELL buttons are not shown unless Scalper has a local position.
- BUY can still appear during temporary balance API outage because it leads to Scalper confirmation, not direct execution.

## Touched Code

- `bot.py`
  - Added latest saved signal filter helpers for `/signal buy`, `/signal sell`, and `/signal hold`.
  - Added official-pair and balance helpers.
  - Added safe signal action keyboard helpers.
  - Routed single-pair and watchlist signal messages through safe button rendering.
  - Added startup dry-run enforcement so each `bot.py` process start applies `/autotrade dryrun` semantics automatically.
  - Locked `/autotrade real`, `/start_trading`, `/smarthunter on`, `/ultrahunter start`, and `ultra_start_confirm` to DRY RUN / NO MONEY behavior.
- `autotrade/runtime.py` (Sesi 5 — 2026-05-22)
  - `monitor_strong_signal` (raw HTTP path untuk watchlist alert) sekarang membangun `bot._build_signal_action_markup(signal)` dan melampirkan `markup.to_dict()` ke `payload["reply_markup"]`.
  - `check_trading_opportunity` (PTB path untuk auto-trade alert) sekarang pass `reply_markup=InlineKeyboardMarkup` ke `bot.app.bot.send_message(...)`.
  - Kedua jalur dibungkus `try/except` defensive — jika builder gagal, pesan tetap terkirim tanpa tombol.
  - Tidak ada perubahan ke safety policy `_build_signal_action_markup()` itu sendiri.

## Test Coverage

See:

- `tests/test_telegram_signal_scalper_buttons.py` — unit test `_build_signal_action_markup` (BUY/SELL/safety rules).
- `tests/test_signal_notification_controls.py` — kontrol notifikasi & filter command.
- `tests/test_signal_dispatch_buttons.py` (Sesi 5 — 2026-05-22) — verifikasi `monitor_strong_signal` & `check_trading_opportunity` melampirkan `reply_markup` sesuai safety policy.
