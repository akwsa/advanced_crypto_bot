#!/usr/bin/env python3
# Tujuan: Registrasi command Telegram untuk bot utama.
# Caller: bot.py saat startup Application.
# Dependensi: python-telegram-bot handlers, AdvancedCryptoBot methods.
# Main Functions: register_bot_handlers.
# Side Effects: Mutasi registry handler Telegram.
"""Telegram handler registration helpers for the main bot."""

import logging
import time
import traceback

from telegram import Update
from telegram.error import (
    BadRequest,
    Conflict,
    Forbidden,
    NetworkError,
    RetryAfter,
    TimedOut,
)
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from core.config import Config
from core.telegram_rate_limiter import TelegramCommandRateLimiter, rate_limited_command

logger = logging.getLogger("crypto_bot")

# Throttle repeated transient errors so logs don't get spammed.
_TRANSIENT_LOG_INTERVAL_SEC = 60
_last_transient_log_at: dict[str, float] = {}
_command_limiter: TelegramCommandRateLimiter | None = None


def _should_log_transient(key: str) -> bool:
    now = time.time()
    last = _last_transient_log_at.get(key, 0.0)
    if now - last >= _TRANSIENT_LOG_INTERVAL_SEC:
        _last_transient_log_at[key] = now
        return True
    return False


def _build_error_handler(bot):
    async def error_handler(update, context):
        err = context.error
        # Transient / expected errors -> single-line throttled log, no admin spam.
        if isinstance(err, Conflict):
            if _should_log_transient("conflict"):
                logger.warning(
                    "⚠️ Telegram Conflict: another bot instance is polling getUpdates "
                    "(suppressing similar logs for %ds). Kill duplicate processes.",
                    _TRANSIENT_LOG_INTERVAL_SEC,
                )
            return
        if isinstance(err, (NetworkError, TimedOut)):
            if _should_log_transient(type(err).__name__):
                logger.warning("⚠️ Telegram %s: %s", type(err).__name__, err)
            return
        if isinstance(err, RetryAfter):
            logger.warning("⚠️ Telegram RetryAfter: retry in %ss", getattr(err, "retry_after", "?"))
            return
        if isinstance(err, Forbidden):
            logger.warning("⚠️ Telegram Forbidden: %s", err)
            return
        if isinstance(err, BadRequest):
            logger.warning("⚠️ Telegram BadRequest: %s", err)
            return

        # Unknown / serious error -> full stacktrace + user feedback + admin DM.
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        logger.error("❌ Unhandled exception in handler: %s\n%s", err, tb)

        # Try to inform the user that triggered the update.
        try:
            if isinstance(update, Update) and update.effective_chat is not None:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Internal error, please try again. Admin has been notified.",
                )
        except Exception as send_err:
            logger.debug("Failed to send error feedback to user: %s", send_err)

        # Notify admins (truncate stacktrace to avoid Telegram length limit).
        try:
            update_repr = ""
            if isinstance(update, Update):
                if update.effective_user is not None:
                    update_repr += f"user={update.effective_user.id} "
                if update.effective_message is not None and update.effective_message.text:
                    txt = update.effective_message.text[:200]
                    update_repr += f"text={txt!r}"
            tb_short = tb[-1500:]
            msg = (
                "🚨 <b>Bot Error</b>\n"
                f"<code>{type(err).__name__}: {str(err)[:300]}</code>\n"
                f"{update_repr}\n\n"
                f"<pre>{tb_short}</pre>"
            )
            if hasattr(bot, "_send_telegram_admins"):
                bot._send_telegram_admins(msg)
        except Exception as notify_err:
            logger.debug("Failed to notify admins: %s", notify_err)

    return error_handler


def _guard_callback(bot, command, callback, allow_unauthorized=False):
    async def guarded(update, context):
        if not allow_unauthorized:
            ok = await bot._require_authorized(update, context)
            if not ok:
                return
        return await callback(update, context)

    guarded.__name__ = getattr(callback, "__name__", f"guarded_{command}")
    return guarded


def _register_command_group(app, commands, bot=None, allow_unauthorized=None):
    allow_unauthorized = set(allow_unauthorized or [])
    for command, callback in commands:
        handler_callback = callback
        if bot is not None:
            handler_callback = _guard_callback(
                bot,
                command,
                callback,
                allow_unauthorized=command in allow_unauthorized,
            )
        if _command_limiter is not None:
            handler_callback = rate_limited_command(command, handler_callback, limiter=_command_limiter)
        app.add_handler(CommandHandler(command, handler_callback))


