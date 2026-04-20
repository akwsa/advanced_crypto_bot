#!/usr/bin/env python3
"""Telegram handler registration helpers for the main bot."""

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters


def _register_command_group(app, commands):
    for command, callback in commands:
        app.add_handler(CommandHandler(command, callback))


def register_bot_handlers(bot):
    """Register all Telegram handlers for the main bot."""
    app = bot.app

    _register_command_group(app, [
        ("start", bot.start),
        ("help", bot.help),
        ("menu", bot.menu),
    ])

    _register_command_group(app, [
        ("watch", bot.watch),
        ("unwatch", bot.unwatch),
        ("list", bot.list_watch),
        ("clear_watchlist", bot.clear_watchlist),
        ("cleanup_signals", bot.cleanup_signals),
        ("reset_skip", bot.reset_skip),
    ])

    _register_command_group(app, [
        ("price", bot.price),
        ("signal", bot.get_signal),
        ("signals", bot.signals),
        ("signal_buy", bot.signal_buy_only),
        ("signal_sell", bot.signal_sell_only),
        ("signal_hold", bot.signal_hold_only),
        ("signal_buysell", bot.signal_buysell),
        ("notifications", bot.notifications),
        ("analyze", bot.analyze_signal),
    ])

    _register_command_group(app, [
        ("balance", bot.balance),
        ("trades", bot.trades),
        ("sync", bot.sync_trades),
        ("performance", bot.performance),
        ("position", bot.position),
        ("trade", bot.trade),
        ("trade_auto_sell", bot.trade_auto_sell),
        ("cancel", bot.cancel_trade),
    ])

    _register_command_group(app, [
        ("status", bot.status),
        ("start_trading", bot.start_trading),
        ("stop_trading", bot.stop_trading),
        ("emergency_stop", bot.emergency_stop),
        ("metrics", bot.metrics_cmd),
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
    ])

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
    ])

    if bot.scalper:
        _register_command_group(app, [
            ("s_menu", bot.scalper.cmd_menu),
            ("s_posisi", bot.scalper.cmd_posisi),
            ("s_analisa", bot.scalper.cmd_analisa),
            ("s_buy", bot.scalper.cmd_buy),
            ("s_sell", bot.scalper.cmd_sell),
            ("s_sltp", bot.scalper.cmd_sltp),
            ("s_cancel", bot.scalper.cmd_cancel),
            ("s_info", bot.scalper.cmd_info),
            ("s_pair", bot.scalper.cmd_pair),
            ("s_reset", bot.scalper.cmd_reset),
            ("s_portfolio", bot.scalper.cmd_portfolio),
            ("s_closeall", bot.scalper.cmd_close_all),
            ("s_riwayat", bot.scalper.cmd_riwayat),
            ("s_sync", bot.scalper.cmd_sync),
        ])
        bot.app.logger.info("✅ Scalper module commands registered") if hasattr(bot.app, "logger") else None

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text_input))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/"), bot.handle_unknown_command))
    app.add_handler(CallbackQueryHandler(bot.callback_handler))