def register_bot_handlers(bot):
    """Register all Telegram handlers for the main bot."""
    global _command_limiter

    app = bot.app
    _command_limiter = TelegramCommandRateLimiter(
        per_command_seconds=getattr(Config, "TELEGRAM_COMMAND_RATE_LIMIT_SECONDS", 2.0)
    )
    bot.telegram_command_rate_limiter = _command_limiter

    # Global error handler (filters transient noise, notifies admins on serious errors).
    app.add_error_handler(_build_error_handler(bot))

    _register_command_group(app, [
        ("start", bot.start),
        ("help", bot.help),
        ("menu", bot.menu),
        ("settings", bot.settings),
        ("register", bot.register_access),
    ], bot=bot, allow_unauthorized={"register"})

    _register_command_group(app, [
        ("watch", bot.watch),
        ("unwatch", bot.unwatch),
        ("list", bot.list_watch),
        ("clear_watchlist", bot.clear_watchlist),
        ("refresh_watchlist", bot.refresh_watchlist),
        ("cleanup_signals", bot.cleanup_signals),
        ("backfill_performance", bot.backfill_performance),
        ("reset_skip", bot.reset_skip),
        ("reset_drawdown", bot.cmd_reset_drawdown),
    ], bot=bot)

    _register_command_group(app, [
        ("price", bot.price),
        ("signal", bot.get_signal),
        ("signals", bot.signals),
        ("signal_buy", bot.signal_buy_only),
        ("signal_sell", bot.signal_sell_only),
        ("signal_hold", bot.signal_hold_only),
        ("signal_buysell", bot.signal_buysell),
        ("notifications", bot.notifications),
        ("alerts", bot.notifications),
        ("analyze", bot.analyze_signal),
        ("signal_notif", bot.signal_notif),
        ("notif_buy", bot.notif_buy),
        ("notif_sell", bot.notif_sell),
        ("notif_scalp", bot.notif_scalp),
        ("notif_all", bot.notif_all),
        ("notif_status", bot.notif_status),
    ], bot=bot)

    _register_command_group(app, [
        ("balance", bot.balance),
        ("portfolio", bot.portfolio),
        ("trades", bot.trades),
        ("sync", bot.sync_trades),
        ("performance", bot.performance),
        ("pair_stats", bot.pair_stats_cmd),
        ("trade_review", bot.trade_review_cmd),
        ("trade_reviews", bot.trade_reviews_recent_cmd),
        ("position", bot.position),
        ("trade", bot.trade),
        ("trade_auto_sell", bot.trade_auto_sell),
        ("cancel", bot.cancel_trade),
    ], bot=bot)

    _register_command_group(app, [
        ("status", bot.status),
        ("start_trading", bot.start_trading),
        ("stop_trading", bot.stop_trading),
        ("emergency_stop", bot.emergency_stop),
        ("metrics", bot.metrics_cmd),
        ("metric", bot.metrics_cmd),  # alias for common typo
        ("autotrade", bot.autotrade),
        ("autotrade_status", bot.autotrade_status),
        ("scheduler_status", bot.scheduler_status),
        ("set_interval", bot.set_interval),
        ("hunter_status", bot.hunter_status),
        ("ultrahunter", bot.ultra_hunter_cmd),
        ("retrain", bot.retrain_ml),
        ("backtest", bot.backtest_cmd),
        ("backtest_v3", bot.backtest_v3_cmd),
        ("dryrun", bot.dryrun_cmd),
        ("regime", bot.regime_cmd),
        ("kelly", bot.kelly_cmd),
        ("compare", bot.compare_cmd),
    ], bot=bot)

    _register_command_group(app, [
        ("signal_quality", bot.signal_quality_cmd),
        ("signal_report", bot.signal_report_cmd),
        ("add_autotrade", bot.add_autotrade),
        ("remove_autotrade", bot.remove_autotrade),
        ("list_autotrade", bot.list_autotrade),
        ("monitor", bot.monitor),
        ("set_sl", bot.set_stoploss),
        ("set_tp", bot.set_takeprofit),
        ("set_sr", bot.set_manual_sr),
        ("view_sr", bot.view_manual_sr),
        ("delete_sr", bot.delete_manual_sr),
        ("smarthunter", bot.smarthunter_cmd),
        ("smarthunter_status", bot.smarthunter_status),
        ("scan", bot.market_scan),
        ("topvolume", bot.top_volume),
        ("cmd", bot.commands_helper),
    ], bot=bot)

    if bot.scalper:
        _register_command_group(app, [
            ("s_menu", bot.scalper.cmd_menu),
            ("s_pairs", bot.scalper.cmd_pairs),
            ("s_posisi", bot.scalper.cmd_posisi),
            ("s_analisa", bot.scalper.cmd_analisa),
            ("s_buy", bot.scalper.cmd_buy),
            ("s_sell", bot.scalper.cmd_sell),
            ("s_sltp", bot.scalper.cmd_sltp),
            ("s_cancel", bot.scalper.cmd_cancel),
            ("s_info", bot.scalper.cmd_info),
            ("s_pair", bot.scalper.cmd_pair),
            ("s_reset", bot.scalper.cmd_reset),
            ("s_rest", bot.scalper.cmd_reset),
            ("s_portfolio", bot.scalper.cmd_portfolio),
            ("s_closeall", bot.scalper.cmd_close_all),
            ("s_riwayat", bot.scalper.cmd_riwayat),
            ("s_sync", bot.scalper.cmd_sync),
            ("s_signal_summary", bot.scalper.cmd_signal_summary),
        ], bot=bot)
        bot.app.logger.info("✅ Scalper module commands registered") if hasattr(bot.app, "logger") else None

    # TMA Dashboard
    app.add_handler(CommandHandler("dashboard", _guard_callback(bot, "dashboard", bot.cmd_dashboard)))

    # Quant Trading Commands
    try:
        from quant.quant_commands import register_quant_handlers
        register_quant_handlers(bot, app)
    except Exception as e:
        logger.warning(f"⚠️ Quant commands not registered: {e}")

    # Pair Scanner Commands (top volume / movers / scan_pairs)
    try:
        from autohunter.scanner_commands import register_scanner_handlers
        register_scanner_handlers(bot, app)
    except Exception as e:
        logger.warning(f"⚠️ Scanner commands not registered: {e}")

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _guard_callback(bot, "text", bot.handle_text_input)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/"), _guard_callback(bot, "unknown", bot.handle_unknown_command)))
    app.add_handler(CallbackQueryHandler(_guard_callback(bot, "callback", bot.callback_handler)))
